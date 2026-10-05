"""Freshly authorized recipient/mailbox discovery, no received opens or writes."""

import argparse
import asyncio
import json
import secrets
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

from librus_python_api import (
    AccountClient,
    AccountCredentials,
    LibrusService,
    MessageFolder,
    MessageReference,
    RequestBudget,
)
from librus_python_api.config import (
    ConnectionSettings,
    Endpoint,
    SideEffect,
    TransportLimits,
    message_page_form,
    recipient_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.messages import parse_messages
from librus_python_api.models import RequestForm, TransportResponse
from librus_python_api.recipients import (
    parse_recipient_group_choices,
    parse_recipient_groups,
)
from librus_python_api.scheduler import RequestScheduler
from scripts.capture_messages import write_private
from scripts.live_capture import ReadOnlyCaptureTransport, private_directory


class CoverageScope:
    captured_operations = frozenset(
        {
            "recipient_groups",
            "recipients",
            "messages_received",
            "messages_sent",
            "message_content_sent",
        }
    )

    def __init__(self) -> None:
        self.requests = self.logins = 0
        self.failed = False
        self.counts: Counter[str] = Counter()
        self.recipient_forms: list[dict[str, str]] = []
        self.allowed_pages = {folder: {0} for folder in MessageFolder}
        self.dispatched_pages: set[tuple[MessageFolder, int]] = set()
        self.sent_reference: str | None = None

    def admit(self, endpoint: Endpoint, form: RequestForm, url: str) -> None:
        name = endpoint.operation_id
        if self.failed or self.requests >= 32:
            raise LibrusError(ErrorKind.LIMIT)
        if name == "recipient_groups":
            if self.counts[name] or form is not None:
                raise LibrusError(ErrorKind.INVALID_INPUT)
        elif name == "recipients":
            if (
                not isinstance(form, Mapping)
                or form not in self.recipient_forms
                or self.counts[name] >= 16
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
            self.recipient_forms.remove(dict(form))
        elif name in {"messages_received", "messages_sent"}:
            folder = MessageFolder(name.removeprefix("messages_"))
            candidates = [
                p
                for p in self.allowed_pages[folder]
                if form == message_page_form(folder, p)
            ]
            if len(candidates) != 1 or (folder, candidates[0]) in self.dispatched_pages:
                raise LibrusError(ErrorKind.INVALID_INPUT)
            self.dispatched_pages.add((folder, candidates[0]))
        elif name == "message_content_sent":
            target = urlsplit(url)
            if (
                self.sent_reference is None
                or self.counts[name]
                or form is not None
                or target.query
                or target.fragment
                or target.path != endpoint.path.replace("{id}", self.sent_reference)
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
        elif name == "identity":
            if self.counts[name] or form is not None:
                raise LibrusError(ErrorKind.INVALID_INPUT)
        elif endpoint.side_effect is not SideEffect.AUTHENTICATION:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if name == "login_submit":
            if self.logins:
                raise LibrusError(ErrorKind.LIMIT)
            self.logins += 1
        self.requests += 1
        self.counts[name] += 1


class CoverageTransport(ReadOnlyCaptureTransport):
    def __init__(
        self,
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
        scope: CoverageScope,
        out: Path,
        index: list[dict[str, object]],
    ) -> None:
        super().__init__(account, scheduler, connection, limits)
        self.scope, self.out, self.index = scope, out, index

    def _get_download_session(self) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    async def _exchange(
        self, endpoint: Endpoint, url: str, budget: RequestBudget, form: RequestForm
    ) -> TransportResponse:
        self.scope.admit(endpoint, form, url)
        try:
            response = await super()._exchange(endpoint, url, budget, form)
            if endpoint.operation_id in self.scope.captured_operations:
                name = f"{len(self.index):02d}-{endpoint.operation_id}.html"
                write_private(self.out / name, response.body)
                self.index.append(
                    {
                        "file": name,
                        "endpoint": endpoint.operation_id,
                        "form": dict(form) if isinstance(form, Mapping) else None,
                        "reference": self.scope.sent_reference
                        if endpoint.operation_id == "message_content_sent"
                        else None,
                        "bytes": len(response.body),
                        "status": response.status,
                    }
                )
                if response.status != 200:
                    raise LibrusError(ErrorKind.PARSE)
                if endpoint.operation_id in {"messages_received", "messages_sent"}:
                    folder = MessageFolder(
                        endpoint.operation_id.removeprefix("messages_")
                    )
                    if form == message_page_form(folder, 0):
                        try:
                            items, count, _ = parse_messages(
                                response.body, folder, 0, "capture"
                            )
                        except LibrusError:
                            items, count = (), 1
                        self.scope.allowed_pages[folder].update(range(1, min(count, 3)))
                        if folder is MessageFolder.SENT and items:
                            self.scope.sent_reference = items[0].reference.identifier
            return response
        except BaseException:
            self.scope.failed = True
            raise


async def smoke(
    client: AccountClient, scope: CoverageScope, budget: RequestBudget
) -> dict[str, object]:
    groups = await client.recipient_groups(budget=budget, max_age_seconds=60)
    scope.recipient_forms = [
        recipient_form(g.reference.identifier) for g in groups.groups if g.available
    ]
    report: dict[str, object] = {"group_types": len(groups.groups)}
    total = unnamed = unavailable = choices_count = 0
    for group in groups.groups:
        if not group.available:
            continue
        if group.reference.identifier == "grupa":
            choices = await client.recipient_group_choices(
                group.reference, budget=budget, max_age_seconds=60
            )
            choices_count += len(choices.items)
            selections = [c.reference for c in choices.items if c.available][:2]
            scope.recipient_forms.extend(
                recipient_form("grupa", selection_id=s.selection_id) for s in selections
            )
        else:
            selections = [group.reference]
        for selection in selections:
            try:
                items = await client.recipients(
                    selection, budget=budget, max_age_seconds=60
                )
            except LibrusError as error:
                if error.kind is not ErrorKind.UNSUPPORTED_CAPABILITY:
                    raise
                unavailable += 1
                continue
            total += len(items.items)
            unnamed += sum(r.label is None for r in items.items)
            before = budget.requests_dispatched
            assert (
                await client.recipients(selection, budget=budget, max_age_seconds=60)
                is items
            )
            assert before == budget.requests_dispatched
    report.update(
        recipient_rows=total,
        unnamed_recipients=unnamed,
        unavailable_types=unavailable,
        group_choices=choices_count,
    )
    for folder in MessageFolder:
        batch = await client.messages(
            folder, max_pages=3, limit=150, budget=budget, max_age_seconds=60
        )
        before = budget.requests_dispatched
        assert (
            await client.messages(
                folder, max_pages=3, limit=150, budget=budget, max_age_seconds=60
            )
            is batch
        )
        assert before == budget.requests_dispatched
        report[folder.value + "_rows"] = len(batch.items)
        report[folder.value + "_pages_fetched"] = batch.pages_fetched
    if scope.sent_reference:
        reference = MessageReference(
            MessageFolder.SENT, scope.sent_reference, "capture"
        )
        content = await client.message_content(
            reference, budget=budget, max_age_seconds=60
        )
        before = budget.requests_dispatched
        assert (
            await client.message_content(reference, budget=budget, max_age_seconds=60)
            is content
        )
        assert before == budget.requests_dispatched
        assert content.may_mark_read is False
        report["recipient_receipts"] = len(content.content.recipient_receipts)
    report["warm_cache_requests"] = 0
    return report


async def capture(
    credentials: AccountCredentials,
    out: Path,
    connection: ConnectionSettings | None = None,
    *,
    mode: str = "discovery",
) -> dict[str, object]:
    if mode not in {"discovery", "smoke"}:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    scope = CoverageScope()
    index: list[dict[str, object]] = []
    report: dict[str, object] = {"status": "started", "mode": mode}

    def factory(
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
    ) -> CoverageTransport:
        return CoverageTransport(
            account, scheduler, connection, limits, scope, out, index
        )

    try:
        async with LibrusService(
            {"capture": credentials},
            context_key=secrets.token_bytes(32),
            connection=connection,
            transport_factory=factory,
        ) as service:
            client = service.account("capture")
            budget = RequestBudget(max_requests=32, timeout_seconds=240)
            await client.identity(budget=budget)
            if mode == "smoke":
                report.update(await smoke(client, scope, budget), status="completed")
                return report
            response = await client._transport.request("recipient_groups", budget)
            client._validate_read_response(response, "text/html")
            groups = parse_recipient_groups(response.body, "capture")
            scope.recipient_forms = [
                recipient_form(g.reference.identifier) for g in groups if g.available
            ]
            report["group_types"] = len(groups)
            # Discovery must preserve unsupported hierarchical/empty layouts for
            # diagnosis, without claiming that the current public parser accepts.
            for form in tuple(scope.recipient_forms):
                response = await client._transport.request(
                    "recipients", budget, form=form
                )
                client._validate_read_response(response, "text/html")
                if form["typAdresata"] == "grupa":
                    from librus_python_api import RecipientGroupReference

                    try:
                        choices = parse_recipient_group_choices(
                            response.body, RecipientGroupReference("grupa", "capture")
                        )
                    except LibrusError:
                        report["group_choice_parser_error"] = True
                        choices = ()
                    report["group_choices"] = len(choices)
                    # Only observed nonzero available options authorize these
                    # two bounded selector forms, never arbitrary IDs or
                    # virtual classes.
                    selected = [c for c in choices if c.available][:2]
                    for choice in selected:
                        selected_form = recipient_form(
                            "grupa", selection_id=choice.reference.selection_id
                        )
                        scope.recipient_forms.append(selected_form)
                        selected_response = await client._transport.request(
                            "recipients", budget, form=selected_form
                        )
                        client._validate_read_response(selected_response, "text/html")
            for folder in MessageFolder:
                response = await client._transport.request(
                    "messages_" + folder.value,
                    budget,
                    form=message_page_form(folder, 0),
                )
                client._validate_read_response(response, "text/html")
                try:
                    items, count, _ = parse_messages(
                        response.body, folder, 0, "capture"
                    )
                    report[folder.value + "_rows"] = len(items)
                    report[folder.value + "_pages"] = count
                    if folder is MessageFolder.SENT and items:
                        scope.sent_reference = items[0].reference.identifier
                except LibrusError:
                    # Do not guess a sent message reference from unknown markup.
                    count = 1
                    report[folder.value + "_parser_error"] = True
                scope.allowed_pages[folder].update(range(1, min(count, 3)))
                for page in range(1, min(count, 3)):
                    response = await client._transport.request(
                        "messages_" + folder.value,
                        budget,
                        form=message_page_form(folder, page),
                    )
                    client._validate_read_response(response, "text/html")
            if scope.sent_reference:
                response = await client._transport.request(
                    "message_content_sent", budget, reference_id=scope.sent_reference
                )
                client._validate_read_response(response, "text/html")
            report["status"] = "completed"
    except Exception as error:
        report.update(status="stopped", error_type=type(error).__name__)
    finally:
        report.update(
            requests=scope.requests,
            logins=scope.logins,
            operations=dict(scope.counts),
            received_opens=0,
            downloads=0,
            read_once_requests=0,
        )
        write_private(
            out / "index.json",
            json.dumps({"captured": index, "report": report}).encode(),
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--account", type=int, choices=range(4), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=["discovery", "smoke"], default="discovery")
    args = parser.parse_args()
    if args.secrets.stat().st_mode & 0o077 or args.secrets.stat().st_size > 1048576:
        raise SystemExit("Private credential file rejected")
    account = json.loads(args.secrets.read_text())["accounts"][args.account]
    report = asyncio.run(
        capture(
            AccountCredentials(login=account["username"], password=account["password"]),
            private_directory(args.out),
            mode=args.mode,
        )
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
