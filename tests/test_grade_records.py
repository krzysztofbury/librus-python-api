import asyncio
from datetime import date, datetime

import pytest

from librus_python_api import (
    Availability,
    RequestBudget,
    SchedulerLimits,
    TransportLimits,
)
from librus_python_api.config import GRADE_MAX_METADATA_LENGTH, GRADE_MAX_RECORDS
from librus_python_api.exceptions import (
    AccessDeniedError,
    InvalidInputError,
    LimitError,
    MaintenanceError,
    ParseError,
    SessionExpiredError,
    ThrottledError,
    UnsupportedCapabilityError,
)
from librus_python_api.grade_records import parse_grade_records
from tests.grade_records_support import GradeRecordsFixture, grade_box, grades_html
from tests.http_support import serve


@pytest.mark.parametrize("day", ["2026-09-30", "2026-09-30 (śr.)"])
def test_grade_date_is_a_civil_date_with_optional_display_weekday(day: str) -> None:
    result = parse_grade_records(grades_html(first=grade_box(day=day)).encode())
    (grade,) = result.numeric
    assert grade.day.isoformat() == "2026-09-30"
    assert dict(grade.metadata)["Data"] == day


@pytest.mark.parametrize(
    "day", ["2026-02-30", "2026-09-30 (unknown)", "2026-09-30 12:00", ""]
)
def test_invalid_or_unevidenced_grade_date_is_not_silently_skipped(day: str) -> None:
    with pytest.raises(ParseError) as caught:
        parse_grade_records(grades_html(first=grade_box(day=day)).encode())
    assert caught.value.__context__ is None


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

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2026, 9, 30), date(2026, 9, 29)),
        (date(2026, 1, 1), date(2027, 1, 2)),
        (datetime(2026, 1, 1), date(2026, 1, 1)),
        ("2026-01-01", date(2026, 1, 1)),
    ],
)
def test_invalid_window_is_rejected_before_any_login(start: date, end: date) -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            with pytest.raises(InvalidInputError):
                await service.account("student").grades_window(start, end)
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,error",
    [
        (401, SessionExpiredError),
        (302, SessionExpiredError),
        (403, AccessDeniedError),
        (429, ThrottledError),
        (503, MaintenanceError),
    ],
)
def test_grade_view_failure_never_replays_the_post_or_credentials(
    status: int, error: type[Exception]
) -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.grade_status = status
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                budget = RequestBudget(max_requests=20)
                with pytest.raises(error):
                    await client.grades(budget=budget)
                assert budget.requests_dispatched == 1
                assert len(fixture.view_posts) == 1
                assert fixture.logins == {"student": 1}
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_four_login_grade_reads_coalesce_without_merging_security_contexts() -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        aliases = ("student-a", "parent-a", "student-b", "parent-b")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(
                aliases, scheduler_limits=SchedulerLimits()
            ) as service:
                results = await asyncio.gather(
                    *(service.account(a).grades() for a in aliases for _ in range(2))
                )
                for index, alias in enumerate(aliases):
                    result = results[2 * index]
                    assert result is results[2 * index + 1]
                    assert result.identity.owner.id == alias
                    assert result.identity.student.id == "student-shared"
                    assert result.records.numeric[0].subject == f"Fixture {alias}"
                    assert (
                        await service.account(alias).grades(max_age_seconds=60)
                        is result
                    )
                assert fixture.logins == dict.fromkeys(aliases, 1)
                assert len(fixture.view_posts) == 4
                assert (
                    len(fixture.calls) == service.snapshot().requests_dispatched == 24
                )
                assert len(fixture.connections) == 4

    asyncio.run(scenario())


@pytest.mark.parametrize("max_requests", [5, 6])
def test_view_post_obeys_the_original_login_and_read_budget(max_requests: int) -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                budget = RequestBudget(max_requests=max_requests)
                if max_requests == 5:
                    with pytest.raises(LimitError):
                        await service.account("student").grades(budget=budget)
                    assert not fixture.view_posts
                else:
                    assert (
                        await service.account("student").grades(budget=budget)
                    ).records.numeric[0].raw == "4+"
                assert budget.requests_dispatched == max_requests

    asyncio.run(scenario())


def test_last_waiter_cancellation_joins_view_operation_and_releases_scheduler() -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.wait_grades = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                task = asyncio.create_task(client.grades())
                await fixture.grades_started.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert service.snapshot().active == service.snapshot().queued == 0
                fixture.wait_grades.set()
                assert (await client.grades()).records.numeric
                assert len(fixture.view_posts) == 2
                assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["wrong-type", "malformed", "parser-bytes"])
def test_grade_collection_checks_content_and_parser_byte_bounds(mode: str) -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        limits = TransportLimits()
        expected: type[ParseError | LimitError] = ParseError
        if mode == "wrong-type":
            fixture.grade_content_type = "application/json"
        elif mode == "malformed":
            fixture.grade_body = "<html>Wrong fixture page</html>"
        else:
            limits = TransportLimits(parse_max_bytes=512)
            expected = LimitError
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(transport_limits=limits) as service:
                with pytest.raises(expected):
                    await service.account("student").grades()
                assert len(fixture.view_posts) == 1

    asyncio.run(scenario())
