"""Original timetable requirements and independent loopback wire fixture."""

import asyncio
from datetime import date, timedelta
from html import escape

from aiohttp import web

from tests.http_support import SchoolFixture

MONDAY = date(2026, 10, 5)


def lesson(
    subject: str = "Fixture Biology", teacher: str = "Fixture Teacher - R12"
) -> str:
    return (
        '<div class="text"><b>'
        + escape(subject)
        + "</b> - "
        + escape(teacher)
        + "</div>"
    )


def notice(label: str = "Fixture change", title: str | None = None) -> str:
    text = escape(label)
    if title is not None:
        text = '<a title="' + escape(title, quote=True) + '">' + text + "</a>"
    return '<div class="plan-lekcji-info center">' + text + "</div>"


def timetable_html(
    monday: date = MONDAY, content: str | None = None, *, tbody: bool = True
) -> str:
    if content is None:
        content = lesson()
    rows = []
    for number, start, end in ((2, "08:10", "08:55"), (4, "09:15", "10:00")):
        cells = [
            '<td class="center">' + str(number) + "</td><th>Fixture time</th><td></td>"
        ]
        for index in range(7):
            day = monday + timedelta(days=index)
            cells.append(
                '<td class="line1" id="timetableEntryBox" data-time_to="'
                + end
                + '" data-date="'
                + day.isoformat()
                + '" data-time_from="'
                + start
                + '">'
                + (content if index == 0 and number == 2 else "")
                + "</td>"
            )
        rows.append('<tr class="line1">' + "".join(cells) + "</tr>")
        if number == 2:
            rows.append(
                '<tr class="line0"><td></td><td class="center">08:55 - 09:15</td>'
                '<td colspan="9"></td></tr>'
            )
    grid = '<table class="plan-lekcji decorated"><tr><th>Fixture week</th></tr>'
    body = "".join(rows)
    grid += ("<tbody>" + body + "</tbody>") if tbody else body
    return "<html><body>" + grid + "</table></body></html>"


class TimetableFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.timetable_body: str | None = None
        self.timetable_status = 200
        self.week_posts: list[tuple[str, dict[str, str]]] = []
        self.wait_timetable: asyncio.Event | None = None
        self.timetable_started = asyncio.Event()

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_post("/przegladaj_plan_lekcji", self.timetable)
        return app

    async def timetable(self, request: web.Request) -> web.Response:
        login = self.record(request)
        form = {key: str(value) for key, value in (await request.post()).items()}
        assert set(form) == {"tydzien"}
        first, last = form["tydzien"].split("_")
        monday = date.fromisoformat(first)
        assert monday.weekday() == 0 and date.fromisoformat(last) == monday + timedelta(
            days=6
        )
        assert "X-Requested-With" not in request.headers
        self.week_posts.append((login, form))
        self.timetable_started.set()
        if self.wait_timetable is not None:
            await self.wait_timetable.wait()
        return web.Response(
            status=self.timetable_status,
            text=self.timetable_body
            if self.timetable_body is not None
            else timetable_html(monday, lesson("Fixture " + login + " " + first)),
            content_type="text/html",
            headers={"Location": "/loguj"} if self.timetable_status == 302 else None,
        )
