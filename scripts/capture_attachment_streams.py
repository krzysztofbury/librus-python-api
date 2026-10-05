"""Explicitly authorized bounded attachment discovery and installed smoke.

Each invocation has one login, 24 total wire attempts, one page-zero list per
folder, at most one already-read received content open and, in smoke only, one
selected attachment up to 10 MiB. No file bytes are retained. Private message
captures are outside Git and must be deleted after offline comparison.
"""

import argparse
import asyncio
import json
import secrets
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
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
from librus_python_api.models import (
    AttachmentHeaders,
    MessageFolder,
    RequestForm,
    TransportResponse,
)
from librus_python_api.scheduler import RequestScheduler
from scripts.capture_messages import write_private
from scripts.live_capture import ReadOnlyCaptureTransport, private_directory


class StreamAudit:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.requests = self.logins = 0
        self.failed = False
        self.message_id: str | None = None
        self.file_id: str | None = None
        self.counts: Counter[str] = Counter()

    def admit(self, endpoint: Endpoint, form: RequestForm, url: str) -> None:
        operation = endpoint.operation_id
        if self.failed or self.requests >= 24:
            raise LibrusError(ErrorKind.LIMIT)
        if operation in {"messages_received", "messages_sent"}:
            folder = MessageFolder(operation.removeprefix("messages_"))
            if self.counts[operation] or form != message_page_form(folder, 0):
                raise LibrusError(ErrorKind.INVALID_INPUT)
        elif operation in {"message_content_received", "attachment_resolve"}:
            path = endpoint.path.replace("{id}", self.message_id or "")
            if operation == "attachment_resolve":
                if self.mode != "smoke" or self.file_id is None:
                    raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
                path = endpoint.path.format(
                    message_id=self.message_id, file_id=self.file_id
                )
            target = urlsplit(url)
            if (
                self.message_id is None
                or self.counts[operation]
                or form is not None
                or target.path != path
                or target.query
                or target.fragment
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

    def admit_download(self, max_bytes: int) -> None:
        if self.failed or self.requests >= 24:
            raise LibrusError(ErrorKind.LIMIT)
        if (
            self.mode != "smoke"
            or self.file_id is None
            or self.counts["attachment_resolve"] != 1
            or self.counts["attachment_download"]
            or max_bytes > 10 * 1024 * 1024
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        self.requests += 1
        self.counts["attachment_download"] += 1


class StreamCaptureTransport(ReadOnlyCaptureTransport):
    def __init__(
        self,
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
        audit: StreamAudit,
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
            if endpoint.operation_id in {
                "messages_received",
                "messages_sent",
                "message_content_received",
            }:
                assert form is None or isinstance(form, Mapping)
                name = f"{len(self.index):02d}-{endpoint.operation_id}.html"
                write_private(self.out / name, response.body)
                self.index.append(
                    {
                        "file": name,
                        "endpoint": endpoint.operation_id,
                        "form": dict(form) if form is not None else None,
                        "reference": self.audit.message_id
                        if endpoint.operation_id == "message_content_received"
                        else None,
                        "status": response.status,
                    }
                )
                if response.status != 200:
                    raise LibrusError(ErrorKind.PARSE)
            return response
        except BaseException:
            self.audit.failed = True
            raise

    async def _download_exchange(
        self,
        key: str,
        budget: RequestBudget,
        max_bytes: int,
        opened: Callable[[AttachmentHeaders], None],
        demand: Callable[[], Awaitable[None]],
        deliver: Callable[[bytes], None],
    ) -> None:
        self.audit.admit_download(max_bytes)
        try:
            await super()._download_exchange(
                key, budget, max_bytes, opened, demand, deliver
            )
        except BaseException:
            self.audit.failed = True
            raise


async def capture(
    credentials: AccountCredentials,
    out: Path,
    *,
    mode: str = "discovery",
    account_index: int = 0,
    selection: tuple[str, str] | None = None,
) -> dict[str, object]:
    if mode not in {"discovery", "smoke"}:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if mode == "smoke" and selection is None:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    audit = StreamAudit(mode)
    index: list[dict[str, object]] = []
    report: dict[str, object] = {"mode": mode, "status": "started"}

    def factory(
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
    ) -> StreamCaptureTransport:
        return StreamCaptureTransport(
            account, scheduler, connection, limits, audit, out, index
        )

    try:
        async with LibrusService(
            {"capture": credentials},
            context_key=secrets.token_bytes(32),
            transport_factory=factory,
        ) as service:
            budget = RequestBudget(
                max_requests=24,
                timeout_seconds=240,
                max_response_bytes=12 * 1024 * 1024,
            )
            client = service.account("capture")
            await client.identity(budget=budget)
            received = await client.messages_page(budget=budget)
            await client.messages_page(MessageFolder.SENT, budget=budget)
            candidates = [
                r for r in received.items if r.unread is False and r.has_attachment
            ]
            if selection is not None:
                candidates = [
                    r for r in candidates if r.reference.identifier == selection[0]
                ]
            report["eligible_summaries"] = len(candidates)
            if not candidates:
                report["status"] = "no_eligible_attachment"
            else:
                audit.message_id = candidates[0].reference.identifier
                content = await client.message_content(
                    candidates[0].reference, allow_mark_read=True, budget=budget
                )
                report["attachment_metadata_count"] = len(content.content.attachments)
                if not content.content.attachments:
                    raise LibrusError(ErrorKind.PARSE)
                attachment = next(
                    (
                        a
                        for a in content.content.attachments
                        if selection is None or a.reference.identifier == selection[1]
                    ),
                    None,
                )
                if attachment is None:
                    raise LibrusError(ErrorKind.INVALID_INPUT)
                write_private(
                    out / "selection.json",
                    json.dumps(
                        {
                            "account_index": account_index,
                            "message_id": audit.message_id,
                            "file_id": attachment.reference.identifier,
                        }
                    ).encode(),
                )
                if mode == "smoke":
                    audit.file_id = attachment.reference.identifier
                    total = 0
                    async with client.stream_attachment(
                        attachment.reference, max_bytes=10 * 1024 * 1024, budget=budget
                    ) as stream:
                        async for chunk in stream:
                            assert 1 <= len(chunk) <= 65536
                            total += len(chunk)
                        assert stream.complete
                        declared = stream.metadata.headers.content_length
                        assert declared is None or declared == total
                        report["download"] = {
                            "bytes": total,
                            "complete": stream.complete,
                            "declared_length_present": declared is not None,
                            "declared_length_matches": declared == total
                            if declared is not None
                            else None,
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
    parser.add_argument("--selection", type=Path)
    args = parser.parse_args()
    if args.account not in range(4):
        raise SystemExit(
            "Only an independently authorized account index 0..3 is allowed"
        )
    if args.secrets.stat().st_mode & 0o077 or args.secrets.stat().st_size > 1048576:
        raise SystemExit("Private credential permissions or size rejected")
    values = json.loads(args.secrets.read_text())["accounts"][args.account]
    credentials = AccountCredentials(
        login=values["username"], password=values["password"]
    )
    selection = None
    if args.mode == "smoke":
        if (
            args.selection is None
            or args.selection.stat().st_mode & 0o077
            or args.selection.stat().st_size > 1024
        ):
            raise SystemExit(
                "Smoke requires a private account-bound discovery selection"
            )
        approved = json.loads(args.selection.read_text())
        if approved["account_index"] != args.account:
            raise SystemExit("Discovery selection belongs to a different login context")
        selection = (approved["message_id"], approved["file_id"])
    report = asyncio.run(
        capture(
            credentials,
            private_directory(args.out),
            mode=args.mode,
            account_index=args.account,
            selection=selection,
        )
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(
        0 if report["status"] in {"completed", "no_eligible_attachment"} else 1
    )


if __name__ == "__main__":
    main()
