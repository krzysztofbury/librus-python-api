"""New synthetic grade markup and HTTP fixtures, not copied school captures."""

import asyncio
from html import escape

from aiohttp import web

from tests.http_support import SchoolFixture


def summary_html(
    subject: str = "Fixture Language",
    annual: str = "4+",
    midterm: str = "progressing",
    predicted: str = "-",
    *,
    include_midterm: bool = True,
    include_predicted: bool = True,
) -> str:
    # Deliberately different column order, element types, values, and structure
    # from research material. Unused spanning headers exercise semantic alignment.
    headers = [
        '<th title="Ocena roczna&lt;br /&gt;fixture year">Annual</th>',
        '<th colspan="2">Unrelated display columns</th>',
    ]
    cells = [f"<td>{escape(annual)}</td>", "<td></td>", "<td></td>"]
    if include_midterm:
        headers.append('<th title="Ocena śródroczna z pierwszego okresu">Midterm</th>')
        cells.append(f"<td>{escape(midterm)}</td>")
    if include_predicted:
        headers.append('<th title="Przewidywana ocena roczna">Forecast</th>')
        cells.append(f"<td>{escape(predicted)}</td>")
    return (
        '<!doctype html><html><body><table class="stretch fixture decorated">'
        f"<thead><tr>{''.join(headers)}</tr></thead><tbody>"
        f"<tr><td></td><td>{escape(subject)}</td>{''.join(cells)}</tr>"
        "</tbody></table></body></html>"
    )


class GradeFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.grade_status: dict[str, int] = {}
        self.expire_grades: dict[str, int] = {}
        self.grade_body: str | None = None
        self.grade_bodies: dict[str, str] = {}
        self.grade_content_type = "text/html"
        self.wait_grades: asyncio.Event | None = None
        self.grades_started = asyncio.Event()

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get("/przegladaj_oceny/uczen", self.grades)
        return app

    async def grades(self, request: web.Request) -> web.Response:
        login = self.record(request)
        assert not request.query
        self.grades_started.set()
        if self.wait_grades is not None:
            await self.wait_grades.wait()
        if self.expire_grades.get(login, 0):
            self.expire_grades[login] -= 1
            return web.Response(status=401)
        if login in self.grade_status:
            return web.Response(status=self.grade_status[login])
        return web.Response(
            text=self.grade_body
            if self.grade_body is not None
            else self.grade_bodies.get(login, summary_html(subject=f"Fixture {login}")),
            content_type=self.grade_content_type,
        )
