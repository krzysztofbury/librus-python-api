"""Original contracts for the school-year archive page (`/archiwum`)."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date

import pytest

from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import ArchiveCounts, ArchiveMarks
from librus_python_api.school_year_archive import parse_school_year_archive
from tests.school_year_archive_support import (
    ABSENCES,
    CANARY_NAME,
    EMPTY_ARCHIVE,
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
        archive_page(
            achievements=achievements_table(()).replace(
                '<tfoot><tr><td colspan="4"></td></tr></tfoot>', ""
            )
        ).encode()
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
    assert CANARY_NAME not in repr([asdict(item) for item in years])
    assert CANARY_NAME not in repr([asdict(item) for item in achievements])


def test_explicit_archive_empty_notice_returns_empty_records() -> None:
    assert parse(archive_page(archive="", achievements="", extra=EMPTY_ARCHIVE)) == (
        (),
        (),
    )


@pytest.mark.parametrize(
    "extra",
    [
        EMPTY_ARCHIVE * 2,
        EMPTY_ARCHIVE.replace("Brak danych", "Fixture unknown notice"),
        EMPTY_ARCHIVE.replace("warning-title", "fixture-title"),
        EMPTY_ARCHIVE.replace("warning-head", "fixture-head"),
        EMPTY_ARCHIVE.replace("information", "fixture-kind"),
        EMPTY_ARCHIVE + '<table class="decorated"><tr><td>Fixture</td></tr></table>',
    ],
)
def test_unknown_or_contradictory_empty_pages_are_not_silent_success(
    extra: str,
) -> None:
    with pytest.raises(LibrusError):
        parse(archive_page(archive="", achievements="", extra=extra))


def test_empty_notice_cannot_override_populated_archive_tables() -> None:
    with pytest.raises(LibrusError) as failure:
        parse(archive_page(extra=EMPTY_ARCHIVE))
    assert failure.value.kind is ErrorKind.PARSE


def test_rowless_chart_table_after_achievements_footer_is_ignored() -> None:
    # The upstream closing-table typo causes lxml to nest the chart container.
    # Only this geometry is reproduced; all chart/text values are invented.
    malformed = achievements_table().removesuffix("</table>") + (
        "<table><br><script>fixture_chart();</script>"
        "<div>Fixture chart label</div></table></table>"
    )
    expected = parse(archive_page())
    assert parse(archive_page(achievements=malformed)) == expected


@pytest.mark.parametrize(
    "trailer",
    [
        "<table><tr><td>Fixture data</td></tr></table>",
        "<table><div><table></table></div></table>",
        '<table class="decorated"></table>',
        "<table></table><div>Fixture later section</div>",
    ],
)
def test_chart_exception_does_not_hide_nested_data_or_unknown_geometry(
    trailer: str,
) -> None:
    table = achievements_table().removesuffix("</table>") + trailer + "</table>"
    with pytest.raises(LibrusError) as failure:
        parse(archive_page(achievements=table))
    assert failure.value.kind is ErrorKind.PARSE


def test_descriptions_and_achievements_preserve_explicit_line_breaks() -> None:
    years, achievements = parse_school_year_archive(
        archive_page(
            archive=archive_table(
                descriptive=(("Fixture skills", ("First<br>Second", "b", "c")),)
            ),
            achievements=achievements_table(
                (("2042-05-17", "4", "Fixture", "Place<br>Details"),)
            ),
        ).encode()
    )
    assert years[0].descriptive[0].text == "First\nSecond"
    assert achievements[0].text == "Place\nDetails"


@pytest.mark.parametrize(
    "before,after,kind",
    [
        (
            '<td class="center">4</td>',
            '<th class="center">4</th>',
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            '<td class="center">4</td>',
            '<td title="Extra mark metadata">4</td>',
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            "<td>okres 1</td>",
            "<td><a href='/x'>okres 1</a></td>",
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        ("<td>okres 1</td>", "<th>okres 1</th>", ErrorKind.UNSUPPORTED_CAPABILITY),
        (
            "<tr><td></td><td colspan=",
            "<tr><th></th><td colspan=",
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            "<td>Data</td>",
            "<td colspan='2'>Data</td>",
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            "<td>Data</td>",
            "<td><a href='/x'>Data</a></td>",
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            "<td>2042-05-17</td>",
            "<th>2042-05-17</th>",
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            '<td colspan="4"></td>',
            '<td colspan="3"></td>',
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            '<td colspan="4"></td>',
            '<td colspan="4"><a href="/x"></a></td>',
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        (
            '<td colspan="10"></td>',
            '<th colspan="10"></th>',
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
        ("<tfoot>", "<tfoot><tr><td colspan='10'></td></tr>", ErrorKind.PARSE),
    ],
)
def test_unrecognized_cell_geometry_and_markup_are_not_flattened(
    before: str, after: str, kind: ErrorKind
) -> None:
    page = archive_page()
    assert before in page
    with pytest.raises(LibrusError) as failure:
        parse(page.replace(before, after, 1))
    assert failure.value.kind is kind


def test_an_archive_nested_in_a_wrapper_table_is_not_a_top_level_archive() -> None:
    with pytest.raises(LibrusError) as failure:
        parse(
            archive_page(archive=f"<table><tr><td>{archive_table()}</td></tr></table>")
        )
    assert failure.value.kind is ErrorKind.PARSE


def test_class_name_field_limit_is_not_reduced_by_the_year_header_prefix() -> None:
    years, _ = parse_school_year_archive(
        archive_page(
            archive=archive_table(years=(("x" * 1024, "2041/2042"), *YEARS[1:]))
        ).encode()
    )
    assert years[0].class_name == "x" * 1024


def corrected(label: str) -> dict[str, tuple[tuple[str, str, str], ...]]:
    return {(label if k == "nieusprawiedlione" else k): v for k, v in ABSENCES.items()}


def link_in_mark() -> str:
    marks = (('<a href="/x">5</a>', "5", "5"),) + SUBJECTS[0][1][1:]
    return archive_table(subjects=(("Fixture astronomy", marks),))


MALFORMED: list[tuple[str, Callable[[], str], ErrorKind]] = [
    (
        "duplicate absence row",
        lambda: archive_page(
            archive=archive_table(
                body_tail="<tr><th>spóźnienia</th>" + "<td>0</td>" * 9 + "</tr>"
            )
        ),
        ErrorKind.PARSE,
    ),
    (
        "no footer",
        lambda: archive_page(archive=archive_table(footer="")),
        ErrorKind.PARSE,
    ),
    (
        "two achievement tables",
        lambda: archive_page(achievements=achievements_table() * 2),
        ErrorKind.PARSE,
    ),
    (
        "row after footer",
        lambda: archive_page(
            archive=archive_table(
                footer='<tr><td colspan="10"></td></tr><tr><td>Extra</td></tr>'
            )
        ),
        ErrorKind.PARSE,
    ),
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


@pytest.mark.parametrize("count", [16, 17])
def test_year_count_boundary(count: int) -> None:
    page = archive_page(
        archive=archive_table(
            years=tuple((f"{i}q", f"{2000 + i}/{2001 + i}") for i in range(count)),
            subjects=(),
            descriptive=(),
            absences={label: (("0", "0", "0"),) * count for label in ABSENCES},
        )
    )
    if count == 17:
        with pytest.raises(LibrusError) as failure:
            parse(page)
        assert failure.value.kind is ErrorKind.LIMIT
    else:
        years, _ = parse_school_year_archive(page.encode())
        assert len(years) == 16
        assert years[-1].school_year == "2015/2016"


@pytest.mark.parametrize(
    "family,maximum", [("subjects", 128), ("descriptive", 32), ("achievements", 256)]
)
@pytest.mark.parametrize("overflow", [False, True])
def test_collection_count_boundaries(family: str, maximum: int, overflow: bool) -> None:
    count = maximum + overflow
    if family == "subjects":
        page = archive_page(
            archive=archive_table(
                subjects=tuple(
                    (f"Fixture subject {i}", (("4", "5", "6"),) * 3)
                    for i in range(count)
                )
            )
        )
    elif family == "descriptive":
        page = archive_page(
            archive=archive_table(
                descriptive=tuple(
                    (f"Fixture description {i}", ("a", "b", "c")) for i in range(count)
                )
            )
        )
    else:
        page = archive_page(
            achievements=achievements_table(
                tuple(
                    ("2042-05-17", "4q", "Fixture", f"Synthetic {i}")
                    for i in range(count)
                )
            )
        )
    if overflow:
        with pytest.raises(LibrusError) as failure:
            parse(page)
        assert failure.value.kind is ErrorKind.LIMIT
    else:
        years, achievements = parse_school_year_archive(page.encode())
        items = achievements if family == "achievements" else getattr(years[0], family)
        assert len(items) == maximum


def test_total_text_budget_is_shared_across_both_tables() -> None:
    page = archive_page(
        archive=archive_table(descriptive=(("Fixture", ("x" * 60000,) * 3),)),
        achievements=achievements_table(
            (
                ("2042-05-17", "4q", "Fixture", "x" * 60000),
                ("2042-05-18", "4q", "Fixture", "x" * 60000),
            )
        ),
    )
    with pytest.raises(LibrusError) as failure:
        parse(page)
    assert failure.value.kind is ErrorKind.LIMIT


@pytest.mark.parametrize("field", ["mark", "class", "text", "count"])
@pytest.mark.parametrize("overflow", [False, True])
def test_scalar_boundaries(field: str, overflow: bool) -> None:
    if field == "class":
        archive = archive_table(
            years=(("x" * (1024 + overflow), "2041/2042"), *YEARS[1:])
        )
    elif field == "mark":
        archive = archive_table(
            subjects=(("Fixture", (("x" * (1024 + overflow), "", "-"),) * 3),)
        )
    elif field == "text":
        archive = archive_table(
            descriptive=(("Fixture", ("x" * (65536 + overflow), "", "")),)
        )
    else:
        archive = archive_table(
            absences=ABSENCES | {"spóźnienia": (("9" * (6 + overflow), "0", "1"),) * 3}
        )
    if overflow:
        with pytest.raises(LibrusError) as failure:
            parse(archive_page(archive=archive))
        assert failure.value.kind is (
            ErrorKind.PARSE if field == "count" else ErrorKind.LIMIT
        )
    else:
        years, _ = parse_school_year_archive(archive_page(archive=archive).encode())
        assert len(years) == 3
        if field == "count":
            assert years[0].absences.late == ArchiveCounts(999999, 0, 1)
