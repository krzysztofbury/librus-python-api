import asyncio
from datetime import date

import pytest

from librus_python_api import (
    Availability,
    GradeView,
)
from librus_python_api.config import GRADE_MAX_METADATA_LENGTH, GRADE_MAX_RECORDS
from librus_python_api.exceptions import (
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.grade_records import parse_grade_records
from tests.grade_records_support import (
    GradeRecordsFixture,
    behaviour_box,
    behaviour_points,
    behaviour_row,
    grade_box,
    grades_html,
    point_box,
    point_row,
    point_table,
)
from tests.http_support import serve


@pytest.mark.parametrize(
    "day,expected",
    [
        ("2026-09-30", "2026-09-30"),
        ("2026-09-30 (śr.)", "2026-09-30"),
        ("2026-10-04 (nd.)", "2026-10-04"),
        ("2026-10-04 (ndz.)", "2026-10-04"),
    ],
)
def test_grade_date_is_a_civil_date_with_optional_display_weekday(
    day: str, expected: str
) -> None:
    # The short Sunday label was observed in a guarded structure-only capture.
    result = parse_grade_records(grades_html(first=grade_box(day=day)).encode())
    (grade,) = result.numeric
    assert grade.day.isoformat() == expected
    assert dict(grade.metadata)["Data"] == day


@pytest.mark.parametrize(
    "day", ["2026-02-30", "2026-09-30 (unknown)", "2026-09-30 12:00", ""]
)
def test_invalid_or_unevidenced_grade_date_is_not_silently_skipped(day: str) -> None:
    with pytest.raises(ParseError) as caught:
        parse_grade_records(grades_html(first=grade_box(day=day)).encode())
    assert caught.value.__context__ is None


def _with_behaviour(first: str | None = None, second: str | None = None) -> bytes:
    return grades_html(rows=behaviour_row(first, second)).encode()


def test_behaviour_starting_points_are_not_a_malformed_grade_cell() -> None:
    records = parse_grade_records(
        _with_behaviour(behaviour_points(), behaviour_points())
    )
    assert records == parse_grade_records(
        _with_behaviour(behaviour_points("45"), behaviour_points("0"))
    )
    assert [g.subject for g in records.numeric] == ["Fixture Language"]
    assert [
        (a.semester, a.value.availability)
        for a in records.averages
        if a.subject == "Zachowanie"
    ] == [
        (1, Availability.UNAVAILABLE),
        (2, Availability.UNAVAILABLE),
        (0, Availability.AVAILABLE),
    ]


def test_behaviour_running_total_alone_is_not_a_malformed_grade_cell() -> None:
    total = '<span class="tooltip" title="Fixture points history"> {} </span>'
    records = parse_grade_records(
        _with_behaviour(total.format("120"), total.format("-15"))
    )
    assert [g.subject for g in records.numeric] == ["Fixture Language"]
    assert records.descriptive == ()
    assert records.descriptive_summaries == ()


def test_behaviour_point_entries_are_recognized_but_never_reported_as_grades() -> None:
    boxes = behaviour_box() + behaviour_box("-2", "902")
    records = parse_grade_records(_with_behaviour(behaviour_points(boxes=boxes), "-"))
    assert [g.subject for g in records.numeric] == ["Fixture Language"]
    assert records.descriptive == ()


@pytest.mark.parametrize(
    "first",
    [
        behaviour_points("many"),
        behaviour_points("1.5"),
        behaviour_points("<b>50</b>"),
        '<span class="fixture">50</span>',
        behaviour_points() + behaviour_points(),
        behaviour_points() + "Fixture text",
        behaviour_points(boxes="<b>Fixture</b>"),
        behaviour_points(boxes=grade_box()),
        behaviour_points(boxes=behaviour_box(href="fixture-link")),
        behaviour_points(boxes=behaviour_box("many")),
        behaviour_points(boxes=behaviour_box().replace("</a>", "</a><a>1</a>")),
    ],
)
def test_behaviour_points_layout_fails_closed(first: str) -> None:
    with pytest.raises(ParseError):
        parse_grade_records(_with_behaviour(first))


def test_starting_points_outside_the_behaviour_row_fail() -> None:
    body = grades_html(first=behaviour_points(boxes=behaviour_box()))
    with pytest.raises(ParseError):
        parse_grade_records(body.encode())
    body = grades_html(first=behaviour_points())
    with pytest.raises(ParseError):
        parse_grade_records(body.encode())


def test_point_table_beside_the_ordinary_table_adds_percentage_scores() -> None:
    # Point-grade schools add an "Oceny punktowe" table with its own current
    # grade columns; both tables used to make the whole read ambiguous.
    rows = point_row(second=point_box("100", "7003", "2027-02-01")) + point_row(
        point_box("100", "7004"), subject="Fixture Language", node="72"
    )
    ordinary = grades_html().replace("<td>4,25</td>", "<td>-</td>")
    records = parse_grade_records(
        ordinary.replace("</body>", point_table(rows) + "</body>").encode()
    )
    symbol, first, low, later, same_subject = records.numeric
    assert symbol.point_grade_id is None
    assert [(g.subject, g.raw, g.semester) for g in (first, low, later)] == [
        ("Fixture Science", "90", 1),
        ("Fixture Science", "44", 1),
        ("Fixture Science", "100", 2),
    ]
    assert [g.point_grade_id for g in (first, low, later)] == ["7001", "7002", "7003"]
    assert first.category == "Fixture essay (0-100)"
    assert first.day == date(2026, 10, 5)
    assert first.counts_toward_average is None
    assert ("Licz do wyniku", "TAK") in first.metadata
    assert (same_subject.subject, same_subject.raw) == ("Fixture Language", "100")
    # "Wyn." results are the school's period averages; they fill an unassigned
    # ordinary average and never add a second entry for the same period.
    assert [(a.subject, a.semester, a.value.raw) for a in records.averages] == [
        ("Fixture Language", 1, "67"),
        ("Fixture Language", 2, ""),
        ("Fixture Language", 0, "-"),
        ("Fixture Science", 1, "67"),
        ("Fixture Science", 2, "-"),
        ("Fixture Science", 0, "-"),
    ]


def test_equal_point_result_and_ordinary_average_are_one_value() -> None:
    extra = point_table(point_row(subject="Fixture Language", result="4,25"))
    records = parse_grade_records(grades_html(extra=extra).encode())
    assert [(a.semester, a.value.raw) for a in records.averages] == [
        (1, "4,25"),
        (2, ""),
        (0, "-"),
    ]


def test_point_table_alone_is_a_complete_grade_page() -> None:
    body = f"<!doctype html><html><body>{point_table(annual=False)}</body></html>"
    records = parse_grade_records(body.encode())
    assert [g.raw for g in records.numeric] == ["90", "44"]
    assert records.averages[0].value.raw == "67"


@pytest.mark.parametrize(
    "extra",
    [
        point_table() + point_table(point_row(node="73")),
        point_table(point_row() + point_row(node="73")),
        point_table().replace('<td class="center">67</td>', ""),
        point_table().replace("<td>Wyn.I</td>", "<td>Oceny bieżące</td>"),
        point_table(point_row(subject="Fixture Language")),
    ],
    ids=[
        "two-point-tables",
        "duplicate-subject",
        "short-row",
        "third-current",
        "conflicting-average",
    ],
)
def test_ambiguous_point_table_fails_closed(extra: str) -> None:
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(extra=extra).encode())


