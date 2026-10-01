"""Original ordinary-calendar/homework requirements and exact loopback routes."""

import asyncio
import calendar
from datetime import date
from html import escape

from aiohttp import web

from tests.http_support import SchoolFixture


def event_cell(identifier: str = "123", subject: bool = True) -> str:
    return (
        '<td title="Nauczyciel: Fixture Teacher&lt;br /&gt;Opis: Fixture: description" '
        "onclick=\"open('/terminarz/szczegoly/" + identifier + "')\">"
        "Lekcja: 2<br>"
        + ("<span>Fixture Biology</span><br>" if subject else "")
        + "Fixture test<br>Fixture ancillary text</td>"
    )


def agenda_html(year: int = 2026, month: int = 10, cell: str | None = None) -> str:
    days = []
    if cell is None:
        cell = event_cell()
    for number in range(1, calendar.monthrange(year, month)[1] + 1):
        rows = "<table><tr>" + cell + "</tr></table>" if number == 2 and cell else ""
        days.append(
            '<div class="kalendarz-dzien"><div class="kalendarz-numer-dnia">'
            + str(number)
            + "</div>"
            + rows
            + "</div>"
        )
    return "<html><body><!-- Fixture comment -->" + "".join(days) + "</body></html>"


def homework_html(identifier: str = "456", extra: str = "") -> str:
    values = (
        "Fixture topic",
        "Fixture Teacher",
        "Fixture Biology",
        "Fixture practice",
        "2026-09-01",
        "08:15",
        "2026-10-03",
        "12:30",
    )
    cells = "".join("<td>" + escape(value) + "</td>" for value in values)
    return (
        '<html><body><table class="myHomeworkTable decorated"><thead><tr>'
        "<th>Fixture columns</th></tr></thead><tbody>"
        '<tr class="line0">'
        + cells
        + '<td><!-- Fixture comment --><input type="button" '
        "onclick=\"open('/moje_zadania/podglad/"
        + identifier
        + "')\">"
        + extra
        + "</td></tr></tbody></table></body></html>"
    )


def detail_html(
    kind: str = "agenda", value: str = "Fixture<br>complete content"
) -> str:
    tag = "th" if kind == "agenda" else "td"
    return (
        '<html><div class="container-background"><table><thead><tr>'
        '<td colspan="2">Fixture heading</td></tr></thead>'
        '<tbody><tr class="line0"><'
        + tag
        + ">Opis:</"
        + tag
        + "><td>"
        + value
        + "</td></tr>"
        '<tr class="line1"><'
        + tag
        + ">Fixture unknown label</"
        + tag
        + "><td></td></tr>"
        '<tr class="line0"><td colspan="2">Fixture separate note</td></tr>'
        '<tr><td colspan="2"></td></tr></tbody></table></div></html>'
    )


class SchoolReadsFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[tuple[str, str, dict[str, str]]] = []
        self.detail_gets: list[tuple[str, str, str]] = []
        self.status: dict[str, int] = {}
        self.bodies: dict[str, str] = {}
        self.detail_expiry = 0
        self.wait: asyncio.Event | None = None
        self.started = asyncio.Event()

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_post("/terminarz/", self.agenda)
        app.router.add_post("/moje_zadania", self.homework)
        app.router.add_get("/terminarz/szczegoly/{id}", self.agenda_detail)
        app.router.add_get("/moje_zadania/podglad/{id}", self.homework_detail)
        return app

    async def selected(
        self, request: web.Request, kind: str
    ) -> tuple[str, dict[str, str]]:
        login = self.record(request)
        assert not request.query and "X-Requested-With" not in request.headers
        form = {k: str(v) for k, v in (await request.post()).items()}
        self.forms.append((kind, login, form))
        self.started.set()
        if self.wait is not None:
            await self.wait.wait()
        return login, form

    def response(self, kind: str, body: str) -> web.Response:
        return web.Response(
            status=self.status.get(kind, 200),
            text=self.bodies.get(kind, body),
            content_type="text/html",
            headers={"Location": "/loguj"} if self.status.get(kind) == 302 else None,
        )

    async def agenda(self, request: web.Request) -> web.Response:
        login, form = await self.selected(request, "agenda")
        assert set(form) == {"rok", "miesiac"}
        assert form["miesiac"] == f"{int(form['miesiac']):02}"
        return self.response(
            "agenda",
            agenda_html(
                int(form["rok"]),
                int(form["miesiac"]),
                event_cell().replace("Fixture test", "Fixture " + login),
            ),
        )

    async def homework(self, request: web.Request) -> web.Response:
        login, form = await self.selected(request, "homework")
        assert set(form) == {"dataOd", "dataDo", "przedmiot", "status"}
        assert form["przedmiot"] == form["status"] == "-1"
        assert date.fromisoformat(form["dataOd"]) <= date.fromisoformat(form["dataDo"])
        return self.response(
            "homework",
            homework_html().replace(
                "Fixture topic", "Fixture " + login + " " + form["dataOd"]
            ),
        )

    async def detail(self, request: web.Request, kind: str) -> web.Response:
        login = self.record(request)
        assert not request.query and not await request.read()
        self.detail_gets.append((kind, login, request.match_info["id"]))
        if self.detail_expiry:
            self.detail_expiry -= 1
            return web.Response(status=401)
        return self.response(kind + "_detail", detail_html(kind))

    async def agenda_detail(self, request: web.Request) -> web.Response:
        return await self.detail(request, "agenda")

    async def homework_detail(self, request: web.Request) -> web.Response:
        return await self.detail(request, "homework")
