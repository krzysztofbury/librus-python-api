"""Independently authored grade markup; no external fixture or captured HTML."""

import asyncio
from html import escape

from aiohttp import web

from tests.http_support import SchoolFixture


def grade_box(
    raw: str = "4+",
    day: str = "2026-09-30",
    *,
    descriptive: bool = False,
    extra: str = "Licz do średniej: tak<br/>Waga: 2<br/>Komentarz: Synthetic: note",
) -> str:
    title = escape(
        f"Data: {day}<br/>Kategoria: Fixture quiz<br/>Nauczyciel: Fixture Teacher"
        + ("<br/>" + extra if extra else ""),
        quote=True,
    )
    if descriptive:
        return (
            f'<span class="grade-box" title="{title}">'
            f'<span class="ocena">{raw}</span></span>'
        )
    return (
        '<span class="grade-box"><a href="fixture-link" '
        f'title="{title}">{raw}</a></span>'
    )


def grades_html(
    first: str | None = None,
    second: str = "",
    subject: str = "Fixture Language",
) -> str:
    if first is None:
        first = grade_box()
    return f"""<!doctype html><html><body>
    <table class="stretch decorated"><thead><tr>
    <th>Oceny bieżące</th><th title="Średnia ocen&lt;br/&gt;Fixture period">Average</th>
    <th title="Ocena śródroczna z pierwszego okresu">Midterm</th>
    <th>Oceny bieżące</th><th title="Średnia ocen z drugiego okresu">Average</th>
    <th title="Przewidywana ocena roczna">Predicted</th>
    <th title="Średnia roczna">Average</th><th title="Ocena roczna">Annual</th>
    </tr></thead><tbody><tr><td></td><td>{subject}</td>
    <td>{first}</td><td>4,25</td><td>-</td><td>{second}</td><td></td><td>-</td>
    <td>-</td><td>-</td></tr></tbody></table></body></html>"""


class GradeRecordsFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.grade_body: str | None = None
        self.grade_status = 200
        self.grade_content_type = "text/html"
        self.view_posts: list[tuple[str, dict[str, str]]] = []
        self.wait_grades: asyncio.Event | None = None
        self.grades_started = asyncio.Event()

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_post("/przegladaj_oceny/uczen", self.grades)
        return app

    async def grades(self, request: web.Request) -> web.Response:
        login = self.record(request)
        form = {key: str(value) for key, value in (await request.post()).items()}
        assert form in (
            {"zmiany_logowanie_wszystkie": "1"},
            {"zmiany_logowanie_tydzien": "1"},
            {"zmiany_logowanie": "1"},
        )
        assert "X-Requested-With" not in request.headers
        self.view_posts.append((login, form))
        self.grades_started.set()
        if self.wait_grades is not None:
            await self.wait_grades.wait()
        return web.Response(
            status=self.grade_status,
            text=self.grade_body
            if self.grade_body is not None
            else grades_html(subject=f"Fixture {login}"),
            content_type=self.grade_content_type,
            headers={"Location": "/loguj"} if self.grade_status == 302 else None,
        )