def test_numeric_symbols_descriptive_entries_and_school_averages_are_lossless() -> None:
    body = grades_html(
        first=grade_box("np", extra=""),
        second=grade_box("making progress", "2027-01-12", descriptive=True),
    )
    records = parse_grade_records(body.encode())
    (numeric,) = records.numeric
    assert numeric.raw == "np"
    assert numeric.counts_toward_average is None
    assert numeric.weight is None
    assert numeric.semester == 1
    assert numeric.teacher == "Fixture Teacher"
    assert numeric.category == "Fixture quiz"
    assert numeric.href == "fixture-link"
    (descriptive,) = records.descriptive
    assert descriptive.raw == "making progress"
    assert descriptive.semester == 2
    assert descriptive.day == date(2027, 1, 12)
    assert descriptive.comment == "Synthetic: note"
    assert [(a.semester, a.value.raw) for a in records.averages] == [
        (1, "4,25"),
        (2, ""),
        (0, "-"),
    ]
    assert all(a.value.availability == Availability.AVAILABLE for a in records.averages)
    for item in (records, numeric, descriptive, *records.averages):
        assert "Fixture" not in repr(item)
        assert "progress" not in repr(item)
        assert "2027" not in repr(item)


def test_optional_average_column_is_unavailable_not_zero() -> None:
    body = grades_html().replace('<th title="Średnia roczna">Average</th>', "")
    body = body.replace("<td>-</td><td>-</td></tr></tbody>", "<td>-</td></tr></tbody>")
    records = parse_grade_records(body.encode())
    annual = next(a for a in records.averages if a.semester == 0)
    assert annual.value.raw is None
    assert annual.value.availability == Availability.UNAVAILABLE


def test_inline_revised_grades_are_preserved_without_expanded_detail_duplicates() -> (
    None
):
    inline = "<span>" + grade_box("3") + grade_box("5") + "</span>"
    body = grades_html(first=inline).replace(
        "</tbody>",
        '<tr><td colspan="10"><table><tr><td>'
        + grade_box("5")
        + "</td></tr></table></td></tr></tbody>",
    )
    records = parse_grade_records(body.encode())
    assert [g.raw for g in records.numeric] == ["3", "5"]


@pytest.mark.parametrize("empty_marker", ["", "Brak ocen"])
def test_valid_subject_table_without_grade_entries_is_empty_not_wrong_page(
    empty_marker: str,
) -> None:
    records = parse_grade_records(grades_html(first=empty_marker).encode())
    assert records.numeric == ()
    assert records.descriptive == ()
    assert len(records.averages) == 3
    with pytest.raises(ParseError):
        parse_grade_records(b"<html>No grade contract</html>")


