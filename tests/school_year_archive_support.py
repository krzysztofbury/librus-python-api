"""Original synthetic school-year archive pages in the observed table geometry.

Values are inserted as raw HTML so tests can inject unexpected markup. Every
class, year, subject, text and name here is invented.
"""

from collections.abc import Mapping, Sequence

CANARY_NAME = "Canarypupil Zzyzx"
YEARS = (("4q", "2041/2042"), ("5q", "2042/2043"), ("6q", "2043/2044"))
PERIODS = ("okres 1", "okres 2", "koniec roku")
SUBJECTS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    ("Fixture astronomy", (("4", "5", "5"), ("-", "3", "4"), ("6", "6", "6"))),
)
DESCRIPTIVE: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Fixture skills",
        (
            "Synthetic remark one.\n  Continues on a second source line.",
            "Synthetic remark two.",
            "Synthetic remark three.",
        ),
    ),
    ("Fixture conduct notes", ("First note.", "Second note.", "Third note.")),
)
ABSENCES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "nieusprawiedlione": (("0", "1", "1"), ("2", "0", "2"), ("0", "0", "0")),
    "usprawiedlione": (("10", "12", "22"), ("7", "8", "15"), ("3", "4", "7")),
    "spóźnienia": (("1", "0", "1"), ("0", "0", "0"), ("2", "1", "3")),
}
ACHIEVEMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("2042-05-17", "4", "Fixture contest", "Synthetic first place."),
    ("2043-03-02", "5", "Fixture olympiad", "Synthetic finalist."),
)


def _year_header(class_name: str, school_year: str) -> str:
    return (
        '<td colspan="3" class="center"><span>Klasa: <b>'
        f"{class_name}</b></span>&nbsp;&nbsp;"
        f"<span>Rok: <b>{school_year}</b></span></td>"
    )


def _subject_row(label: str, marks: Sequence[Sequence[str]], line: int) -> str:
    cells = "".join(f'<td class="center">{m}</td>' for year in marks for m in year)
    return f'<tr class="line{line}"><th>{label}</th>{cells}</tr>'


def _descriptive_row(label: str, texts: Sequence[str], line: int) -> str:
    cells = "".join(f'<td colspan="3">{text}</td>' for text in texts)
    return f'<tr class="line{line}"><th>{label}</th>{cells}</tr>'


def archive_table(
    *,
    years: Sequence[tuple[str, str]] = YEARS,
    periods: Sequence[str] = PERIODS,
    subjects: Sequence[tuple[str, Sequence[Sequence[str]]]] = SUBJECTS,
    descriptive: Sequence[tuple[str, Sequence[str]]] = DESCRIPTIVE,
    behaviour: Sequence[tuple[str, str]] | None = None,
    behaviour_rows: int = 1,
    absences: Mapping[str, Sequence[Sequence[str]]] = ABSENCES,
    headings: tuple[str, str] = ("Zachowanie", "Nieobecności"),
    body_tail: str = "",
    footer: str | None = None,
) -> str:
    span = 1 + 3 * len(years)
    behaviour = behaviour or [("", "")] * len(years)
    header = "".join(_year_header(c, y) for c, y in years)
    period_cells = "".join(f"<td>{label}</td>" for _ in years for label in periods)
    grade_rows = [
        _subject_row(label, marks, i % 2) for i, (label, marks) in enumerate(subjects)
    ] + [
        _descriptive_row(label, texts, i % 2)
        for i, (label, texts) in enumerate(descriptive)
    ]
    behaviour_row = (
        '<tr class="line1"><th></th>'
        + "".join(f'<td>{a}</td><td colspan="2">{b}</td>' for a, b in behaviour)
        + "</tr>"
    )
    absence_rows = "".join(
        f'<tr class="line{i % 2}"><th>{label}</th>'
        + "".join(f'<td class="center">{v}</td>' for year in values for v in year)
        + "</tr>"
        for i, (label, values) in enumerate(absences.items())
    )
    footer = f'<tr><td colspan="{span}"></td></tr>' if footer is None else footer
    return (
        '<table class="decorated"><thead>'
        f"<tr><td></td>{header}</tr><tr><td></td>{period_cells}</tr>"
        "</thead><tbody>"
        + "".join(grade_rows)
        + f'<tr class="bolded"><td colspan="{span}">{headings[0]}</td></tr>'
        + behaviour_row * behaviour_rows
        + f'<tr class="bolded"><td colspan="{span}">{headings[1]}</td></tr>'
        + absence_rows
        + body_tail
        + f"</tbody><tfoot>{footer}</tfoot></table>"
    )


def achievements_table(
    rows: Sequence[tuple[str, str, str, str]] = ACHIEVEMENTS,
    *,
    headers: Sequence[str] = ("Data", "Klasa", "Kategoria", "Osiągnięcie"),
    body: str | None = None,
) -> str:
    head = "".join(f"<td>{h}</td>" for h in headers)
    cells = (
        "".join(
            f'<tr class="line{i % 2}">'
            + "".join(f"<td>{v}</td>" for v in row)
            + "</tr>"
            for i, row in enumerate(rows)
        )
        if body is None
        else body
    )
    return (
        '<table class="decorated big center">'
        f"<thead><tr>{head}</tr></thead><tbody>{cells}</tbody>"
        '<tfoot><tr><td colspan="4"></td></tr></tfoot></table>'
    )


def archive_page(
    *,
    archive: str | None = None,
    achievements: str | None = None,
    extra: str = "",
    header_name: str = CANARY_NAME,
) -> str:
    """A whole page: name header, archive table, achievements, chart noise."""
    return (
        "<html><body><div class='container-background'>"
        f"<table><tr><td></td><td>Uczeń: {header_name}</td></tr></table>"
        + (archive_table() if archive is None else archive)
        + (achievements_table() if achievements is None else achievements)
        + extra
        + "<div id='gradeChart'></div><script>show_archive_grade_graph();</script>"
        "</div></body></html>"
    )
