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
    href: str = "fixture-link",
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
    return f'<span class="grade-box"><a href="{href}" title="{title}">{raw}</a></span>'


def grades_html(
    first: str | None = None,
    second: str = "",
    subject: str = "Fixture Language",
    extra: str = "",
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
    <td>-</td><td>-</td></tr></tbody></table>{extra}</body></html>"""


FORMATIVE_LINK = "/przegladaj_oceny/szczegoly/ksztaltujace/{}"
FORMATIVE_HEADERS = (
    "Przedmiot",
    "Ocena kształtująca",
    "Kategoria",
    "Okres",
    "Data",
    "Typ",
)


def formative_cells(
    text: str = "Fixture observation one.",
    category: str = "FIXTURE AREA (synthetic)",
    period: str = "1",
    day: str = "2041-09-15",
    kind: str = "Fixture current",
    detail: str = "901",
    *,
    assessment: str | None = None,
) -> str:
    """The five data cells of one formative row, in the observed order."""
    if assessment is None:
        assessment = (
            f'<a href="{FORMATIVE_LINK.format(detail)}">{text}</a>'
            '<span class="grade-box"></span>'
        )
    return (
        f'<td class="spacing">{assessment}</td>'
        f'<td class="no-border-left">{category}</td>'
        f'<td class="center no-border-left">{period}</td>'
        f'<td class="center no-border-left">{day}</td>'
        f'<td class="no-border-left">{kind}</td>'
    )


def formative_row(
    subject: str = "KARTA SPOSTRZEŻEŃ",
    *,
    rowspan: str = "1",
    line: int = 0,
    attributes: str = "",
    **cells: str,
) -> str:
    return (
        f'<tr class="line{line}"{attributes}><th rowspan="{rowspan}">{subject}</th>'
        + formative_cells(**cells)
        + "</tr>"
    )


def formative_table(
    rows: str | None = None,
    *,
    headers: tuple[str, ...] = FORMATIVE_HEADERS,
    footer: str = '<tr><td colspan="6"></td></tr>',
) -> str:
    """The "Oceny kształtujące" section with original synthetic rows."""
    if rows is None:
        rows = formative_row() + formative_row(
            "Fixture Language",
            line=1,
            text="Fixture quiz - 80%",
            category="FIXTURE SKILL (synthetic)",
            period="2",
            day="2042-02-03",
            detail="902",
        )
    head = "".join(f"<td>{label}</td>" for label in headers)
    return (
        '<h3 class="center">Oceny kształtujące</h3>'
        '<table class="stretch decorated">'
        f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody>"
        f"<tfoot>{footer}</tfoot></table>"
    )


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
