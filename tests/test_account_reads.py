"""Shared read guarantees, checked once per operation over real loopback HTTP.

Every public read runs through the same admission, coalescing, cache, session
and budget path. Family test modules own parser semantics and wire forms.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from librus_python_api import AccountClient, RequestBudget, SchoolReference
from librus_python_api.config import ENDPOINTS, TransportLimits
from librus_python_api.exceptions import (
    AccessDeniedError,
    ErrorKind,
    InvalidInputError,
    LibrusError,
    LimitError,
    MaintenanceError,
    OperationTimeoutError,
    ParseError,
    SessionExpiredError,
    ThrottledError,
    ViewDisabledError,
)
from librus_python_api.models import DiagnosticEvent
from tests.http_support import serve
from tests.reads_support import (
    HTML_OPERATIONS,
    OPERATIONS,
    VALID,
    Read,
    ReadsFixture,
    read,
)
from tests.school_reads_support import VIEW_DISABLED, warning_html
from tests.timetable_support import MONDAY

# portal, authorization form, credential submission, callback, identity
LOGIN_REQUESTS = 5

type Scenario = Callable[[ReadsFixture, Any], Awaitable[None]]


def run(scenario: Scenario, aliases: tuple[str, ...] = ("student",)) -> None:
    async def main() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(aliases) as service:
                await scenario(fixture, service)

    asyncio.run(main())


@pytest.mark.parametrize("operation", OPERATIONS)
def test_identical_reads_coalesce_per_login_and_never_share_a_session(
    operation: str,
) -> None:
    aliases = ("student-a", "parent-a", "student-b", "parent-b")

    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        def call(alias: str, **options: Any) -> Awaitable[Any]:
            return read(service.account(alias), alias, operation)(**options)

        results = await asyncio.gather(*(call(a) for a in aliases for _ in range(2)))
        assert fixture.logins == dict.fromkeys(aliases, 1)
        for index, alias in enumerate(aliases):
            assert fixture.count(operation, alias) == 1
            # Same-student logins remain separate owners, never merged sessions.
            assert (
                {results[2 * index].identity.owner.id}
                == {results[2 * index + 1].identity.owner.id}
                == {alias}
            )
        await call(aliases[0], max_age_seconds=60)
        assert fixture.count(operation, aliases[0]) == 1
        await call(aliases[0])
        assert fixture.count(operation, aliases[0]) == 2

    run(scenario, aliases)


@pytest.mark.parametrize("status", [401, 302])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_proven_expiry_recovers_safe_reads_once_and_never_replays_a_post(
    operation: str, status: int
) -> None:
    safe = ENDPOINTS[operation].retry_safe

    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        client = service.account("student")
        await client.identity()
        fixture.failures[operation] = [status]
        if safe:
            await read(client, "student", operation)()
        else:
            with pytest.raises(SessionExpiredError):
                await read(client, "student", operation)()
        assert fixture.logins == {"student": 2 if safe else 1}
        assert fixture.count(operation) == (2 if safe else 1)

    run(scenario)


@pytest.mark.parametrize(
    "status,error",
    [(403, AccessDeniedError), (429, ThrottledError), (503, MaintenanceError)],
)
@pytest.mark.parametrize("operation", OPERATIONS)
def test_denial_throttling_and_maintenance_are_never_retried(
    operation: str, status: int, error: type[LibrusError]
) -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        client = service.account("student")
        await client.identity()
        fixture.failures[operation] = [status]
        with pytest.raises(error):
            await read(client, "student", operation)()
        assert fixture.logins == {"student": 1}
        assert fixture.count(operation) == 1

    run(scenario)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_unrecognized_page_fails_whole_read_and_is_not_cached(operation: str) -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        client = service.account("student")
        kind = "application/json" if operation == "gateway_attendance" else "text/html"
        fixture.bodies[operation] = (
            b"{}" if "json" in kind else b"<html></html>",
            kind,
        )
        with pytest.raises(LibrusError) as failure:
            await read(client, "student", operation)(max_age_seconds=60)
        assert failure.value.kind in (ErrorKind.PARSE, ErrorKind.UNSUPPORTED_CAPABILITY)
        del fixture.bodies[operation]
        await read(client, "student", operation)(max_age_seconds=60)
        assert fixture.count(operation) == 2

    run(scenario)


@pytest.mark.parametrize("operation", HTML_OPERATIONS)
def test_view_disabled_by_school_is_typed_for_every_page(operation: str) -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        fixture.bodies[operation] = (warning_html(VIEW_DISABLED).encode(), "text/html")
        with pytest.raises(ViewDisabledError):
            await read(service.account("student"), "student", operation)()

    run(scenario)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_one_budget_covers_login_and_read(operation: str) -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        short = RequestBudget(max_requests=LOGIN_REQUESTS)
        with pytest.raises(LimitError):
            await read(service.account("short"), "short", operation)(budget=short)
        assert fixture.count(operation) == 0
        exact = RequestBudget(max_requests=LOGIN_REQUESTS + 1)
        await read(service.account("exact"), "exact", operation)(budget=exact)
        assert exact.requests_dispatched == LOGIN_REQUESTS + 1

    run(scenario, ("short", "exact"))


@pytest.mark.parametrize("operation", OPERATIONS)
def test_cancelling_the_last_waiter_joins_the_read_and_frees_capacity(
    operation: str,
) -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        client = service.account("student")
        await client.identity()
        fixture.hold = asyncio.Event()
        task = asyncio.create_task(read(client, "student", operation)())
        await asyncio.wait_for(fixture.held.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert service.snapshot().active == service.snapshot().queued == 0
        fixture.hold.set()
        fixture.hold = None
        await read(client, "student", operation)()

    run(scenario)


def invalid_calls(client: AccountClient) -> list[Callable[[], Awaitable[Any]]]:
    other = SchoolReference("agenda", "123", "another-login")
    return [
        lambda: client.grades(view="all"),  # type: ignore[arg-type]
        lambda: client.attendance(view="all"),  # type: ignore[arg-type]
        lambda: client.grades_window(date(2026, 2, 1), date(2026, 1, 1)),
        lambda: client.attendance_window(date(2026, 1, 1), date(2027, 1, 2)),
        lambda: client.attendance_detail("../2468"),
        lambda: client.subject_frequency(datetime(2026, 1, 1)),
        lambda: client.timetable(date(2026, 10, 6)),  # a Tuesday
        lambda: client.timetable(datetime(2026, 10, 5)),
        lambda: client.timetable("2026-10-05"),  # type: ignore[arg-type]
        lambda: client.agenda(2026, 13),
        lambda: client.agenda(2000, 1),
        lambda: client.agenda(True, 10),
        lambda: client.agenda_detail(other),
        lambda: client.homework_detail(SchoolReference("agenda", "123", "student")),
        lambda: client.agenda_detail(SchoolReference("agenda", "../1", "student")),
        lambda: client.homework_detail("456"),  # type: ignore[arg-type]
        lambda: client.homework(date(2026, 9, 1), date(2026, 10, 2)),
        lambda: client.completed_lessons_page(
            date(2026, 9, 1), date(2026, 9, 1), page=-1
        ),
        lambda: client.completed_lessons(date(2026, 9, 1), date(2026, 9, 1), limit=0),
        lambda: client.identity(max_age_seconds=float("nan")),
        lambda: client.identity(max_age_seconds=3601),
    ]


def test_invalid_inputs_are_rejected_before_any_request() -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        client = service.account("student")
        for call in invalid_calls(client):
            with pytest.raises(InvalidInputError):
                await call()
        assert fixture.calls == []

    run(scenario)


def selection_pairs(client: AccountClient) -> dict[str, tuple[Read, Read]]:
    """Two different selections per operation; each must be its own read."""
    from librus_python_api import AttendanceView, GradeView

    def ref(kind: Any, identifier: str) -> SchoolReference:
        return SchoolReference(kind, identifier, "student")

    october, september = (
        (date(2026, 10, 1), date(2026, 10, 31)),
        (
            date(2026, 9, 1),
            date(2026, 9, 30),
        ),
    )
    return {
        "grades": (
            lambda **kw: client.grades(**kw),
            lambda **kw: client.grades(view=GradeView.WEEK, **kw),
        ),
        "attendance": (
            lambda **kw: client.attendance(**kw),
            lambda **kw: client.attendance(view=AttendanceView.LAST_LOGIN, **kw),
        ),
        "attendance_detail": (
            lambda **kw: client.attendance_detail("2468", **kw),
            lambda **kw: client.attendance_detail("2469", **kw),
        ),
        "timetable": (
            lambda **kw: client.timetable(MONDAY, **kw),
            lambda **kw: client.timetable(MONDAY + timedelta(days=7), **kw),
        ),
        "agenda": (
            lambda **kw: client.agenda(2026, 10, **kw),
            lambda **kw: client.agenda(2026, 9, **kw),
        ),
        "agenda_detail": (
            lambda **kw: client.agenda_detail(ref("agenda", "123"), **kw),
            lambda **kw: client.agenda_detail(ref("agenda", "124"), **kw),
        ),
        "homework": (
            lambda **kw: client.homework(*september, **kw),
            lambda **kw: client.homework(september[0], date(2026, 9, 29), **kw),
        ),
        "homework_detail": (
            lambda **kw: client.homework_detail(ref("homework", "456"), **kw),
            lambda **kw: client.homework_detail(ref("homework", "457"), **kw),
        ),
        "completed_lessons": (
            lambda **kw: client.completed_lessons_page(*october, **kw),
            lambda **kw: client.completed_lessons_page(
                october[0], date(2026, 10, 30), **kw
            ),
        ),
    }


@pytest.mark.parametrize(
    "operation",
    [
        "grades",
        "attendance",
        "attendance_detail",
        "timetable",
        "agenda",
        "agenda_detail",
        "homework",
        "homework_detail",
        "completed_lessons",
    ],
)
def test_distinct_selections_are_never_served_from_each_others_cache(
    operation: str,
) -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        first, second = selection_pairs(service.account("student"))[operation]
        await first(max_age_seconds=60)
        await second(max_age_seconds=60)
        assert fixture.count(operation) == 2
        await first(max_age_seconds=60)
        await second(max_age_seconds=60)
        assert fixture.count(operation) == 2

    run(scenario)


@pytest.mark.parametrize("mode", ["media_type", "parser_bytes"])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_wrong_media_type_or_oversized_page_fails_without_raw_cause(
    operation: str, mode: str
) -> None:
    async def main() -> None:
        fixture = ReadsFixture()
        body, kind = VALID[operation]
        if mode == "media_type":
            wrong = "text/html" if kind == "application/json" else "application/json"
            fixture.bodies[operation] = (body, wrong)
        else:
            fixture.bodies[operation] = (body + b" " * 1024, kind)
        limits = TransportLimits(parse_max_bytes=len(body) + 512)
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(transport_limits=limits) as service:
                expected = ParseError if mode == "media_type" else LimitError
                with pytest.raises(expected) as failure:
                    await read(service.account("student"), "student", operation)()
                assert failure.value.__context__ is None
                assert failure.value.__cause__ is None
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(main())


WIRE_FORMS = {
    "grades": {"zmiany_logowanie_wszystkie": "1"},
    "attendance": {"zmiany_logowanie_wszystkie": ""},
    "timetable": {"tydzien": "2026-10-05_2026-10-11"},
    "agenda": {"rok": "2026", "miesiac": "10"},
    "homework": {
        "dataOd": "2026-09-01",
        "dataDo": "2026-09-30",
        "przedmiot": "-1",
        "status": "-1",
    },
    "completed_lessons": {
        "data1": "2026-10-01",
        "data2": "2026-10-31",
        "filtruj_id_przedmiotu": "-1",
        "numer_strony1001": "0",
        "porcjowanie_pojemnik1001": "1001",
    },
}


@pytest.mark.parametrize("operation", OPERATIONS)
def test_each_read_sends_exactly_its_fixed_form(operation: str) -> None:
    async def scenario(fixture: ReadsFixture, service: Any) -> None:
        await read(service.account("student"), "student", operation)()
        form, query, body = fixture.wire[operation]
        assert ENDPOINTS[operation].method == ("POST" if form else "GET")
        assert form == WIRE_FORMS.get(operation, {})
        assert query == "" and body == b""

    run(scenario)


def test_diagnostics_report_each_outcome_kind() -> None:
    events: list[DiagnosticEvent] = []

    async def main() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(diagnostic_sink=events.append) as service:
                client = service.account("student")
                await client.announcements()
                fixture.bodies["announcements"] = (b"<html></html>", "text/html")
                with pytest.raises(ParseError):
                    await client.announcements()
                del fixture.bodies["announcements"]
                fixture.hold = asyncio.Event()
                with pytest.raises(OperationTimeoutError):
                    await client.announcements(
                        budget=RequestBudget(timeout_seconds=0.3)
                    )
                fixture.held.clear()
                task = asyncio.create_task(client.agenda(2026, 10))
                await asyncio.wait_for(fixture.held.wait(), timeout=2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                fixture.hold.set()

    asyncio.run(main())
    assert [event.outcome for event in events] == [
        "ok",
        ErrorKind.PARSE,
        ErrorKind.TIMEOUT,
        "cancelled",
    ]
