"""Original ordinary-calendar and homework markup requirements."""

import calendar
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


HOMEWORK_FILTERS = (
    '<table class="decorated filters medium center"><tr><td>Data</td>'
    '<td><input name="dataOd" value="2026-09-28"></td></tr></table>'
)
HOMEWORK_HEADER = (
    "<thead><tr><td><a>Przedmiot</a></td><td><a>Nauczyciel</a></td>"
    "<td><a>Temat</a></td><td><a>Kategoria</a></td>"
    '<td colspan="2"><a>Data zadania</a></td>'
    '<td colspan="2"><a>Termin wykonania</a></td>'
    '<td class="tiny"> Status przesyłania rozwiązania <br> <br> '
    '<a><img title="Fixture refresh"></a> <br> </td>'
    '<td class="big">Opcje</td></tr></thead>'
)


def homework_row(
    identifier: str = "456",
    topic: str = "Fixture topic",
    assigned: tuple[str, str] = ("2026-09-16", "śr."),
    due: tuple[str, str] = ("2026-09-17", "czw."),
    options: str = "",
) -> str:
    """Observed column order; due date sits in a layout div, weekdays apart."""
    plain = ("Fixture Biology", "Fixture Teacher", topic, "Fixture category")
    return (
        f'<tr class="line1" id="homework_{identifier}">'
        + "".join(f'<td class=" bold">{escape(value)}</td>' for value in plain)
        + f"<td>{assigned[0]}</td><td>{assigned[1]}</td>"
        + f'<td> <div class="left">{due[0]}</div> <div class="left"> </div> </td>'
        + f"<td>{due[1]}</td><!-- status --><td> - </td><!-- //status -->"
        + '<td><input type="button" value="Podgląd" onclick=" checkAsRead('
        + identifier
        + "); otworz_w_nowym_oknie('/moje_zadania/podglad/"
        + identifier
        + "','o1',650,600); \">"
        + '<input type="button" onclick="showConfirmQuestion(1, 2);" '
        + 'value="Fixture mark done">'
        + options
        + "</td></tr>"
    )


def homework_html(identifier: str = "456", rows: str | None = None) -> str:
    body = homework_row(identifier) if rows is None else rows
    return (
        "<html><body><h2>Zadania domowe</h2>"
        + HOMEWORK_FILTERS
        + '<table class="decorated myHomeworkTable">'
        + HOMEWORK_HEADER
        + "<tbody>"
        + body
        + '</tbody><tfoot><tr><td colspan="10"> </td></tr></tfoot>'
        + "</table></body></html>"
    )


def warning_html(message: str, empty: str | None = None) -> str:
    """Observed page-level information box; empty markers can sit beside it."""
    return (
        '<html><body><h2 class="inside">Fixture view</h2>'
        '<div class="warning-box information"><div class="warning-head">'
        '<div class="warning-title">Informacja</div></div>'
        f'<div class="warning-content">{message}</div>'
        '<div class="warning-buttons"></div></div>'
        + (f'<p class="msgEmptyTable">{empty}</p>' if empty else "")
        + "</body></html>"
    )


HOMEWORK_EMPTY = (
    "<html><body>" + HOMEWORK_FILTERS + '<p class="msgEmptyTable">Brak wpisów</p>'
    "</body></html>"
)
VIEW_DISABLED = "Ten widok został wyłączony przez administratora szkoły."
RANGE_REJECTED = "Wybrano nieprawidłowy zakres daty."


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

    async def selected(
        self, request: web.Request, kind: str
    ) -> tuple[str, dict[str, str]]:
        login = self.record(request)
        assert not request.query and "X-Requested-With" not in request.headers
        form = {k: str(v) for k, v in (await request.post()).items()}
        self.forms.append((kind, login, form))
        return login, form
