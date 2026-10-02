"""Owning row/pagination integrity and public bounded continuation guarantees."""

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import cast

import pytest

from librus_python_api import CompletedLesson, CompletedLessonsCursor, RequestBudget
from librus_python_api.completed_lessons import parse_completed_lessons
from librus_python_api.exceptions import (
    AccessDeniedError,
    ClosedError,
    InvalidInputError,
    LimitError,
    MaintenanceError,
    OperationTimeoutError,
    ParseError,
    SessionExpiredError,
    ThrottledError,
    UnsupportedCapabilityError,
)
from tests.completed_lessons_support import (
    CompletedLessonsFixture,
    lesson_row,
    lessons_html,
)
from tests.http_support import serve

START, END = date(2026, 10, 1), date(2026, 10, 31)


def parse(body: str, page: int = 0) -> tuple[tuple[CompletedLesson, ...], int, str]:
    return parse_completed_lessons(body.encode(), START, END, page)


def test_fields_rendered_boundaries_reference_and_one_based_page_metadata() -> None:
    items, count, fingerprint = parse(
        lessons_html(1, 3, lesson_row("Fixture<br>topic")), 1
    )
    item = items[0]
    assert count == 3 and len(fingerprint) == 64
    assert item.day == date(2026, 10, 2) and item.raw_day == "2026-10-02"
    assert item.weekday == "pt." and item.lesson_number == 2
    assert item.subject == "Fixture Biology" and item.teacher == "Fixture Teacher"
    assert item.subject_teacher_text == "Fixture Biology, Fixture Teacher"
    assert item.topic == "Fixture\ntopic" and item.z_value == "Fixture Z"
    assert item.attendance_symbol == "nb" and item.attendance_detail_id == "123"
    assert "Fixture" not in repr(item) and "2026" not in repr(item)


def test_optional_teacher_number_and_link_do_not_invent_values() -> None:
    body = lessons_html(rows=lesson_row(number="-")).replace(
        "Fixture Biology, Fixture Teacher",
        "Fixture Biology",
    )
    start = body.index("<a onclick=")
    end = body.index("</a>", start) + 4
    item = parse(body[:start] + "nb" + body[end:])[0][0]
    assert item.teacher is None and item.lesson_number is None
    assert item.raw_lesson_number == "-" and item.attendance_detail_id is None
    assert parse(body.replace("2026-10-02", "02-10-2026"))[0][0].day == date(
        2026, 10, 2
    )


def test_explicit_empty_and_single_page_without_pagination() -> None:
    assert (
        parse('<html><p class="msgEmptyTable">Fixture no lessons</p></html>')[0] == ()
    )
    body = lessons_html()
    start, end = body.index('<div class="pagination">'), body.index("</div>") + 6
    assert parse(body[:start] + body[end:])[1] == 1
    with pytest.raises(ParseError):
        parse(body[:start] + body[end:], 1)


@pytest.mark.parametrize(
    "body",
    [
        lessons_html(),
        '<html><body><p class="msgEmptyTable">Fixture empty</p></body></html>',
    ],
)
def test_comments_do_not_change_recognized_page_semantics(body: str) -> None:
    assert parse(body.replace("<body>", "<body><!-- Fixture comment -->")) == parse(
        body
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ("Strona 1 z 1", "Strona 2 z 2"),
        ("Strona 1 z 1", "Strona 1 z 0"),
        ("Strona 1 z 1", "Fixture unknown pagination"),
        ("2026-10-02", "2026-02-30"),
        ("2026-10-02", "2026-09-30"),
        ("2026-10-02", "02.10.2026"),
        ("<td>2</td>", "<td>Fixture period</td>"),
        ("<td>Fixture Z</td>", ""),
        ("<td>Fixture Z</td>", '<td rowspan="2">Fixture Z</td>'),
        ("<td>Fixture topic</td>", "<td><script>Fixture unsafe()</script></td>"),
        ("/przegladaj_nb/szczegoly/123", "https://example.invalid/123"),
        ("/przegladaj_nb/szczegoly/123", "/przegladaj_nb/szczegoly/%31"),
        ("Fixture Z", "<table><tr><td>Fixture nested</td></tr></table>"),
        ("</body>", '<p class="msgEmptyTable">Fixture empty</p></body>'),
        ("</body>", '<table class="decorated"></table></body>'),
        ("</body>", '<div class="pagination"><span>1 z 1</span></div></body>'),
    ],
)
def test_malformed_rows_and_metadata_never_become_partial(
    before: str, after: str
) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse(lessons_html().replace(before, after))


@pytest.mark.parametrize(
    "body",
    [
        "<html></html>",
        "<html><body><!-- Fixture comment -->Fixture unknown</body></html>",
        lessons_html(rows=""),
        '<html><p class="msgEmptyTable"></p></html>',
        '<html><div class="pagination"><span>1 z 2</span></div>'
        '<p class="msgEmptyTable">Fixture empty</p></html>',
        '<html><div class="warning-content">Fixture unknown notice</div>'
        '<p class="msgEmptyTable">Fixture empty</p></html>',
    ],
)
def test_unknown_or_contradictory_empty_layout_fails(body: str) -> None:
    with pytest.raises(ParseError):
        parse(body)


