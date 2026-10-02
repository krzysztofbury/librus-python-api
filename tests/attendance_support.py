"""Independently authored attendance markup and loopback wire fixtures."""

import json
from html import escape

from aiohttp import web

from tests.http_support import SchoolFixture


def gateway_rows(types: tuple[int, ...] = (1, 2, 100, 1266, 3)) -> bytes:
    return json.dumps(
        {
            "Attendances": [
                {
                    "Id": index + 1,
                    "Date": "2026-10-01",
                    "Semester": 1,
                    "Type": {"Id": kind},
                    "Lesson": {"Id": 41},
                    "LessonNo": 2,
                }
                for index, kind in enumerate(types)
            ]
        }
    ).encode()


DETAIL = (
    '<div class="container-background"><table>'
    '<tr class="line0"><th>Data:</th><td>2026-10-01</td></tr>'
    '<tr class="line1"><th>Temat zajęć:</th><td>Fixture<br>topic</td></tr>'
    "</table></div>"
)


def attendance_box(
    symbol: str = "nb",
    day: str = "2026-10-01",
    *,
    extra: str = "Lekcja: Fixture Biology<br>Godzina lekcyjna: 3<br>Czy wycieczka: Nie",
    onclick: str = "otworz_w_nowym_oknie('/przegladaj_nb/szczegoly/2468', 'fixture')",
) -> str:
    title = (
        "Data: " + day + "<br>Rodzaj: Fixture absence<br>Nauczyciel: Fixture Teacher"
    )
    if extra:
        title += "<br>" + extra
    return (
        '<a title="'
        + escape(title, quote=True)
        + '" onclick="'
        + escape(onclick, quote=True)
        + '">'
        + escape(symbol)
        + "</a>"
    )


def attendance_html(
    first: str | None = None,
    second: str = "",
    *,
    reverse: bool = False,
) -> str:
    if first is None:
        first = attendance_box()
    sections = [
        '<tr class="line1"><td class="bolded center">I okres</td></tr>'
        '<tr class="line0"><td>Fixture day</td><td class="center">'
        + first
        + "</td></tr>",
        '<tr class="line0"><td class="center bolded">II okres</td></tr>'
        '<tr class="line1"><td>Fixture day</td><td class="center">'
        + second
        + "</td></tr>",
    ]
    if reverse:
        sections.reverse()
    return (
        '<html><body><table class="decorated big center"><thead><tr>'
        "<th>Fixture grid</th>"
        "</tr></thead><tbody>" + "".join(sections) + "</tbody></table></body></html>"
    )


class AttendanceFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.view_posts: list[tuple[str, dict[str, str]]] = []

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_post("/przegladaj_nb/uczen", self.attendance)
        return app

    async def attendance(self, request: web.Request) -> web.Response:
        login = self.record(request)
        form = {key: str(value) for key, value in (await request.post()).items()}
        assert form in (
            {"zmiany_logowanie_wszystkie": ""},
            {"zmiany_logowanie_tydzien": "zmiany_logowanie_tydzien"},
            {"zmiany_logowanie": "zmiany_logowanie"},
        )
        assert "X-Requested-With" not in request.headers
        self.view_posts.append((login, form))
        return web.Response(
            text=attendance_html(
                first=attendance_box(
                    day="2026-10-01"
                    if "zmiany_logowanie_wszystkie" in form
                    else "2026-10-02"
                    if "zmiany_logowanie_tydzien" in form
                    else "2026-10-03",
                    extra="Lekcja: Fixture " + login,
                ),
                second=attendance_box(day="2027-02-03")
                if "zmiany_logowanie_wszystkie" in form
                else "",
            ),
            content_type="text/html",
        )
