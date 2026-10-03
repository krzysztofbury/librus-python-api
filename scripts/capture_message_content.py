"""Separately authorized content capture: one already-read message, no downloads.

One invocation permits one login submission, 24 wire attempts, one page-zero
list per folder, and at most two opens of the selected already-read received
message. Stop on failure, never automatically rerun. Private captures belong
outside Git and must be deleted after offline comparison.
"""

import argparse
import asyncio
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from librus_python_api import AccountCredentials, LibrusService, RequestBudget
from librus_python_api.config import (
    ConnectionSettings,
    Endpoint,
    SideEffect,
    TransportLimits,
    message_page_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import MessageFolder, RequestForm, TransportResponse
from librus_python_api.scheduler import RequestScheduler
from scripts.capture_messages import write_private
from scripts.live_capture import ReadOnlyCaptureTransport, private_directory


class ContentAudit:
    captured_operations = frozenset(
        {"messages_received", "messages_sent", "message_content_received"}
    )

    def __init__(self) -> None:
        self.requests = self.logins = 0
        self.failed = False
        self.selected: str | None = None
        self.counts: Counter[str] = Counter()

    def admit(self, endpoint: Endpoint, form: RequestForm, url: str) -> None:
        operation = endpoint.operation_id
        if self.failed or self.requests >= 24:
            raise LibrusError(ErrorKind.LIMIT)
        if operation in {"messages_received", "messages_sent"}:
            folder = MessageFolder(operation.removeprefix("messages_"))
            if self.counts[operation] or form != message_page_form(folder, 0):
                raise LibrusError(ErrorKind.INVALID_INPUT)
        elif operation == "message_content_received":
            target = urlsplit(url)
            if (
                self.selected is None
                or self.counts[operation] >= 2
                or form is not None
                or target.query
                or target.fragment
                or target.path != endpoint.path.replace("{id}", self.selected)
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
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


class ContentCaptureTransport(ReadOnlyCaptureTransport):
    def __init__(
        self,
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
        audit: ContentAudit,
        out: Path,
        index: list[dict[str, object]],
    ) -> None:
        super().__init__(account, scheduler, connection, limits)
        self.audit, self.out, self.index = audit, out, index

    async def _exchange(
        self, endpoint: Endpoint, url: str, budget: RequestBudget, form: RequestForm
    ) -> TransportResponse:
        self.audit.admit(endpoint, form, url)
        try:
            response = await super()._exchange(endpoint, url, budget, form)
            if endpoint.operation_id in self.audit.captured_operations:
                assert form is None or isinstance(form, Mapping)
                name = f"{len(self.index):02d}-{endpoint.operation_id}.html"
                write_private(self.out / name, response.body)
                self.index.append(
                    {
                        "file": name,
                        "endpoint": endpoint.operation_id,
                        "form": dict(form) if form is not None else None,
                        "reference": self.audit.selected
                        if endpoint.operation_id == "message_content_received"
                        else None,
                        "status": response.status,
                        "bytes": len(response.body),
                    }
                )
                if response.status != 200:
                    raise LibrusError(ErrorKind.PARSE)
            return response
        except BaseException:
            self.audit.failed = True
            raise


async def capture(
    credentials: AccountCredentials, out: Path, *, mode: str = "discovery"
) -> dict[str, object]:
    if mode not in {"discovery", "smoke"}:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    audit = ContentAudit()
    index: list[dict[str, object]] = []

    def factory(
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
    ) -> ContentCaptureTransport:
        return ContentCaptureTransport(
            account, scheduler, connection, limits, audit, out, index
        )

    report: dict[str, object] = {"mode": mode, "status": "started"}
    try:
        async with LibrusService(
            {"capture": credentials}, transport_factory=factory
        ) as service:
            client = service.account("capture")
            budget = RequestBudget(max_requests=24, timeout_seconds=240)
            await client.identity(budget=budget)
            received = await client.messages_page(budget=budget)
            await client.messages_page(MessageFolder.SENT, budget=budget)
            candidates = [r for r in received.items if r.unread is False]
            if not candidates:
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            reference = candidates[0].reference
            audit.selected = reference.identifier
            if mode == "discovery":
                response = await client._transport.request(
                    "message_content_received",
                    budget,
                    reference_id=reference.identifier,
                )
                client._validate_read_response(response, "text/html")
            else:
                result = await client.message_content(
                    reference, allow_mark_read=True, budget=budget, max_age_seconds=60
                )
                before = budget.requests_dispatched
                assert (
                    await client.message_content(
                        reference,
                        allow_mark_read=True,
                        budget=budget,
                        max_age_seconds=60,
                    )
                    is result
                )
                assert budget.requests_dispatched == before
                fresh = await client.message_content(
                    reference, allow_mark_read=True, budget=budget
                )
                assert fresh.content == result.content
                report["content"] = {
                    "characters": len(result.content.text),
                    "attachments": len(result.content.attachments),
                    "may_mark_read": result.may_mark_read,
                    "warm_cache_requests": 0,
                }
            report["status"] = "completed"
    except Exception as error:
        report.update(status="stopped", error_type=type(error).__name__)
    finally:
        report.update(
            requests=audit.requests, logins=audit.logins, operations=dict(audit.counts)
        )
        write_private(out / "index.json", json.dumps({"captured": index}).encode())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--account", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=["discovery", "smoke"], default="discovery")
    args = parser.parse_args()
    if args.account < 0:
        raise SystemExit("Account index must be nonnegative and separately authorized")
    if args.secrets.stat().st_mode & 0o077 or args.secrets.stat().st_size > 1024 * 1024:
        raise SystemExit("Private credential file permissions or size rejected")
    values = json.loads(args.secrets.read_text())["accounts"][args.account]
    credentials = AccountCredentials(
        login=values["username"], password=values["password"]
    )
    report = asyncio.run(
        capture(credentials, private_directory(args.out), mode=args.mode)
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
