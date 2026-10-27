"""Independently authored grade markup; no external fixture or captured HTML."""

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
    rows: str = "",
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
    <td>-</td><td>-</td></tr>{rows}</tbody></table>{extra}</body></html>"""


BEHAVIOUR_DETAIL = "/przegladaj_oceny/zachowanie_szczegoly/{}"


def behaviour_box(points: str = "3", detail: str = "901", **attributes: str) -> str:
    """A behaviour-points entry; its tooltip opens with an unlabelled line."""
    title = escape(
        f"fixture points category({points})<br/>Zakres od: 1<br/>Zakres do: 5"
        "<br />Data wystawienia: 2026-09-21<br />Dodał: Teacher Fixture"
        "<br>Komentarz: Fixture remark",
        quote=True,
    )
    href = attributes.get("href", BEHAVIOUR_DETAIL.format(detail))
    return (
        '<span class="grade-box positive-behaviour">'
        f'<a title="{title}" href="{href}">{points}</a></span>'
    )


def behaviour_points(start: str = "50", boxes: str = "") -> str:
    """A behaviour-row cell: starting points, then any point entries."""
    return (
        '<span class="tooltip" style="cursor: pointer;" title="Punkty startowe">'
        f"\n    {start}    </span>\n{boxes}  &#160;\n"
    )


def behaviour_row(first: str | None = None, second: str | None = None) -> str:
    """The behaviour row: each period's current and average cells are merged."""
    if first is None:
        first = behaviour_points(boxes=behaviour_box())
    if second is None:
        second = behaviour_points()
    return (
        '<tr class="bolded line0"><td class="center micro screen-only"></td>'
        f'<td>\n Zachowanie\n</td><td colspan="2">{first}</td>'
        f'<td class="center">-</td><td colspan="2">{second}</td>'
        '<td>-</td><td>-</td><td class="center">-</td></tr>'
    )


POINT_LINK = "/przegladaj_oceny_punktowe/szczegoly/{}"


def point_box(
    score: str = "90", detail: str = "7001", day: str = "2026-10-05 (pon.)"
) -> str:
    """A percentage entry; its category names the scale, it counts to a result."""
    title = escape(
        f"Kategoria: Fixture essay  (0-100)<br>Data: {day}<br>Nauczyciel: Fixture"
        " Teacher<br>Licz do wyniku: TAK<br/>Fixture pool: NIE",
        quote=True,
    )
    return (
        f'<span class="grade-box"><a title="{title}" '
        f'href="{POINT_LINK.format(detail)}">{score}</a></span>'
    )


def point_row(
    first: str | None = None,
    second: str = "Brak ocen",
    *,
    subject: str = "Fixture Science",
    node: str = "71",
    result: str = "67",
    annual: str = "-",
) -> str:
    """A subject row and its hidden detail row, which mirrors the entries.

    As in an owner-relayed screenshot: 90 and 44 on a 0-100 scale make a
    first-period result of 67 while the period grade is not yet assigned.
    """
    if first is None:
        first = point_box() + point_box("44", "7002", "2026-10-12 (pon.)")
    return (
        f'<tr class="line0"><td class="center micro screen-only"><img '
        f'src="/images/tree_colapsed.png" id="przedmioty_OP_{node}_node"></td>'
        f'<td>{subject}</td><td>{first}</td><td class="center">{result}</td>'
        f'<td class="center"> - </td><td>{second}</td><td class="center"> - </td>'
        f'<td class="center"> - </td><td class="center">{annual}</td></tr>'
        f'<tr class="line1" id="przedmioty_OP_{node}" style="display: none;">'
        f'<td>&nbsp;</td><td colspan="7"><table class="stretch"><tr><td>{first}'
        "</td></tr></table></td></tr>"
    )


def point_table(rows: str | None = None, *, annual: bool = True) -> str:
    """The "Oceny punktowe" section: untitled result columns beside summaries.

    Result columns are known only by their visible "Wyn." labels; which of
    them a school shows varies.
    """
    if rows is None:
        rows = point_row()
    annual_title = ' title="Ocena roczna"' if annual else ""
    return (
        '<h3 class="center">Oceny punktowe</h3><table class="decorated stretch">'
        '<thead><tr><td rowspan="2"></td><td rowspan="2">Przedmiot</td>'
        '<td colspan="3">Okres 1</td><td colspan="2">Okres 2</td>'
        '<td colspan="2">Koniec roku</td></tr><tr><td>Oceny bieżące</td>'
        '<td>Wyn.I</td><td title="Ocena śródroczna z pierwszego okresu">I</td>'
        "<td>Oceny bieżące</td><td>Wyn.II</td><td>Wyn.R</td>"
        f"<td{annual_title}>R</td></tr></thead><tbody>{rows}</tbody></table>"
    )


def _observed_result(value: str) -> str:
    title = escape("Suma punktów: 9<br />Maksymalna ilość punktów: 10", quote=True)
    link = f'<a href="javascript:void()" title="{title}">{value}</a>'
    return f'<td class="right">{link}</td>'


def _observed_detail(node: str, entries: str = "") -> str:
    return (
        f'<tr class="line0" name="przedmioty_OP_all" id="przedmioty_OP_{node}" '
        'style="display: none;"><td>&nbsp;</td><td colspan="12"><table class="stretch">'
        "<thead><tr><td>Ocena</td><td>Kategoria</td></tr></thead><tbody>"
        f'<tr class="line1 bolded"><td colspan="2">Okres 1</td></tr>{entries}</tbody>'
        '<tfoot><tr><td colspan="12"></td></tr></tfoot></table></td></tr>'
    )