@pytest.mark.parametrize(
    "bound,value",
    [
        ("COMPLETED_LESSONS_MAX_PAGE_ITEMS", 0),
        ("COMPLETED_LESSONS_MAX_PAGE_COUNT", 0),
        ("SCHOOL_MAX_FIELD_LENGTH", 2),
        ("SCHOOL_MAX_CONTENT_LENGTH", 2),
        ("SCHOOL_MAX_TOTAL_TEXT_LENGTH", 2),
    ],
)
def test_parser_bounds_never_truncate(
    bound: str, value: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.completed_lessons." + bound, value)
    with pytest.raises(LimitError):
        parse(lessons_html())


def test_actual_page_row_and_page_count_boundaries() -> None:
    body = lessons_html(999, 1000, lesson_row() * 256)
    items, count, _ = parse(body, 999)
    assert len(items) == 256 and count == 1000
    with pytest.raises(LimitError):
        parse(lessons_html(rows=lesson_row() * 257))
    with pytest.raises(LimitError):
        parse(lessons_html(0, 1001))


def test_inclusive_date_window_boundary_and_page_selection_cache_key() -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                result = await client.completed_lessons_page(
                    START, START + timedelta(days=370)
                )
                assert result.end == START + timedelta(days=370)
                assert len(fixture.forms) == 1
                with pytest.raises(InvalidInputError):
                    await client.completed_lessons_page(
                        START, START + timedelta(days=371)
                    )
                await client.completed_lessons_page(START, END, max_age_seconds=60)
                assert len(fixture.forms) == 2

    asyncio.run(scenario())


def test_batch_limits_resume_midpage_and_complete_without_extra_count_requests() -> (
    None
):
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.completed_lessons(START, END, limit=1)
                assert [i.topic for i in first.items] == ["Fixture first"]
                assert first.pages_fetched == 1 and first.next_cursor is not None
                assert (first.next_cursor.page, first.next_cursor.offset) == (0, 1)
                second = await client.completed_lessons(
                    START, END, cursor=first.next_cursor, max_pages=1
                )
                assert [i.topic for i in second.items] == ["Fixture second"]
                assert second.next_cursor is not None
                assert (second.next_cursor.page, second.next_cursor.offset) == (1, 0)
                last = await client.completed_lessons(
                    START, END, cursor=second.next_cursor
                )
                assert [i.topic for i in last.items] == ["Fixture third"]
                assert last.next_cursor is None and last.pages_fetched == 1
                assert [f[1]["numer_strony1001"] for f in fixture.forms] == [
                    "0",
                    "0",
                    "1",
                ]
                assert fixture.forms[0][1]["data1"] == START.isoformat()
                assert fixture.forms[0][1]["data2"] == END.isoformat()
                assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_page_batch_coalescing_cache_and_four_login_isolation() -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        aliases = ("student-a", "parent-a", "student-b", "parent-b")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(aliases) as service:

                async def read(alias: str) -> None:
                    client = service.account(alias)
                    results = await asyncio.gather(
                        *(client.completed_lessons(START, END) for _ in range(2))
                    )
                    assert results[0] is results[1]
                    assert [i.topic for i in results[0].items] == [
                        "Fixture first",
                        "Fixture second",
                        "Fixture third",
                    ]
                    assert (
                        results[0].pages_fetched == 2 and results[0].next_cursor is None
                    )
                    assert (
                        await client.completed_lessons(START, END, max_age_seconds=60)
                        is results[0]
                    )
                    page = await client.completed_lessons_page(START, END, page=1)
                    assert page.page == 1 and page.page_count == 2
                    assert (
                        await client.completed_lessons_page(
                            START, END, page=1, max_age_seconds=60
                        )
                        is page
                    )

                await asyncio.gather(*(read(alias) for alias in aliases))
                assert len(fixture.forms) == 12
                assert fixture.logins == dict.fromkeys(aliases, 1)
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change", ["changed_row", "count_drift", "repeated", "clamped"]
)
def test_resume_drift_and_duplicate_pages_fail_without_silent_results(
    change: str,
) -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.completed_lessons(
                    START, END, limit=1 if change == "changed_row" else 2
                )
                assert first.next_cursor is not None
                page = first.next_cursor.page
                if change == "changed_row":
                    fixture.bodies[page] = fixture.bodies[page].replace(
                        "Fixture second", "Fixture changed"
                    )
                elif change == "count_drift":
                    fixture.bodies[page] = fixture.bodies[page].replace("z 2", "z 3")
                elif change == "clamped":
                    fixture.bodies[page] = fixture.bodies[0]
                else:
                    fixture.bodies[page] = fixture.bodies[0].replace(
                        "Strona 1", "Strona 2"
                    )
                with pytest.raises(ParseError):
                    await client.completed_lessons(START, END, cursor=first.next_cursor)

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
def test_failed_second_page_never_replays_or_returns_first_page(
    status: int, error: type[Exception]
) -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        fixture.status[1] = status
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                with pytest.raises(error):
                    await service.account("student").completed_lessons(START, END)
                assert len(fixture.forms) == 2 and fixture.logins == {"student": 1}
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_invalid_inputs_and_foreign_cursors_fail_before_login() -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        fixture.origin = "http://localhost:8080"
        cursor = CompletedLessonsCursor("student", START, END, 0, 1, 2, "a" * 64)
        bad = [
            replace(cursor, account="parent"),
            replace(cursor, start=date(2026, 9, 1)),
            replace(cursor, page=True),
            replace(cursor, offset=256),
            replace(cursor, page_count=0),
            replace(cursor, fingerprint="private"),
            replace(cursor, offset=0),
            "arbitrary",
        ]
        async with fixture.service() as service:
            client = service.account("student")
            for value in bad:
                with pytest.raises(InvalidInputError):
                    await client.completed_lessons(
                        START, END, cursor=cast(CompletedLessonsCursor, value)
                    )
            for start, end in [
                (END, START),
                (datetime(2026, 10, 1), END),
                (date(2026, 1, 1), date(2027, 1, 8)),
            ]:
                with pytest.raises(InvalidInputError):
                    await client.completed_lessons(start, end)
            for pages, limit in [
                (0, 1),
                (9, 1),
                (True, 1),
                (1, 0),
                (1, 257),
                (1, True),
            ]:
                with pytest.raises(InvalidInputError):
                    await client.completed_lessons(
                        START, END, max_pages=pages, limit=limit
                    )
            for page in [True, -1, 1000]:
                with pytest.raises(InvalidInputError):
                    await client.completed_lessons_page(START, END, page=page)
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


