"""Original semantic announcement requirements and exact loopback HTTP fixture."""

import asyncio
from html import escape

from aiohttp import web

from tests.http_support import SchoolFixture


def announcement_table(
    title: str = "Fixture notice",
    author: str = "Fixture Editor",
    day: str = "2026-10-01",
    content: str = "<p>Fixture first paragraph.</p><p>Fixture final paragraph.</p>",
) -> str:
    return (
        '<table class="margin-top printable big center decorated">'
        '<thead><tr><td colspan="2">' + escape(title) + "</td></tr></thead><tbody>"
        '<tr class="line0"><th>Dodał:</th><td>' + escape(author) + "</td></tr>"
        '<tr class="line1"><th>Data publikacji:</th><td>' + escape(day) + "</td></tr>"
        '<tr class="line0"><th>Treść:</th><td>' + content + "</td></tr>"
        '<tr><td colspan="2"></td></tr></tbody></table>'
    )


def page(*tables: str) -> str:
    return "<!doctype html><html><body>" + "".join(tables) + "</body></html>"


def empty_page() -> str:
    return page(
        '<div class="center container resizeable border-red">'
        "<div><p>Brak ogłoszeń.</p></div></div>"
    )


class AnnouncementsFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.announcement_body: str | None = None
        self.announcement_status = 200
        self.announcement_expiry = 0
        self.announcement_gets: list[str] = []
        self.wait_announcements: asyncio.Event | None = None
        self.announcements_started = asyncio.Event()

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get("/ogloszenia", self.announcements)
        return app

    async def announcements(self, request: web.Request) -> web.Response:
        login = self.record(request)
        assert request.method == "GET"
        assert not request.query and not await request.read()
        assert "X-Requested-With" not in request.headers
        self.announcement_gets.append(login)
        self.announcements_started.set()
        if self.wait_announcements is not None:
            await self.wait_announcements.wait()
        if self.announcement_expiry:
            self.announcement_expiry -= 1
            return web.Response(status=401)
        return web.Response(
            status=self.announcement_status,
            text=self.announcement_body
            if self.announcement_body is not None
            else page(announcement_table(author="Fixture " + login)),
            content_type="text/html",
            headers={"Location": "/loguj"} if self.announcement_status == 302 else None,
        )