def observed_point_page(midterm: str = " - ") -> str:
    """The point-table layout of an owner-relayed page (2026-10-27).

    Original values; the structure follows the page: a period's current
    grades, result and grade under three titled columns, results as links,
    a formative mirror among point entries, an untitled-subject image, the
    merged behaviour row, an over-wide empty footer and the formative table
    whose text holds line breaks.
    """
    formative = (
        '<span class="grade-box"><a title="Ocena: +&lt;br /&gt;\n&lt;br /&gt;\n'
        "Fixture note: text&lt;br&gt;Kategoria: Fixture task"
        "&lt;br&gt;Data: 2026-10-16 (pt.)"
        '&lt;br&gt;Licz do wyniku: NIE" '
        f'href="{FORMATIVE_LINK.format(951)}">T</a></span>'
    )
    head = (
        '<thead><tr><th class="center micro screen-only" rowspan="2"><img '
        'id="przedmioty_OP_all_node"></th><td rowspan="2">Przedmiot</td>'
        '<td class="colspan center" colspan="3"><span>Okres 1</span></td>'
        '<td class="colspan center" colspan="3"><span>Okres 2</span></td>'
        '<td class="colspan" colspan="2"><span>Koniec roku</span></td></tr>'
        '<tr class="no-border-top"><td class="spacing">Oceny bieżące</td>'
        '<td class="center" title="Wynik z pierwszego okresu">Wyn.I</td>'
        '<td title="Ocena śródroczna &lt;br&gt; z pierwszego okresu">I</td>'
        '<td class="center">Oceny bieżące</td>'
        '<td class="center" title="Wynik z drugiego okresu">Wyn.II</td>'
        '<td class="center" title="Ocena śródroczna &lt;br&gt; z drugiego okresu">'
        "II</td>"
        '<td title="Wynik z całego roku szkolnego">Wyn.R</td>'
        '<td title="Ocena roczna">R</td></tr></thead>'
    )
    node = '<td class="center micro screen-only"><img id="przedmioty_OP_{}_node"></td>'
    rows = (
        f'<tr class="line1">{node.format(81)}<td>Fixture Science</td><td>'
        + point_box()
        + point_box("44", "7002", "2026-10-12 (pon.)")
        + formative
        + f'</td>{_observed_result("67")}<td class="center">{midterm}</td>'
        '<td>Brak ocen</td><td class="right">-</td><td class="center"> - </td>'
        f'{_observed_result("67.00")}<td class="center"> - </td></tr>'
        + _observed_detail("81", "<tr><td>90</td><td>Fixture essay</td></tr>")
        + f'<tr class="line0">{node.format(82)}<td>Fixture Workshop<img '
        'src="/images/p_pozalekcyjny.gif" title="Fixture extracurricular"></td>'
        '<td>Brak ocen</td><td class="right">-</td><td class="center"> - </td>'
        '<td>Brak ocen</td><td class="right">-</td><td class="center"> - </td>'
        '<td class="right">0.00</td><td class="center"> - </td></tr>'
        + _observed_detail("82")
        + f'<tr class="bolded line1">{node.format("zachowanie")}'
        '<td class="left">Zachowanie</td><td class="left" colspan="2">&nbsp;</td>'
        '<td class="center">-</td><td colspan="2">&nbsp;</td>'
        '<td class="center" colspan="3">-</td></tr>'
        '<tr class="line0" name="przedmioty_OP_all" id="przedmioty_OP_zachowanie">'
        '<td colspan="12"><table class="stretch"><tr><td>Brak ocen</td></tr></table>'
        "</td></tr>"
    )
    formative_table = (
        '<table class="stretch decorated"><thead><tr><td>Przedmiot</td>'
        "<td>Ocena kształtująca</td><td>Kategoria</td><td>Okres</td><td>Data</td>"
        '<td>Typ</td></tr></thead><tbody><tr class="line0"><th rowspan="1">Fixture'
        ' Science</th><td class="spacing">&nbsp;&nbsp;<a title="" class="" '
        f'href="{FORMATIVE_LINK.format(951)}"><span class="grade-box"></span>+<br>'
        "<br>\nFixture text</a></td><td>Fixture task</td><td>1</td><td>2026-10-16</td>"
        '<td>Fixture current</td></tr></tbody><tfoot><tr><td colspan="6">&nbsp;</td>'
        "</tr></tfoot></table>"
    )
    return (
        '<!doctype html><html><body><h3 class="center">Oceny punktowe</h3>'
        f'<table class="decorated stretch">{head}<tbody>{rows}</tbody><tfoot><tr>'
        f'<td colspan="20">&nbsp;</td></tr></tfoot></table>{formative_table}'
        "</body></html>"
    )


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
    """The five data cells of one formative row, in the observed order.

    Observed 2026-10-08: the empty coloured marker is the link's first child,
    and the link carries empty title and class attributes.
    """
    if assessment is None:
        assessment = (
            f'<a title="" class="" href="{FORMATIVE_LINK.format(detail)}">'
            '<span class="grade-box" style="background-color: #fixture;"></span>'
            f"{text}</a>"
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
        self.view_posts: list[tuple[str, dict[str, str]]] = []

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
        return web.Response(
            text=self.grade_body
            if self.grade_body is not None
            else grades_html(subject=f"Fixture {login}"),
            content_type="text/html",
        )