def test_html_comments_are_not_grade_markers() -> None:
    body = grades_html(first=grade_box("4<!-- invisible -->+")).replace(
        "<body>", "<body><!-- Original display comment -->"
    )
    records = parse_grade_records(body.encode())
    assert records.numeric[0].raw == "4+"


@pytest.mark.parametrize("count", [GRADE_MAX_RECORDS, GRADE_MAX_RECORDS + 1])
def test_grade_record_bound_is_not_partial_success(count: int) -> None:
    body = grades_html(first=grade_box(extra="") * count).encode()
    if count == GRADE_MAX_RECORDS:
        assert len(parse_grade_records(body).numeric) == count
    else:
        with pytest.raises(LimitError):
            parse_grade_records(body)


def test_unrecognized_current_grade_markup_does_not_mean_empty_success() -> None:
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(first="<span>4+</span>").encode())


@pytest.mark.parametrize(
    "extra",
    [
        "Data: 2026-09-30",
        "Licz do średniej: unknown",
        "Waga: -1",
        "Waga: 1.5",
        "Waga: 10000",
        "Malformed field",
    ],
)
def test_malformed_metadata_fails_the_whole_collection(extra: str) -> None:
    with pytest.raises(ParseError) as caught:
        parse_grade_records(grades_html(first=grade_box(extra=extra)).encode())
    assert caught.value.__context__ is None
    assert "Fixture" not in str(caught.value)


@pytest.mark.parametrize("counts", ["tak", "nie", "TAK"])
def test_count_and_weight_are_taken_only_from_explicit_metadata(counts: str) -> None:
    records = parse_grade_records(
        grades_html(
            first=grade_box(
                extra=f"Licz do średniej: {counts}<br/>Waga: 0<br/>Extra: Preserved",
            )
        ).encode()
    )
    (grade,) = records.numeric
    assert grade.counts_toward_average == (counts.casefold() == "tak")
    assert grade.weight == 0
    assert dict(grade.metadata)["Extra"] == "Preserved"


def test_metadata_length_bound_is_enforced_without_value_disclosure() -> None:
    with pytest.raises(LimitError):
        parse_grade_records(
            grades_html(
                first=grade_box(
                    extra="Comment: " + "x" * GRADE_MAX_METADATA_LENGTH,
                )
            ).encode()
        )


@pytest.mark.parametrize(
    "outside,expected",
    [
        (
            "<table><tr><td>" + grade_box() + "</td></tr></table>",
            UnsupportedCapabilityError,
        ),
        (
            "<table><tr><th><strong>Fixture semester report</strong> "
            "opublikowano: Fixture publication metadata</th></tr></table>",
            ParseError,
        ),
    ],
)
def test_unsupported_extra_grade_layouts_do_not_return_partial_success(
    outside: str,
    expected: type[Exception],
) -> None:
    with pytest.raises(expected):
        parse_grade_records(
            grades_html().replace("</body>", outside + "</body>").encode()
        )


def test_public_grade_read_and_windows_share_one_account_scoped_collection() -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.grade_body = grades_html(
            first=grade_box(day="2026-09-29") + grade_box(day="2026-09-30"),
            second=grade_box("good progress", "2026-10-01", descriptive=True),
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                result = await client.grades()
                window = await client.grades_window(
                    date(2026, 9, 30), date(2026, 10, 1), max_age_seconds=60
                )
                assert [g.day for g in window.numeric] == [date(2026, 9, 30)]
                assert [g.day for g in window.descriptive] == [date(2026, 10, 1)]
                assert window.observation is result.observation
                assert result.observation.source == "grades"
                assert result.identity.owner.id == "student"
                assert await client.grades(max_age_seconds=60) is result
                assert len(fixture.view_posts) == 1
                assert len(fixture.calls) == service.snapshot().requests_dispatched == 6
                assert await client.grades() is not result
                assert len(fixture.view_posts) == 2
                last = await client.grades_window(
                    end=date(2026, 9, 29), view=GradeView.LAST_LOGIN
                )
                assert last.view is GradeView.LAST_LOGIN and last.start is None
                assert [g.day for g in last.numeric] == [date(2026, 9, 29)]
                assert last.descriptive == ()
                assert fixture.view_posts[-1][1] == {"zmiany_logowanie": "1"}
                unfiltered = await client.grades_window(
                    view=GradeView.LAST_LOGIN, max_age_seconds=60
                )
                assert len(unfiltered.numeric) == 2
                assert len(unfiltered.descriptive) == 1
                assert unfiltered.observation == last.observation
                assert len(fixture.view_posts) == 3
                # MCP's accepted 370-day difference also remains cache-only.
                wide = await client.grades_window(
                    date(2026, 1, 1), date(2027, 1, 6), max_age_seconds=60
                )
                assert len(wide.numeric) == 2 and len(wide.descriptive) == 1
                assert len(fixture.view_posts) == 3

    asyncio.run(scenario())
