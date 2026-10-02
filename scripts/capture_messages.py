"""Explicitly authorized message-list capture; never opens, sends or deletes.

The two fixed pagination POSTs select received/sent lists. Captures are private,
outside every Git work tree, and must be deleted after offline diagnosis. One
run permits at most one credential submission, 24 total wire attempts and ten
list requests, restricted to pages zero through two. No automatic reruns.
"""

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

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
    message_page_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import MessageFolder, RequestForm, TransportResponse
from librus_python_api.scheduler import RequestScheduler
from librus_python_api.transport import AiohttpTransport
from scripts.live_capture import private_directory


class CaptureAudit:
    captured_operations = frozenset({"messages_received", "messages_sent"})

    def __init__(self) -> None:
        self.requests = self.logins = self.lists = 0
        self.failed = False
        self.counts: Counter[str] = Counter()

    def admit(self, endpoint: Endpoint, form: RequestForm) -> None:
        operation = endpoint.operation_id
        if self.failed or self.requests >= 24:
            raise LibrusError(ErrorKind.LIMIT)
        if operation in {"messages_received", "messages_sent"}:
            folder = MessageFolder(operation.removeprefix("messages_"))
            if self.lists >= 10 or not any(
                form == message_page_form(folder, p) for p in range(3)
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
            self.lists += 1
        elif operation == "identity":
            if self.counts[operation] != 0:
                raise LibrusError(ErrorKind.LIMIT)
        elif endpoint.side_effect != SideEffect.AUTHENTICATION:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if operation == "login_submit":
            if self.logins:
                raise LibrusError(ErrorKind.LIMIT)
            self.logins += 1
        self.requests += 1
        self.counts[operation] += 1


def write_private(path: Path, body: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)


class MessageCaptureTransport(AiohttpTransport):
    def __init__(
        self,
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
        audit: CaptureAudit,
        out: Path,
        index: list[dict[str, object]],
    ) -> None:
        super().__init__(account, scheduler, connection, limits)
        self.audit, self.out, self.index = audit, out, index

    async def _exchange(
        self,
        endpoint: Endpoint,
        url: str,
        budget: RequestBudget,
        form: RequestForm,
    ) -> TransportResponse:
        self.audit.admit(endpoint, form)
        session = self._get_session()
        # Count every actual attempt rather than a dependency's hidden GET replay.
        session._retry_connection = False
        try:
            response = await super()._exchange(endpoint, url, budget, form)
        except BaseException:
            self.audit.failed = True
            raise
        if endpoint.operation_id in self.audit.captured_operations:
            assert form is None or isinstance(form, Mapping)
            name = f"{len(self.index):02d}-{endpoint.operation_id}.html"
            write_private(self.out / name, response.body)
            self.index.append(
                {
                    "file": name,
                    "endpoint": endpoint.operation_id,
                    "form": dict(form) if form is not None else None,
                    "status": response.status,
                    "bytes": len(response.body),
                }
            )
            if response.status != 200:
                self.audit.failed = True
                raise LibrusError(ErrorKind.PARSE)
        return response


async def discover(client: AccountClient, budget: RequestBudget) -> None:
    for folder in MessageFolder:
        response = await client._transport.request(
            "messages_" + folder.value, budget, form=message_page_form(folder, 0)
        )
        client._validate_read_response(response, "text/html")
        # Only inspect pagination, not private rows. An unknown display keeps the
        # discovery to one page; diagnose it offline rather than guessing a count.
        from lxml import html

        document = html.document_fromstring(response.body.decode())
        labels = document.xpath('//div[contains(@class,"pagination")]/span')
        if len(labels) == 1:
            match = re.search(r"([0-9]+)\s*z\s*([0-9]+)", labels[0].text_content())
            if match and int(match[2]) > 1:
                response = await client._transport.request(
                    "messages_" + folder.value,
                    budget,
                    form=message_page_form(folder, 1),
                )
                client._validate_read_response(response, "text/html")


async def smoke(client: AccountClient, budget: RequestBudget) -> dict[str, object]:
    results: dict[str, object] = {}
    for folder in MessageFolder:
        page = await client.messages_page(folder, budget=budget, max_age_seconds=60)
        before = budget.requests_dispatched
        assert (
            await client.messages_page(folder, budget=budget, max_age_seconds=60)
            is page
        )
        assert budget.requests_dispatched == before
        batch = await client.messages(folder, limit=1, max_pages=1, budget=budget)
        assert batch.items == page.items[:1]
        resumed = 0
        if batch.next_cursor and batch.next_cursor.page < 3:
            rest = await client.messages(
                folder, cursor=batch.next_cursor, max_pages=1, budget=budget
            )
            resumed = len(rest.items)
            if batch.next_cursor.offset:
                assert batch.items + rest.items == page.items
        results[folder.value] = {
            "rows": len(page.items),
            "pages": page.page_count,
            "unread": sum(r.unread is True for r in page.items),
            "attachments": sum(r.has_attachment for r in page.items),
            "batch_rows": len(batch.items),
            "resume_rows": resumed,
            "cache_zero_requests": True,
        }
    return results


async def capture(
    credentials: AccountCredentials, out: Path, *, mode: str = "discovery"
) -> dict[str, object]:
    audit = CaptureAudit()
    index: list[dict[str, object]] = []
    if mode not in {"discovery", "smoke"}:
        raise LibrusError(ErrorKind.INVALID_INPUT)
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
                report["reads"] = await smoke(client, budget)
            else:
                await discover(client, budget)
            report["status"] = "completed"
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
    account = json.loads(args.secrets.read_text())["accounts"][args.account]
    credentials = AccountCredentials(
        login=account["username"], password=account["password"]
    )
    out = private_directory(args.out)
    report = asyncio.run(capture(credentials, out, mode=args.mode))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