def test_original_budget_spans_authentication_and_all_pages() -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                budget = RequestBudget(max_requests=6)
                with pytest.raises(LimitError):
                    await service.account("student").completed_lessons(
                        START, END, budget=budget
                    )
                assert budget.requests_dispatched == 6 and len(fixture.forms) == 1
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_last_waiter_cancellation_on_second_page_is_joined() -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        fixture.wait_page = 1
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                task = asyncio.create_task(
                    service.account("student").completed_lessons(START, END)
                )
                try:
                    await asyncio.wait_for(fixture.started.wait(), timeout=2)
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert service.snapshot().active == service.snapshot().queued == 0
                finally:
                    fixture.wait.set()

    asyncio.run(scenario())


def test_maximum_page_and_item_bounds_produce_exact_continuations() -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        fixture.bodies = {
            page: lessons_html(
                page, 3, "".join(lesson_row(f"Fixture {page}:{i}") for i in range(100))
            )
            for page in range(3)
        }
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                result = await client.completed_lessons(
                    START, END, max_pages=8, limit=256
                )
                assert len(result.items) == 256 and result.pages_fetched == 3
                cursor = result.next_cursor
                assert cursor is not None and (cursor.page, cursor.offset) == (2, 56)
                last = await client.completed_lessons(START, END, cursor=cursor)
                assert len(last.items) == 44 and last.next_cursor is None
                assert last.items[0].topic == "Fixture 2:56"
                fixture.bodies = {
                    p: lessons_html(p, 12, lesson_row(f"Fixture {p}"))
                    for p in range(12)
                }
                bounded = await client.completed_lessons(
                    START, END, max_pages=8, limit=256
                )
                assert bounded.pages_fetched == 8 and len(bounded.items) == 8
                assert bounded.next_cursor is not None and bounded.next_cursor.page == 8

    asyncio.run(scenario())


def test_malformed_page_is_not_cached_and_empty_batch_is_explicit() -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        fixture.bodies[0] = "<html>Fixture unknown</html>"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                with pytest.raises(ParseError):
                    await client.completed_lessons(START, END)
                fixture.bodies[0] = (
                    '<html><p class="msgEmptyTable">Fixture no lessons</p></html>'
                )
                result = await client.completed_lessons(START, END, max_age_seconds=60)
                assert result.items == () and result.next_cursor is None
                assert result.pages_fetched == 1 and len(fixture.forms) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["deadline", "body_bytes", "close"])
def test_second_page_whole_operation_cleanup(kind: str) -> None:
    async def scenario() -> None:
        fixture = CompletedLessonsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                if kind == "body_bytes":
                    budget = RequestBudget(
                        max_response_bytes=len(fixture.bodies[0].encode()) + 10
                    )
                    with pytest.raises(LimitError):
                        await client.completed_lessons(START, END, budget=budget)
                else:
                    fixture.wait_page = 1
                    budget = RequestBudget(
                        timeout_seconds=0.2 if kind == "deadline" else 10
                    )
                    task = asyncio.create_task(
                        client.completed_lessons(START, END, budget=budget)
                    )
                    try:
                        await asyncio.wait_for(fixture.started.wait(), timeout=2)
                        if kind == "close":
                            await service.aclose()
                            with pytest.raises(ClosedError):
                                await task
                        else:
                            with pytest.raises(OperationTimeoutError):
                                await task
                    finally:
                        fixture.wait.set()
                assert len(fixture.forms) == 2
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())
