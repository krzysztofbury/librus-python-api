"""Original completed-lesson requirements and exact offline HTTP fixtures."""

import asyncio
from html import escape

from aiohttp import web

from tests.http_support import SchoolFixture


def lesson_row(topic: str = "Fixture topic", number: str = "2") -> str:
    return (
        '<tr class="line0"><td class="small center">2026-10-02</td>'
        '<td class="tiny">pt.</td><td>' + escape(number) + "</td>"
        "<td>Fixture Biology, Fixture Teacher</td><td>" + topic + "</td>"
        '<td>Fixture Z</td><td><p class="box"><a '
        "onclick=\"otworz_w_nowym_oknie('/przegladaj_nb/szczegoly/123',"
        "'fixture',800,600)\">nb</a></p></td></tr>"
    )


def lessons_html(page: int = 0, count: int = 1, rows: str | None = None) -> str:
    if rows is None:
        rows = lesson_row()
    return (
        '<html><body><div class="pagination"><span>Strona '
        + str(page + 1)
        + " z "
        + str(count)
        + "</span></div>"
        '<table class="extra decorated"><thead><tr><th>Fixture headings</th></tr>'
        "</thead><tbody>" + rows + "</tbody></table></body></html>"
    )


class CompletedLessonsFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.bodies: dict[int, str] = {
            0: lessons_html(
                0, 2, lesson_row("Fixture first") + lesson_row("Fixture second")
            ),
            1: lessons_html(1, 2, lesson_row("Fixture third")),
        }
        self.forms: list[tuple[str, dict[str, str]]] = []
        self.status: dict[int, int] = {}
        self.wait_page: int | None = None
        self.wait = asyncio.Event()
        self.started = asyncio.Event()

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_post("/zrealizowane_lekcje", self.lessons)
        return app

    async def lessons(self, request: web.Request) -> web.Response:
        login = self.record(request)
        form = {k: str(v) for k, v in (await request.post()).items()}
        self.forms.append((login, form))
        assert set(form) == {
            "data1",
            "data2",
            "filtruj_id_przedmiotu",
            "numer_strony1001",
            "porcjowanie_pojemnik1001",
        }
        assert form["filtruj_id_przedmiotu"] == "-1"
        assert form["porcjowanie_pojemnik1001"] == "1001"
        page = int(form["numer_strony1001"])
        if page == self.wait_page:
            self.started.set()
            await self.wait.wait()
        status = self.status.get(page, 200)
        return web.Response(
            text=self.bodies.get(page, "<html>Fixture missing page</html>"),
            status=status,
            content_type="text/html",
            headers={"Location": "/loguj"} if status == 302 else None,
        )
