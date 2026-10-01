"""Calendar/homework integrity and owning service security/wire guarantees."""

import asyncio
from datetime import date, datetime, time
from typing import Literal, cast

import pytest

from librus_python_api import Agenda, Homework, RequestBudget, SchoolReference
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
from librus_python_api.school_reads import (
    parse_agenda,
    parse_homework,
    parse_school_detail,
)
from tests.http_support import serve
from tests.school_reads_support import (
    SchoolReadsFixture,
    agenda_html,
    detail_html,
    homework_html,
)


@pytest.mark.parametrize(
    "year,month,count", [(2026, 10, 31), (2026, 9, 30), (2028, 2, 29), (2026, 2, 28)]
)
def test_complete_month_retains_empty_days_events_metadata_and_references(
    year: int, month: int, count: int
) -> None:
    days = parse_agenda(agenda_html(year, month).encode(), year, month, "fixture")
    assert len(days) == count
    assert [day.day for day in days] == [
        date(year, month, i) for i in range(1, count + 1)
    ]
    event = days[1].events[0]
    assert event.title == "Fixture test"
    assert event.subject == "Fixture Biology"
    assert event.lesson_number == 2 and event.at_time is None
    assert (
        event.text == "Lekcja: 2\nFixture Biology\nFixture test\nFixture ancillary text"
    )
    assert dict(event.metadata)["Opis"] == "Fixture: description"
    assert event.reference == SchoolReference("agenda", "123", "fixture")
    assert all(not day.events for day in days if day.day.day != 2)
    assert "Fixture" not in repr(event)


def test_subjectless_nonlesson_and_metadata_notes_do_not_invent_defaults() -> None:
    cell = (
        '<td title="Fixture flag&lt;br&gt;Opis: Fixture note">'
        "09:30<br>Fixture meeting</td>"
    )
    event = parse_agenda(agenda_html(cell=cell).encode(), 2026, 10, "fixture")[
        1
    ].events[0]
    assert event.title == "Fixture meeting"
    assert event.subject is None
    assert event.lesson_number is None
    assert event.reference is None
    assert event.at_time == time(9, 30)
    assert event.metadata_notes == ("Fixture flag",)
    assert dict(event.metadata) == {"Opis": "Fixture note"}
    assert all(
        not day.events
        for day in parse_agenda(agenda_html(cell="").encode(), 2026, 10, "fixture")
    )


def test_tooltip_full_text_retains_intermediate_notes_and_label_spacing() -> None:
    cell = (
        '<td title="Nauczyciel : Fixture Teacher&lt;br /&gt;'
        'Fixture intermediate note&lt;br /&gt;Opis: Fixture detail">'
        "Fixture meeting</td>"
    )
    event = parse_agenda(agenda_html(cell=cell).encode(), 2026, 10, "fixture")[
        1
    ].events[0]
    assert event.metadata_text == (
        "Nauczyciel : Fixture Teacher\nFixture intermediate note\nOpis: Fixture detail"
    )
    assert event.metadata == (
        ("Nauczyciel", "Fixture Teacher"),
        ("Opis", "Fixture detail"),
    )
    assert event.metadata_notes == ("Fixture intermediate note",)


def test_subjectless_multiline_title_is_not_replaced_with_its_note() -> None:
    event = parse_agenda(
        agenda_html(
            cell="<td>Fixture school closure<br>Fixture explanation</td>"
        ).encode(),
        2026,
        10,
        "fixture",
    )[1].events[0]
    assert event.title == "Fixture school closure"
    assert event.lesson_number is None and event.subject is None


def test_inline_subject_header_does_not_hide_lesson_number_or_punctuation() -> None:
    cell = (
        "<td>Lekcja nr: 4, <span>Fixture Biology</span><br>Fixture quiz, revision</td>"
    )
    event = parse_agenda(agenda_html(cell=cell).encode(), 2026, 10, "fixture")[
        1
    ].events[0]
    assert event.lesson_number == 4
    assert event.title == "Fixture quiz, revision"
    assert event.subject == "Fixture Biology"


