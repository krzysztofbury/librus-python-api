"""Independently authored two-origin attachment wire fixtures, never live data."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiohttp import web

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    MessageAttachmentReference,
    MessageFolder,
    MessageReference,
    SchedulerLimits,
)
from tests.http_support import FIXTURE_SECRET, SchoolFixture, serve


def reference(account: str = "student") -> MessageAttachmentReference:
    return MessageAttachmentReference(
        MessageReference(MessageFolder.RECEIVED, "101", account), "301"
    )


class AttachmentFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.download_origin = ""
        self.location: str | None = None
        self.resolve_status, self.download_status = 302, 200
        self.body = b"original invented attachment bytes\n"
        self.encoding: str | None = None
        self.declared: int | None = None
        self.resolutions: list[str] = []
        self.downloads: list[dict[str, str]] = []
        self.body_started = asyncio.Event()
        self.headers_hold: asyncio.Event | None = None
        self.body_hold: asyncio.Event | None = None
        self.resolve_hold: asyncio.Event | None = None
        self.resolve_started = asyncio.Event()
        self.truncate = False
        self.disconnect = False
        self.repetitions = 1

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get(
            "/wiadomosci/pobierz_zalacznik/{message_id}/{file_id}", self.resolve
        )
        return app

    def download_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/GetFile/{key}/get", self.download)
        return app

    async def resolve(self, request: web.Request) -> web.Response:
        account = self.record(request)
        self.resolutions.append(account)
        self.resolve_started.set()
        assert request.match_info == {"message_id": "101", "file_id": "301"}
        assert not request.query and await request.read() == b""
        if self.resolve_hold is not None:
            await self.resolve_hold.wait()
        location = (
            self.location
            if self.location is not None
            else self.download_origin + "/GetFile/Fixture-Key_123"
        )
        return web.Response(
            status=self.resolve_status, headers={"Location": location}, body=b""
        )

    async def download(self, request: web.Request) -> web.StreamResponse:
        self.downloads.append(dict(request.headers))
        if self.disconnect:
            assert request.transport is not None
            request.transport.close()
            return web.Response()
        if self.headers_hold is not None:
            await self.headers_hold.wait()
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="Fixture file.bin"',
            "Set-Cookie": "download-secret=do-not-store; Path=/",
        }
        if self.encoding:
            headers["Content-Encoding"] = self.encoding
        if self.declared is not None:
            headers["Content-Length"] = str(self.declared)
        if self.body_hold is None and not self.truncate and self.repetitions == 1:
            return web.Response(
                status=self.download_status, headers=headers, body=self.body
            )
        response = web.StreamResponse(status=self.download_status, headers=headers)
        await response.prepare(request)
        try:
            for _ in range(self.repetitions):
                await response.write(self.body)
            self.body_started.set()
            if self.truncate:
                assert request.transport is not None
                request.transport.close()
            else:
                if self.body_hold is not None:
                    await self.body_hold.wait()
                await response.write_eof()
        except ConnectionResetError:
            pass
        return response


@asynccontextmanager
async def rig(
    aliases: tuple[str, ...] = ("student",), **options: Any
) -> AsyncIterator[tuple[AttachmentFixture, LibrusService]]:
    fixture = AttachmentFixture()
    async with (
        serve(fixture.app()) as source,
        serve(fixture.download_app()) as download,
    ):
        download = options.pop("download_origin_override", download)
        fixture.origin, fixture.download_origin = source, download
        async with LibrusService(
            {a: AccountCredentials(login=a, password=FIXTURE_SECRET) for a in aliases},
            connection=ConnectionSettings(
                synergia_origin=source, api_origin=source, download_origin=download
            ),
            scheduler_limits=options.pop(
                "scheduler_limits", SchedulerLimits(requests_per_second=1000, burst=40)
            ),
            **options,
        ) as service:
            try:
                yield fixture, service
            finally:
                for hold in (
                    fixture.body_hold,
                    fixture.headers_hold,
                    fixture.resolve_hold,
                ):
                    if hold is not None:
                        hold.set()


async def queued(service: LibrusService, count: int = 1) -> None:
    for _ in range(200):
        if service.snapshot().queued == count:
            return
        await asyncio.sleep(0.001)
    raise AssertionError("Expected scheduler queue was not reached")
