"""Original e-Justifications list markup with invented values.

The shape follows a structure-only observation of two parent logins
(2026-11-13): a filter table, then a list table whose header row holds seven
`td` cells, `line0`/`line1` entry rows and an empty spanning footer cell.
"""

from html import escape

HEADERS = (
    "Załącznik",
    "Okres usprawiedliwienia",
    "Liczba usprawiedliwionych nieobecności",
    "Treść",
    "Powiadomieni nauczyciele",
    "Data wysłania",
    "Status",
)


def entry(
    period: str = "od 2026-10-01 do 2026-10-03",
    count: str = "4",
    content: str = "Fixture reason for the absence.",
    teachers: str = "Fixture Teacher One, Fixture Teacher Two<br>Fixture Teacher Three",
    sent: str = "2026-10-04 08:15:30",
    status: str = "usprawiedliwione (A. Fixture)",
    attachment: str = "",
    line: int = 0,
) -> str:
    cells = (
        attachment,
        f"<b>{escape(period)}</b>",
        escape(count),
        escape(content),
        teachers,
        escape(sent),
        escape(status),
    )
    return (
        f'<tr class="line{line}">' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
    )


def one_day_entry() -> str:
    return entry(
        period="2026-10-07, lekcje: 2, 3",
        count="2",
        content="Fixture visit to a doctor.",
        teachers="Fixture Teacher One",
        sent="2026-10-07 19:02:11",
        status="wysłane",
        line=1,
    )


def justifications_html(
    *rows: str,
    start: str = "2026-10-13",
    end: str = "2026-11-13",
    headers: tuple[str, ...] = HEADERS,
    status_option: str = "",
) -> str:
    if not rows:
        rows = (entry(), one_day_entry())
    options = "".join(
        f'<option value="{value}"{" selected" if value == status_option else ""}>'
        f"{label}</option>"
        for value, label in (
            ("0", "wszystkie"),
            ("1", "wysłane"),
            ("2", "usprawiedliwione"),
            ("3", "odrzucone"),
        )
    )
    return (
        '<!doctype html><html><body><div id="graphic-menu"></div>'
        '<form method="post" action="">'
        '<input type="hidden" name="requestkey" value="fixture-key">'
        '<input type="hidden" name="usprawiedliwienia_filtr" value="1">'
        '<table class="decorated filters small center"><thead><tr>'
        "<td>Od daty</td><td>Do daty</td><td>Status</td></tr></thead><tbody><tr>"
        f'<td><input type="text" name="data_od" value="{start}"></td>'
        f'<td><input type="text" name="data_do" value="{end}"></td>'
        f'<td><select name="status">{options}</select></td>'
        "</tr></tbody></table></form>"
        '<table class="decorated stretch center"><thead><tr>'
        + "".join(f"<td>{escape(label)}</td>" for label in headers)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + '</tbody><tfoot><tr><td colspan="7"></td></tr></tfoot></table>'
        "</body></html>"
    )


# Recorded for a login without entries; its exact markup was not captured.
EMPTY_ROW = '<tr><td colspan="7">Fixture empty list notice</td></tr>'
