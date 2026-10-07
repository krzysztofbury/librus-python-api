"""Original contracts for the school-year archive page (`/archiwum`)."""

from collections.abc import Callable
from datetime import date

import pytest

from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import ArchiveCounts, ArchiveMarks
from librus_python_api.school_year_archive import parse_school_year_archive
from tests.school_year_archive_support import (
    ABSENCES,
    CANARY_NAME,
    SUBJECTS,
    YEARS,
    achievements_table,
    archive_page,
    archive_table,
)


def parse(page: str) -> tuple[object, ...]:
    return parse_school_year_archive(page.encode())


def test_early_education_layout_is_read_per_year() -> None:
    years, achievements = parse_school_year_archive(archive_page().encode())
    assert [(y.class_name, y.school_year, y.first_year) for y in years] == [
        ("4q", "2041/2042", 2041),
        ("5q", "2042/2043", 2042),
        ("6q", "2043/2044", 2043),
    ]
    first = years[0]
    assert [s.subject for s in first.subjects] == ["Fixture astronomy"]
    assert first.subjects[0].marks == ArchiveMarks("4", "5", "5")
    assert years[1].subjects[0].marks == ArchiveMarks("-", "3", "4")
    assert [d.label for d in first.descriptive] == [
        "Fixture skills",
        "Fixture conduct notes",
    ]
    # Source line breaks inside one text node are whitespace, not structure.
    assert first.descriptive[0].text == (
        "Synthetic remark one. Continues on a second source line."
    )
    assert (
        first.behaviour_first_semester,
        first.behaviour_second_semester_and_year_end,
    ) == (
        "",
        "",
    )
    assert first.absences.unexcused == ArchiveCounts(0, 1, 1)
    assert first.absences.excused == ArchiveCounts(10, 12, 22)
    assert years[2].absences.late == ArchiveCounts(2, 1, 3)
    assert [(a.day, a.class_name, a.category) for a in achievements] == [
        (date(2042, 5, 17), "4", "Fixture contest"),
        (date(2043, 3, 2), "5", "Fixture olympiad"),
    ]
    assert achievements[0].text == "Synthetic first place."


def test_unobserved_numeric_layout_with_populated_behaviour_scales_with_years() -> None:
    # Synthetic coverage of an unobserved layout, not a support claim.
    years = tuple((f"{7 + i}r", f"{2040 + i}/{2041 + i}") for i in range(5))
    marks = tuple((str(1 + i % 6), "-", str(2 + i % 5)) for i in range(5))
    subjects = tuple((f"Fixture subject {n}", marks) for n in range(12))
    behaviour = tuple((f"Fixture mark {i}", f"Fixture final {i}") for i in range(5))
    absences = {label: (("0", "0", "0"),) * 5 for label in ABSENCES}
    page = archive_page(
        archive=archive_table(
            years=years,
            subjects=subjects,
            descriptive=(),
            behaviour=behaviour,
            absences=absences,
        )
    )
    parsed, _ = parse_school_year_archive(page.encode())
    assert len(parsed) == 5 and all(len(y.subjects) == 12 for y in parsed)
    assert parsed[4].behaviour_first_semester == "Fixture mark 4"
    assert parsed[4].behaviour_second_semester_and_year_end == "Fixture final 4"


def test_header_only_achievements_table_is_an_explicit_empty_list() -> None:
    _, achievements = parse_school_year_archive(
        archive_page(achievements=achievements_table(())).encode()
    )
    assert achievements == ()


def test_the_name_in_the_page_header_never_reaches_the_result() -> None:
    years, achievements = parse_school_year_archive(archive_page().encode())
    rendered = repr(years) + repr(achievements)
    fields = [
        value
        for year in years
        for value in (
            year.class_name,
            year.school_year,
            *(s.subject for s in year.subjects),
            *(d.text for d in year.descriptive),
        )
    ]
    assert all(CANARY_NAME not in text for text in [rendered, *fields])
    assert "Fixture" not in repr(years[0])  # School text stays out of reprs.


def corrected(label: str) -> dict[str, tuple[tuple[str, str, str], ...]]:
    return {(label if k == "nieusprawiedlione" else k): v for k, v in ABSENCES.items()}


def link_in_mark() -> str:
    marks = (('<a href="/x">5</a>', "5", "5"),) + SUBJECTS[0][1][1:]
    return archive_table(subjects=(("Fixture astronomy", marks),))