@pytest.mark.parametrize(
    "before,after",
    [
        (">31</div>", ">32</div>"),
        (">31</div>", ">30</div>"),
        ("kalendarz-numer-dnia", "unknown-number"),
        ("/terminarz/szczegoly/123", "/terminarz/dodane_od_ostatniego_logowania"),
        ("/terminarz/szczegoly/123", "https://example.invalid/123"),
        (
            "<span>Fixture Biology</span>",
            "<span>Fixture Biology</span><span>Fixture ambiguous</span>",
        ),
        ("<td title=", '<td colspan="2" title='),
        (
            "Fixture ancillary text",
            "<table><tr><td>Fixture nested event</td></tr></table>",
        ),
        ("Nauczyciel: Fixture Teacher", "Opis: Fixture duplicate"),
    ],
)
def test_malformed_calendar_never_becomes_partial(before: str, after: str) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_agenda(agenda_html().replace(before, after).encode(), 2026, 10, "fixture")


def test_homework_preserves_split_dates_extra_cells_and_reference() -> None:
    items = parse_homework(homework_html(extra="Fixture status").encode(), "fixture")
    item = items[0]
    assert (item.lesson, item.teacher, item.subject, item.category) == (
        "Fixture topic",
        "Fixture Teacher",
        "Fixture Biology",
        "Fixture practice",
    )
    assert item.assigned.day == date(2026, 9, 1) and item.assigned.clock == time(8, 15)
    assert item.due.day == date(2026, 10, 3) and item.due.clock == time(12, 30)
    assert item.due.raw_day == "2026-10-03" and item.due.raw_clock == "12:30"
    assert item.extra_cells == ("Fixture status",)
    assert item.reference == SchoolReference("homework", "456", "fixture")
    assert "Fixture" not in repr(item)


def test_explicit_homework_empty_and_missing_clock_are_not_fabricated_data() -> None:
    assert (
        parse_homework(
            b'<html><p class="msgEmptyTable">Fixture no assignments</p></html>',
            "fixture",
        )
        == ()
    )
    item = parse_homework(
        homework_html().replace("08:15", "").replace("2026-10-03", "-").encode(),
        "fixture",
    )[0]
    assert item.assigned.clock is None and item.due.day is None
    for body in (
        "<html></html>",
        "<html><p>Fixture no assignments</p></html>",
        homework_html().replace(
            "</body>", '<p class="msgEmptyTable">Fixture no assignments</p></body>'
        ),
    ):
        with pytest.raises(ParseError):
            parse_homework(body.encode(), "fixture")


@pytest.mark.parametrize(
    "before,after",
    [
        ("2026-09-01", "2026-02-30"),
        ("08:15", "25:01"),
        ("2026-09-01", "01.09.2026"),
        ("<td>Fixture topic</td>", ""),
        ("<td>Fixture Teacher</td>", '<td rowspan="2">Fixture Teacher</td>'),
        ("/moje_zadania/podglad/456", "/moje_zadania/wyslij/456"),
        ("/moje_zadania/podglad/456", "/moje_zadania/podglad/%34"),
    ],
)
def test_invalid_homework_fails_not_silently_dropped(before: str, after: str) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_homework(homework_html().replace(before, after).encode(), "fixture")


@pytest.mark.parametrize("kind", ["agenda", "homework"])
def test_detail_fields_preserve_long_text_empty_values_header_and_notes(
    kind: str,
) -> None:
    title, fields, notes = parse_school_detail(
        detail_html(kind, "Fixture<br>" + ("x" * 2048)).encode()
    )
    assert title == "Fixture heading"
    assert dict(fields) == {
        "Opis:": "Fixture\n" + "x" * 2048,
        "Fixture unknown label": "",
    }
    assert notes == ("Fixture separate note",)


@pytest.mark.parametrize(
    "before,after",
    [
        ("container-background", "unknown-container"),
        ("Fixture unknown label", "Opis"),
        ("Fixture unknown label", "Opis :"),
        (
            "<td>Fixture<br>complete content</td>",
            '<td colspan="2">Fixture invalid</td>',
        ),
        ("Fixture<br>complete content", "<script>Fixture unsupported()</script>"),
    ],
)
def test_unsafe_or_ambiguous_details_fail(before: str, after: str) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_school_detail(detail_html().replace(before, after).encode())


