"""Original timetable requirements and independent loopback wire fixture."""

from datetime import date, timedelta
from html import escape

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
