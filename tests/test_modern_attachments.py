"""Original modern resolution and credential-free download wire proofs."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import (
    LibrusService,
    MessageFolder,
    ModernMessageAttachmentReference,
    ModernMessageReference,
    RequestBudget,
    SchedulerLimits,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.files import publish_attachment
from tests.http_support import serve
from tests.test_modern_communication import CommunicationFixture


def reference(
    account: str = "student", archived: bool = False
) -> ModernMessageAttachmentReference:
    return ModernMessageAttachmentReference(
        ModernMessageReference(MessageFolder.RECEIVED, "19001", account),
        "401",
        archived,
    )


class DownloadFixture(CommunicationFixture):
    def __init__(self) -> None:
        super().__init__()
        self.downloads: list[dict[str, str]] = []
        self.body = b"original fixture attachment bytes\n"
        self.download_status = 200
        self.block_download = False
        self.download_started = asyncio.Event()
        self.download_release = asyncio.Event()

    def modern_app(self) -> web.Application:
        app = super().modern_app()
        app.router.add_get(
            "/api/attachments/{file_id}/messages/{message_id}", self.resolve
        )
        app.router.add_get(
            "/api/archive/attachments/{file_id}/messages/{message_id}", self.resolve
        )
        return app

    async def resolve(self, request: web.Request) -> web.Response:
        self.record_modern(request, request.path)
        assert request.match_info["file_id"] == "401"
        assert request.match_info["message_id"] == "19001"
        assert not request.query and await request.read() == b""
        return self.response(
            "resolve",
            {"data": {"downloadLink": self.download_origin + "/GetFile/fixture-key"}},
        )

    async def download(self, request: web.Request) -> web.Response:
        self.downloads.append(dict(request.headers))
        assert not request.cookies
        assert not any(
            name in request.headers for name in ("Authorization", "Referer", "Origin")
        )
        assert request.headers["Accept-Encoding"] == "identity"
        assert request.path == "/GetFile/fixture-key/get" and not request.query
        self.download_started.set()
        if self.block_download:
            await self.download_release.wait()
        return web.Response(
            body=self.body,
            status=self.download_status,
            headers={
                "Set-Cookie": "file_session=not-forwarded",
                "Location": "/GetFile/elsewhere",
            },
            content_type="application/octet-stream",
        )

    @asynccontextmanager
    async def running(
        self, aliases: tuple[str, ...] = ("student",), **kwargs: Any
    ) -> AsyncIterator[LibrusService]:
        app = web.Application()
        app.router.add_get("/GetFile/{key}/get", self.download)
        async with serve(app) as download_origin:
            self.download_origin = download_origin
            async with super().running(aliases, **kwargs) as service:
                yield service


@pytest.mark.parametrize("archived", [False, True])
def test_modern_download_is_distinct_bounded_credential_free_and_publishable(
    archived: bool, tmp_path: Path
) -> None:
    async def scenario() -> None:
        fixture = DownloadFixture()
        async with fixture.running() as service:
            client = service.account("student")
            await client.modern_identity()
            budget = RequestBudget(max_requests=4, max_response_bytes=4096)
            stream = client.stream_modern_attachment(
                reference(archived=archived), budget=budget
            )
            assert not fixture.downloads
            saved = await publish_attachment(
                stream, tmp_path, filename="../../Fixture.txt"
            )
            assert saved.path.read_bytes() == fixture.body
            assert saved.path.stat().st_mode & 0o077 == 0
            assert stream.complete and stream.metadata.reference == reference(
                archived=archived
            )
            assert stream.metadata.observation.source == "modern_attachment_download"
            async with client.stream_modern_attachment(
                reference(archived=archived), budget=budget
            ) as again:
                assert b"".join([chunk async for chunk in again]) == fixture.body
            assert budget.requests_dispatched == 4
            assert len(fixture.downloads) == 2
            paths = [p for p, _, _ in fixture.modern_calls if "/attachments/" in p]
            expected = (
                "/api/"
                + ("archive/" if archived else "")
                + "attachments/401/messages/19001"
            )
            assert paths == [expected, expected]
            assert not any("/inbox/messages/" in p for p, _, _ in fixture.modern_calls)
            assert not fixture.sends and service.snapshot().active == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid",
    ["foreign", "userinfo", "query", "redirect", "malformed", "missing", "expiry"],
)
def test_modern_resolver_rejects_unqualified_destination_without_following(
    invalid: str,
) -> None:
    async def scenario() -> None:
        fixture = DownloadFixture()
        async with fixture.running() as service:
            client = service.account("student")
            await client.modern_identity()
            link = fixture.download_origin + "/GetFile/fixture-key"
            status = 200
            body = json.dumps({"data": {"downloadLink": link}}).encode()
            if invalid in {"foreign", "userinfo", "query"}:
                link = {
                    "foreign": "https://foreign.invalid/GetFile/secret",
                    "userinfo": link.replace("://", "://user:secret@"),
                    "query": link + "?token=secret",
                }[invalid]
                body = json.dumps({"data": {"downloadLink": link}}).encode()
            elif invalid == "redirect":
                status = 302
            elif invalid == "malformed":
                body = b"{"
            elif invalid == "missing":
                body = b'{"data":{}}'
            elif invalid == "expiry":
                status = 401
            fixture.responses["resolve"] = (
                status,
                body,
                "application/json",
                {"Location": link},
            )
            budget = RequestBudget(max_requests=1)
            with pytest.raises(LibrusError) as error:
                async with client.stream_modern_attachment(reference(), budget=budget):
                    pass
            assert error.value.kind in {
                ErrorKind.ACCESS_DENIED,
                ErrorKind.SESSION_EXPIRED,
                ErrorKind.UNSUPPORTED_CAPABILITY,
                ErrorKind.PARSE,
            }
            assert not fixture.downloads and budget.requests_dispatched == 1
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode", ["cancel", "deadline", "bytes", "requests", "redirect"]
)
def test_modern_download_limits_and_cancel_release_resources_without_retry(
    mode: str,
) -> None:
    async def scenario() -> None:
        fixture = DownloadFixture()
        fixture.block_download = mode in {"cancel", "deadline"}
        fixture.download_status = 302 if mode == "redirect" else 200
        async with fixture.running() as service:
            client = service.account("student")
            await client.modern_identity()
            budget = RequestBudget(
                max_requests=1 if mode == "requests" else 2,
                timeout_seconds=0.05 if mode == "deadline" else 5,
            )

            async def consume() -> None:
                async with client.stream_modern_attachment(
                    reference(), budget=budget, max_bytes=2 if mode == "bytes" else 4096
                ) as stream:
                    async for _ in stream:
                        pass

            task = asyncio.create_task(consume())
            try:
                if mode == "cancel":
                    async with asyncio.timeout(2):
                        await fixture.download_started.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(LibrusError) as error:
                        await task
                    assert (
                        error.value.kind
                        is (
                            {
                                "deadline": ErrorKind.TIMEOUT,
                                "bytes": ErrorKind.LIMIT,
                                "requests": ErrorKind.LIMIT,
                                "redirect": ErrorKind.ACCESS_DENIED,
                            }[mode]
                        )
                    )
                assert len(fixture.downloads) == (0 if mode == "requests" else 1)
                assert service.snapshot().active == service.snapshot().queued == 0
            finally:
                fixture.download_release.set()

    asyncio.run(scenario())


def test_four_modern_download_accounts_share_queue_and_isolate_cookies() -> None:
    async def scenario() -> None:
        fixture = DownloadFixture()
        fixture.block_download = True
        aliases = tuple(f"fixture-{i}" for i in range(4))
        async with fixture.running(
            aliases,
            scheduler_limits=SchedulerLimits(
                active_requests=2,
                active_requests_per_account=1,
                requests_per_second=1000,
                burst=32,
            ),
        ) as service:
            await asyncio.gather(
                *(service.account(a).modern_identity() for a in aliases)
            )

            async def consume(alias: str) -> bytes:
                async with service.account(alias).stream_modern_attachment(
                    reference(alias)
                ) as stream:
                    return b"".join([chunk async for chunk in stream])

            tasks = [asyncio.create_task(consume(a)) for a in aliases]
            try:
                async with asyncio.timeout(2):
                    await fixture.download_started.wait()
                async with asyncio.timeout(2):
                    for _ in range(1000):
                        if (
                            service.snapshot().active == 2
                            and service.snapshot().queued == 2
                        ):
                            break
                        await asyncio.sleep(0.001)
                    assert service.snapshot().active == 2
                    assert service.snapshot().queued == 2
            finally:
                fixture.download_release.set()
            assert await asyncio.gather(*tasks) == [fixture.body] * 4
            assert {
                login for p, login, _ in fixture.modern_calls if "/attachments/" in p
            } == set(aliases)
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_modern_stream_rejects_cross_account_and_malformed_references_before_io() -> (
    None
):
    async def scenario() -> None:
        fixture = DownloadFixture()
        async with fixture.running() as service:
            client = service.account("student")
            for ref in (
                reference("other"),
                replace(reference(), identifier="../401"),
                replace(reference(), archived=1),  # type: ignore[arg-type]
            ):
                with pytest.raises(LibrusError) as error:
                    client.stream_modern_attachment(ref)
                assert error.value.kind is ErrorKind.INVALID_INPUT
            assert (
                not fixture.calls and not fixture.modern_calls and not fixture.downloads
            )

    asyncio.run(scenario())
