"""Original invented menu/read-once fixtures, never copied or live data."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiohttp import web

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    SchedulerLimits,
)
from tests.http_support import FIXTURE_SECRET, GRAPHIC_MENU, SchoolFixture, serve


def counts_html() -> str:
    return f"<html><body>{GRAPHIC_MENU}</body></html>"


def event_row(data: str = "Fixture event<br>Second line") -> str:
    return (
        "<tr><td>1</td><td>2026-10-02 08:00</td>"
        f"<td>Added fixture</td><td>{data}</td></tr>"
    )


def events_html(rows: str | None = None) -> bytes:
    return (
        """<html><body><div class="container-background"><table>
    <thead><tr><th>Lp.</th><th>Czas dodania</th>
    <th>Rodzaj zdarzenia</th><th>Dane</th></tr></thead>
    <tbody>"""
        + (event_row() if rows is None else rows)
        + "</tbody></table></div></body></html>"
    ).encode()


class NotificationsFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.payload = events_html()
        self.mime = "text/html"
        self.encoding: str | None = None
        self.status = 200
        self.location = "/loguj"
        self.disconnect = False
        self.calls_by_account: list[str] = []
        self.pending = asyncio.Event()
        self.body_hold: asyncio.Event | None = None

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get("/terminarz/dodane_od_ostatniego_logowania", self.consume)
        return app

    async def consume(self, request: web.Request) -> web.StreamResponse:
        account = self.record(request)
        self.calls_by_account.append(account)
        assert await request.read() == b"" and not request.query
        if self.disconnect:
            assert request.transport is not None
            request.transport.close()
            return web.Response()
        headers = {
            "Content-Type": self.mime,
            "Location": self.location,
            "Set-Cookie": "private-cookie=never-checkpoint; Path=/",
        }
        if self.encoding:
            headers["Content-Encoding"] = self.encoding
        if self.body_hold is not None:
            response = web.StreamResponse(status=self.status, headers=headers)
            await response.prepare(request)
            await response.write(self.payload[:10])
            self.pending.set()
            await self.body_hold.wait()
            try:
                await response.write(self.payload[10:])
                await response.write_eof()
            except ConnectionResetError:
                pass
            return response
        return web.Response(status=self.status, headers=headers, body=self.payload)


@asynccontextmanager
async def rig(
    aliases: tuple[str, ...] = ("student",), **options: Any
) -> AsyncIterator[tuple[NotificationsFixture, LibrusService]]:
    fixture = NotificationsFixture()
    async with serve(fixture.app()) as origin:
        fixture.origin = origin
        async with LibrusService(
            context_key=bytes(range(32)),
            accounts={
                a: AccountCredentials(login=a, password=FIXTURE_SECRET) for a in aliases
            },
            connection=ConnectionSettings(synergia_origin=origin, api_origin=origin),
            scheduler_limits=options.pop(
                "scheduler_limits", SchedulerLimits(requests_per_second=1000, burst=40)
            ),
            **options,
        ) as service:
            try:
                yield fixture, service
            finally:
                if fixture.body_hold is not None:
                    fixture.body_hold.set()