@pytest.mark.parametrize(
    "bound,value,parser,body",
    [
        ("SCHOOL_MAX_ITEMS", 0, "agenda", agenda_html()),
        ("SCHOOL_MAX_ITEMS", 0, "homework", homework_html()),
        ("SCHOOL_MAX_CONTENT_LENGTH", 10, "detail", detail_html()),
        ("SCHOOL_MAX_DETAIL_FIELDS", 1, "detail", detail_html()),
        ("SCHOOL_MAX_TOTAL_TEXT_LENGTH", 10, "agenda", agenda_html()),
        ("SCHOOL_MAX_TOTAL_TEXT_LENGTH", 10, "homework", homework_html()),
    ],
)
def test_explicit_bounds_fail_without_truncation(
    bound: str, value: int, parser: str, body: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.school_reads." + bound, value)
    with pytest.raises(LimitError):
        if parser == "agenda":
            parse_agenda(body.encode(), 2026, 10, "fixture")
        elif parser == "homework":
            parse_homework(body.encode(), "fixture")
        else:
            parse_school_detail(body.encode())


def test_four_logins_collections_details_and_selection_cache_isolation() -> None:
    async def scenario() -> None:
        fixture = SchoolReadsFixture()
        aliases = ("student-a", "parent-a", "student-b", "parent-b")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(aliases) as service:
                for kind in ("agenda", "homework"):

                    async def read(alias: str, family: str = kind) -> Agenda | Homework:
                        client = service.account(alias)
                        return (
                            await client.agenda(2026, 10)
                            if family == "agenda"
                            else await client.homework(
                                date(2026, 9, 1), date(2026, 10, 31)
                            )
                        )

                    results = await asyncio.gather(
                        *(read(alias) for alias in aliases for _ in range(2))
                    )
                    for index, alias in enumerate(aliases):
                        result = results[index * 2]
                        assert result is results[index * 2 + 1]
                        reference = (
                            result.days[1].events[0].reference
                            if isinstance(result, Agenda)
                            else result.items[0].reference
                        )
                        assert reference is not None and reference.account == alias
                        client = service.account(alias)
                        detail = (
                            await client.agenda_detail(reference)
                            if kind == "agenda"
                            else await client.homework_detail(reference)
                        )
                        assert (
                            detail.reference == reference
                            and dict(detail.fields)["Opis:"]
                            == "Fixture\ncomplete content"
                        )
                        cached = (
                            await client.agenda(2026, 10, max_age_seconds=60)
                            if kind == "agenda"
                            else await client.homework(
                                date(2026, 9, 1), date(2026, 10, 31), max_age_seconds=60
                            )
                        )
                        assert cached is result
                assert len(fixture.forms) == 8 and len(fixture.detail_gets) == 8
                assert fixture.logins == {alias: 1 for alias in aliases}
                await service.account(aliases[0]).agenda(2026, 9)
                await service.account(aliases[0]).homework(
                    date(2026, 9, 2), date(2026, 10, 31)
                )
                assert len(fixture.forms) == 10
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["agenda", "homework"])
def test_invalid_selection_and_foreign_reference_rejected_before_login(
    kind: Literal["agenda", "homework"],
) -> None:
    async def scenario() -> None:
        fixture = SchoolReadsFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            client = service.account("student")
            args = (
                [(True, 10), (2026, 0), (2000, 1), ("2026", 10)]
                if kind == "agenda"
                else [
                    (date(2026, 10, 2), date(2026, 10, 1)),
                    (datetime(2026, 10, 1), date(2026, 10, 3)),
                    (date(2026, 1, 1), date(2027, 1, 8)),
                ]
            )
            for first, last in args:
                with pytest.raises(InvalidInputError):
                    if kind == "agenda":
                        await client.agenda(cast(int, first), cast(int, last))
                    else:
                        await client.homework(cast(date, first), cast(date, last))
            for ref in (
                SchoolReference(kind, "123", "parent"),
                SchoolReference(
                    "homework" if kind == "agenda" else "agenda", "123", "student"
                ),
                SchoolReference(kind, "../123", "student"),
                "123",
            ):
                with pytest.raises(InvalidInputError):
                    if kind == "agenda":
                        await client.agenda_detail(cast(SchoolReference, ref))
                    else:
                        await client.homework_detail(cast(SchoolReference, ref))
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["agenda", "homework"])
@pytest.mark.parametrize(
    "status,expected",
    [
        (401, SessionExpiredError),
        (302, SessionExpiredError),
        (403, AccessDeniedError),
        (429, ThrottledError),
        (503, MaintenanceError),
    ],
)
def test_selection_never_replays(
    kind: str, status: int, expected: type[Exception]
) -> None:
    async def scenario() -> None:
        fixture = SchoolReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                fixture.status[kind] = status
                with pytest.raises(expected):
                    if kind == "agenda":
                        await client.agenda(2026, 10)
                    else:
                        await client.homework(date(2026, 9, 1), date(2026, 10, 31))
                assert len(fixture.forms) == 1 and fixture.logins == {"student": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["agenda", "homework"])