MALFORMED: list[tuple[str, Callable[[], str], ErrorKind]] = [
    ("no archive table", lambda: archive_page(archive=""), ErrorKind.PARSE),
    (
        "two archive tables",
        lambda: archive_page(archive=archive_table() + archive_table()),
        ErrorKind.PARSE,
    ),
    ("no achievements table", lambda: archive_page(achievements=""), ErrorKind.PARSE),
    (
        "unknown period label",
        lambda: archive_page(
            archive=archive_table(periods=("okres 1", "okres 2", "rok"))
        ),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "non-consecutive year",
        lambda: archive_page(
            archive=archive_table(years=(("4q", "2041/2043"),) + YEARS[1:])
        ),
        ErrorKind.PARSE,
    ),
    (
        "duplicate year",
        lambda: archive_page(
            archive=archive_table(years=(YEARS[0], YEARS[0], YEARS[2]))
        ),
        ErrorKind.PARSE,
    ),
    (
        "too many years",
        lambda: archive_page(
            archive=archive_table(
                years=tuple((f"{i}q", f"{2000 + i}/{2001 + i}") for i in range(17)),
                subjects=(),
                descriptive=(),
                absences={k: (("0", "0", "0"),) * 17 for k in ABSENCES},
            )
        ),
        ErrorKind.LIMIT,
    ),
    (
        "wrong subject cell count",
        lambda: archive_page(
            archive=archive_table(subjects=(("Fixture astronomy", (("4", "5"),) * 3),))
        ),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "duplicate subject",
        lambda: archive_page(archive=archive_table(subjects=SUBJECTS * 2)),
        ErrorKind.PARSE,
    ),
    (
        "subject also descriptive",
        lambda: archive_page(
            archive=archive_table(
                descriptive=(("Fixture astronomy", ("a", "b", "c")),),
            )
        ),
        ErrorKind.PARSE,
    ),
    (
        "link in a mark cell",
        lambda: archive_page(archive=link_in_mark()),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "unknown heading",
        lambda: archive_page(
            archive=archive_table(headings=("Fixture section", "Nieobecności"))
        ),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "missing behaviour row",
        lambda: archive_page(archive=archive_table(behaviour_rows=0)),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "two behaviour rows",
        lambda: archive_page(archive=archive_table(behaviour_rows=2)),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "corrected absence spelling",
        lambda: archive_page(
            archive=archive_table(absences=corrected("nieusprawiedliwione"))
        ),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "missing absence row",
        lambda: archive_page(
            archive=archive_table(
                absences={k: v for k, v in ABSENCES.items() if k != "spóźnienia"}
            )
        ),
        ErrorKind.PARSE,
    ),
    (
        "non-integer absence",
        lambda: archive_page(
            archive=archive_table(
                absences=ABSENCES
                | {"spóźnienia": (("1", "x", "1"),) + ABSENCES["spóźnienia"][1:]}
            )
        ),
        ErrorKind.PARSE,
    ),
    (
        "non-ASCII digit absence",
        lambda: archive_page(
            archive=archive_table(
                absences=ABSENCES
                | {"spóźnienia": (("1", "٣", "1"),) + ABSENCES["spóźnienia"][1:]}
            )
        ),
        ErrorKind.PARSE,
    ),
    (
        "row after the absences",
        lambda: archive_page(
            archive=archive_table(
                body_tail='<tr><th>Fixture</th><td colspan="9">x</td></tr>'
            )
        ),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "nonempty footer",
        lambda: archive_page(
            archive=archive_table(footer='<tr><td colspan="10">Fixture</td></tr>')
        ),
        ErrorKind.PARSE,
    ),
    (
        "achievements marker row",
        lambda: archive_page(
            achievements=achievements_table(body='<tr><td colspan="4">Brak</td></tr>')
        ),
        ErrorKind.UNSUPPORTED_CAPABILITY,
    ),
    (
        "bad achievement date",
        lambda: archive_page(
            achievements=achievements_table((("2042-13-01", "4", "Fixture", "Text"),))
        ),
        ErrorKind.PARSE,
    ),
    (
        "nested table",
        lambda: archive_page(
            archive=archive_table(
                descriptive=(
                    (
                        "Fixture skills",
                        ("<table><tr><td>x</td></tr></table>", "b", "c"),
                    ),
                )
            )
        ),
        ErrorKind.PARSE,
    ),
]


@pytest.mark.parametrize(
    "build,kind", [case[1:] for case in MALFORMED], ids=[case[0] for case in MALFORMED]
)
def test_malformed_pages_fail_with_a_typed_kind(
    build: Callable[[], str], kind: ErrorKind
) -> None:
    with pytest.raises(LibrusError) as failure:
        parse(build())
    assert failure.value.kind is kind


def test_oversized_text_is_a_limit_not_a_truncation() -> None:
    long = "x" * 65537
    page = archive_page(
        archive=archive_table(descriptive=(("Fixture skills", (long, "b", "c")),))
    )
    with pytest.raises(LibrusError) as failure:
        parse(page)
    assert failure.value.kind is ErrorKind.LIMIT
