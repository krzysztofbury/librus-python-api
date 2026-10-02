"""Separately authorized one-login recipient discovery; never sends or opens mail."""

import argparse
import asyncio
import json
from pathlib import Path

from lxml import html

from librus_python_api import (
    AccountClient,
    AccountCredentials,
    LibrusService,
    RequestBudget,
)
from librus_python_api.config import (
    ConnectionSettings,
    Endpoint,
    SideEffect,
    TransportLimits,
    recipient_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import RequestForm
from librus_python_api.scheduler import RequestScheduler
from scripts.capture_messages import (
    CaptureAudit,
    MessageCaptureTransport,
    write_private,
)
from scripts.live_capture import private_directory

SAMPLED_GROUP_TYPES = ("wychowawca", "nauczyciel", "sekretariat")


class RecipientCaptureAudit(CaptureAudit):
    captured_operations = frozenset({"recipient_groups", "recipients"})

    def __init__(self) -> None:
        super().__init__()
        self.groups: tuple[str, ...] = ()

    def admit(self, endpoint: Endpoint, form: RequestForm) -> None:
        operation = endpoint.operation_id
        if self.failed or self.requests >= 24:
            raise LibrusError(ErrorKind.LIMIT)
        if operation == "recipient_groups":
            if self.counts[operation] >= 2 or form is not None:
                raise LibrusError(ErrorKind.LIMIT)
        elif operation == "recipients":
            if (
                self.lists >= 6
                or len(self.groups) > 3
                or any(g not in SAMPLED_GROUP_TYPES for g in self.groups)
                or not any(form == recipient_form(g) for g in self.groups)
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
            self.lists += 1
        elif operation == "identity":
            if self.counts[operation]:
                raise LibrusError(ErrorKind.LIMIT)
        elif endpoint.side_effect != SideEffect.AUTHENTICATION:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if operation == "login_submit":
            if self.logins:
                raise LibrusError(ErrorKind.LIMIT)
            self.logins += 1
        self.requests += 1
        self.counts[operation] += 1


async def smoke(
    client: AccountClient, audit: RecipientCaptureAudit, budget: RequestBudget
) -> dict[str, object]:
    groups = await client.recipient_groups(budget=budget, max_age_seconds=60)
    before = budget.requests_dispatched
    assert await client.recipient_groups(budget=budget, max_age_seconds=60) is groups
    assert budget.requests_dispatched == before
    selected = {
        g.reference.identifier: g
        for g in groups.groups
        if g.reference.identifier in SAMPLED_GROUP_TYPES
        and g.available
        and g.lookup_supported
    }
    audit.groups = tuple(selected)
    if set(audit.groups) != set(SAMPLED_GROUP_TYPES):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    results: dict[str, object] = {}
    for token, group in selected.items():
        try:
            recipients = await client.recipients(
                group.reference, budget=budget, max_age_seconds=60
            )
            before = budget.requests_dispatched
            assert (
                await client.recipients(
                    group.reference, budget=budget, max_age_seconds=60
                )
                is recipients
            )
            assert budget.requests_dispatched == before
            fresh = await client.recipients(group.reference, budget=budget)
            results[token] = {
                "rows": len(recipients.items),
                "fresh_rows": len(fresh.items),
                "cache_zero_requests": True,
            }
        except LibrusError as error:
            if error.kind not in {ErrorKind.PARSE, ErrorKind.UNSUPPORTED_CAPABILITY}:
                raise
            # Preserve the other approved groups' bytes for offline diagnosis;
            # never call authentication again or conceal failed qualification.
            results[token] = {"parser_error": error.kind.value}
    return results


async def capture(
    credentials: AccountCredentials, out: Path, *, mode: str = "discovery"
) -> dict[str, object]:
    if mode not in {"discovery", "smoke"}:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    audit = RecipientCaptureAudit()
    index: list[dict[str, object]] = []
    report: dict[str, object] = {"status": "started", "mode": mode}

    def factory(
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
    ) -> MessageCaptureTransport:
        return MessageCaptureTransport(
            account, scheduler, connection, limits, audit, out, index
        )

    try:
        async with LibrusService(
            {"capture": credentials}, transport_factory=factory
        ) as service:
            budget = RequestBudget(max_requests=24, timeout_seconds=240)
            client = service.account("capture")
            await client.identity(budget=budget)
            if mode == "smoke":
                results = await smoke(client, audit, budget)
                report["reads"] = results
                report["status"] = (
                    "completed"
                    if all(
                        isinstance(r, dict) and "parser_error" not in r
                        for r in results.values()
                    )
                    else "captured_parser_failure"
                )
                return report
            response = await client._transport.request("recipient_groups", budget)
            client._validate_read_response(response, "text/html")
            document = html.document_fromstring(response.body.decode())
            values = [
                str(v)
                for v in document.xpath(
                    '//table[contains(@class,"message-recipients")]//input[contains(@class,"recipiantTypeRadio")]/@value'
                )
            ]
            if not values or len(values) > 32:
                raise LibrusError(ErrorKind.PARSE)
            audit.groups = tuple(g for g in SAMPLED_GROUP_TYPES if g in values)
            for group in audit.groups:
                response = await client._transport.request(
                    "recipients", budget, form=recipient_form(group)
                )
                client._validate_read_response(response, "text/html")
            report["status"] = "completed"
            report["discovered_types"] = len(values)
            report["sampled_types"] = len(audit.groups)
    except Exception as error:
        report["status"] = "stopped"
        report["error_type"] = type(error).__name__
    finally:
        report.update(
            requests=audit.requests, logins=audit.logins, operations=dict(audit.counts)
        )
        write_private(
            out / "index.json",
            json.dumps({"captured": index, "report": report}).encode(),
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--account", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=["discovery", "smoke"], default="discovery")
    args = parser.parse_args()
    if (
        args.account < 0
        or args.secrets.stat().st_mode & 0o077
        or args.secrets.stat().st_size > 1024 * 1024
    ):
        raise SystemExit("Private credential file or account rejected")
    account = json.loads(args.secrets.read_text())["accounts"][args.account]
    credentials = AccountCredentials(
        login=account["username"], password=account["password"]
    )
    report = asyncio.run(
        capture(credentials, private_directory(args.out), mode=args.mode)
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