def test_detail_recovery_is_safe_bounded_and_cached(
    kind: Literal["agenda", "homework"],
) -> None:
    async def scenario() -> None:
        fixture = SchoolReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                reference = SchoolReference(kind, "123", "student")
                fixture.detail_expiry = 1
                detail = (
                    await client.agenda_detail(reference)
                    if kind == "agenda"
                    else await client.homework_detail(reference)
                )
                assert detail.fields
                cached = (
                    await client.agenda_detail(reference, max_age_seconds=60)
                    if kind == "agenda"
                    else await client.homework_detail(reference, max_age_seconds=60)
                )
                assert cached is detail
                assert len(fixture.detail_gets) == 2 and fixture.logins == {
                    "student": 2
                }

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["agenda", "homework"])
def test_forms_original_budget_and_last_waiter_cancellation(kind: str) -> None:
    from librus_python_api.models import (
        AgendaSelection,
        HomeworkSelection,
        LoginSubmission,
    )

    async def scenario() -> None:
        fixture = SchoolReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                before = service.snapshot().requests_dispatched
                for form in (
                    None,
                    LoginSubmission(
                        client._credentials.login, client._credentials.password
                    ),
                    HomeworkSelection(date(2026, 9, 1), date(2026, 10, 31))
                    if kind == "agenda"
                    else AgendaSelection(2026, 10),
                ):
                    with pytest.raises(InvalidInputError):
                        await client._transport.request(
                            kind, RequestBudget(), form=form
                        )
                assert service.snapshot().requests_dispatched == before
                fixture.wait = asyncio.Event()
                task = asyncio.create_task(
                    client.agenda(2026, 10)
                    if kind == "agenda"
                    else client.homework(date(2026, 9, 1), date(2026, 10, 31))
                )
                try:
                    await asyncio.wait_for(fixture.started.wait(), timeout=2)
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert service.snapshot().active == service.snapshot().queued == 0
                finally:
                    fixture.wait.set()
            async with fixture.service() as service:
                budget = RequestBudget(max_requests=5)
                with pytest.raises(LimitError):
                    if kind == "agenda":
                        await service.account("student").agenda(2026, 10, budget=budget)
                    else:
                        await service.account("student").homework(
                            date(2026, 9, 1), date(2026, 10, 31), budget=budget
                        )
                assert budget.requests_dispatched == 5

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["agenda", "homework"])
def test_malformed_collection_is_not_cached_or_returned_as_empty(kind: str) -> None:
    async def scenario() -> None:
        fixture = SchoolReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                fixture.bodies[kind] = (
                    "<html><body>Fixture missing collection</body></html>"
                )
                with pytest.raises(ParseError):
                    if kind == "agenda":
                        await client.agenda(2026, 10)
                    else:
                        await client.homework(date(2026, 9, 1), date(2026, 10, 31))
                del fixture.bodies[kind]
                result = (
                    await client.agenda(2026, 10, max_age_seconds=60)
                    if kind == "agenda"
                    else await client.homework(
                        date(2026, 9, 1), date(2026, 10, 31), max_age_seconds=60
                    )
                )
                assert (
                    result.days[1].events
                    if isinstance(result, Agenda)
                    else result.items
                )
                assert len(fixture.forms) == 2
                assert fixture.logins == {"student": 1}

    asyncio.run(scenario())
