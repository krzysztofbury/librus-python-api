import asyncio
import json
from dataclasses import FrozenInstanceError

import pytest

from librus_python_api import (
    Availability,
    RequestBudget,
    SchedulerLimits,
    TransportLimits,
)
from librus_python_api.config import (
    AccountCredentials,
    ConnectionSettings,
)
from librus_python_api.diagnostics import loguru_sink
from librus_python_api.exceptions import (
    AccessDeniedError,
    AccountActionRequiredError,
    ClosedError,
    CredentialsRejectedError,
    ErrorKind,
    LibrusError,
    LimitError,
    ParseError,
    SessionExpiredError,
    error_for,
)
from librus_python_api.models import DiagnosticEvent
from librus_python_api.parsers import parse_identity, parse_profile
from librus_python_api.service import LibrusService
from tests.http_support import FIXTURE_SECRET, SchoolFixture, profile_html, serve


@pytest.mark.parametrize(
    ("user_id", "account_user_id", "valid"),
    [
        (None, 43, True),
        (43, 43, True),
        (43, 44, False),
        (None, None, False),
        (None, True, False),
    ],
)
def test_gateway_user_reference_is_explicit_and_consistent(
    user_id: int | None,
    account_user_id: int | None,
    valid: bool,
) -> None:
    account: dict[str, object] = {"Id": 17, "FirstName": "Fixture Owner"}
    user: dict[str, object] = {"FirstName": "Fixture Student"}
    if account_user_id is not None:
        account["UserId"] = account_user_id
    if user_id is not None:
        user["Id"] = user_id
    body = json.dumps({"Me": {"Account": account, "User": user}}).encode()
    if valid:
        owner, student = parse_identity(body)
        assert owner.id == "17"
        assert student.id == "43"
        assert student.first_name == "Fixture Student"
    else:
        with pytest.raises(ParseError):
            parse_identity(body)


def test_four_login_profile_reads_coalesce_reuse_and_never_merge_by_student() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        aliases = ("student-a", "parent-a", "student-b", "parent-b")
        events: list[DiagnosticEvent] = []
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(
                aliases, diagnostic_sink=events.append
            ) as service:
                results = await asyncio.gather(
                    *(
                        service.account(alias).student_information()
                        for alias in aliases
                        for _ in range(3)
                    )
                )
                for index, alias in enumerate(aliases):
                    result = results[index * 3]
                    assert result is results[index * 3 + 1]
                    assert result.identity.owner.id == alias
                    assert result.identity.student.id == "student-shared"
                    assert result.school == f"Fixture School {alias}"
                    assert result.register_number == 12
                    assert result.lucky_number.number == 7
                    assert result.lucky_number.day is None
                    assert result.observation.account == alias
                    offset = result.observation.observed_at.utcoffset()
                    assert offset is not None
                    assert offset.total_seconds() == 0
                    assert "Fixture" not in repr(result)
                    with pytest.raises(FrozenInstanceError):
                        result.school = "modified"  # type: ignore[misc]
                assert fixture.logins == dict.fromkeys(aliases, 1)
                # 5 login/verification requests and 1 profile request per login.
                assert (
                    len(fixture.calls) == service.snapshot().requests_dispatched == 24
                )
                assert len(fixture.connections) == 4
                cached = await service.account(aliases[0]).student_information(
                    max_age_seconds=60
                )
                assert cached is results[0]
                assert len(fixture.calls) == 24
                fresh = await service.account(aliases[0]).student_information()
                assert fresh is not cached
                assert len(fixture.calls) == 25
                assert fixture.logins[aliases[0]] == 1
                assert service.snapshot().active == service.snapshot().queued == 0
                assert len(events) == 6
                assert sum(event.budget_requests_dispatched for event in events) == 25
                assert "student-a" not in repr(events)
            with pytest.raises(ClosedError):
                await service.account("student-a").identity()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("challenge", AccountActionRequiredError),
        ("rejected", CredentialsRejectedError),
        ("cookie_missing", AccountActionRequiredError),
        ("malformed_identity", ParseError),
        ("redirect_loop", LimitError),
    ],
)
def test_login_failures_are_typed_redacted_and_never_retry_submission(
    mode: str,
    expected: type[LibrusError],
) -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        alias = "rejected" if mode == "rejected" else "student"
        if mode != "rejected":
            setattr(fixture, mode, True)
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(
                (alias,), transport_limits=TransportLimits(max_redirects=2)
            ) as service:
                with pytest.raises(expected) as caught:
                    await service.account(alias).identity()
                assert caught.value.__context__ is None
                assert fixture.logins[alias] == 1
                if mode in ("challenge", "rejected", "cookie_missing"):
                    before = len(fixture.calls)
                    with pytest.raises(expected):
                        await service.account(alias).identity()
                    assert len(fixture.calls) == before
                assert "fixture-only-secret" not in repr(caught.value)

    asyncio.run(scenario())


def test_denied_account_does_not_relogin_or_break_other_account() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.profile_status["parent"] = 403
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student", "parent")) as service:
                outcomes = await asyncio.gather(
                    *(
                        service.account(alias).student_information()
                        for alias in ("student", "parent")
                    ),
                    return_exceptions=True,
                )
                assert not isinstance(outcomes[0], BaseException)
                assert isinstance(outcomes[1], AccessDeniedError)
                before = len(fixture.calls)
                with pytest.raises(AccessDeniedError):
                    await service.account("parent").student_information()
                assert len(fixture.calls) == before
                assert (await service.account("parent").identity()).owner.id == "parent"
                assert fixture.logins == {"student": 1, "parent": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize("expires", [1, 2])
def test_safe_recovery_is_one_reauthentication_with_original_budget(
    expires: int,
) -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.expire_profile["student"] = expires
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                budget = RequestBudget(max_requests=12)
                if expires == 1:
                    result = await service.account("student").student_information(
                        budget=budget
                    )
                    assert result.observation.session_generation == 2
                else:
                    with pytest.raises(SessionExpiredError):
                        await service.account("student").student_information(
                            budget=budget
                        )
                assert budget.requests_dispatched == len(fixture.calls) == 12
                assert fixture.logins == {"student": 2}
                if expires == 2:
                    before = len(fixture.calls)
                    with pytest.raises(SessionExpiredError):
                        await service.account("student").student_information()
                    assert len(fixture.calls) == before

    asyncio.run(scenario())


def test_budget_exhaustion_stops_before_reauthentication_dispatch() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.expire_profile["student"] = 1
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                budget = RequestBudget(max_requests=6)
                with pytest.raises(LimitError):
                    await service.account("student").student_information(budget=budget)
                assert budget.requests_dispatched == len(fixture.calls) == 6
                assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_coalesced_waiter_cancellation_keeps_survivor_and_last_waiter_joins() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.wait_profile = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = asyncio.create_task(client.student_information())
                second = asyncio.create_task(client.student_information())
                await asyncio.wait_for(fixture.profile_started.wait(), 1)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                fixture.wait_profile.set()
                assert (await second).school == "Fixture School student"
                fixture.profile_started.clear()
                fixture.wait_profile.clear()
                last = asyncio.create_task(client.student_information())
                await asyncio.wait_for(fixture.profile_started.wait(), 1)
                last.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await last
                assert service.snapshot().active == 0
                fixture.wait_profile.set()
                assert (await client.student_information()).register_number == 12
                assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_operation_waiters_are_bounded_before_waiting_for_account_lock() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.wait_profile = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            limits = SchedulerLimits(
                requests_per_second=1000,
                burst=16,
                operations=2,
                operations_per_account=2,
            )
            async with fixture.service(scheduler_limits=limits) as service:
                client = service.account("student")
                first = asyncio.create_task(client.student_information())
                await fixture.profile_started.wait()
                second = asyncio.create_task(client.identity())
                await asyncio.sleep(0)
                before = len(fixture.calls)
                with pytest.raises(LimitError):
                    await client.identity()
                assert len(fixture.calls) == before
                fixture.wait_profile.set()
                await asyncio.gather(first, second)

    asyncio.run(scenario())


def test_service_close_cancels_owned_reads_and_rejects_future_calls() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.wait_profile = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            service = fixture.service()
            client = service.account("student")
            pending = asyncio.create_task(client.student_information())
            await fixture.profile_started.wait()
            await service.aclose()
            with pytest.raises(ClosedError):
                await pending
            assert service.snapshot().active == 0
            with pytest.raises(ClosedError):
                await client.identity()
            await service.aclose()
            fixture.wait_profile.set()

    asyncio.run(scenario())


def test_expected_identity_mismatch_is_not_an_accepted_login() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with LibrusService(
                {
                    "student": AccountCredentials(
                        login="student",
                        password=FIXTURE_SECRET,
                        expected_student_id="different",
                    )
                },
                connection=ConnectionSettings(
                    synergia_origin=origin, api_origin=origin
                ),
                scheduler_limits=SchedulerLimits(requests_per_second=1000, burst=16),
            ) as service:
                with pytest.raises(AccessDeniedError):
                    await service.account("student").identity()
                assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"Me": {"Account":{"Id":true},"User":{"Id":"1"}}}',
        b'{"Me": {"Account":{"Id":"../x"},"User":{"Id":"1"}}}',
        b'{"Me": {}, "Me": {}}',
        b"not json",
    ],
)
def test_identity_parser_rejects_required_field_and_id_failures(body: bytes) -> None:
    with pytest.raises(ParseError) as caught:
        parse_identity(body)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_nonfinite_json_in_unknown_fields_is_not_trusted(number: str) -> None:
    # Otherwise-valid identity: must fail at JSON validation, not missing fields.
    body = (
        '{"Me":{"Account":{"Id":"17","FirstName":"Fixture"},'
        '"User":{"Id":"43","FirstName":"Fixture"}},"extra":' + number + "}"
    ).encode()
    with pytest.raises(ParseError) as caught:
        parse_identity(body)
    assert caught.value.__context__ is None


def test_profile_parser_uses_semantics_and_explicit_optional_availability() -> None:
    fields = parse_profile(profile_html(lucky="").encode())
    assert fields.register_number == 12
    assert fields.lucky_number.availability == Availability.UNAVAILABLE
    assert fields.lucky_number.number is None
    assert fields.lucky_number.day is None
    variant = profile_html().replace("Numer w dzienniku", "Nr w dzienniku")
    assert parse_profile(variant.encode()).tutor == "Fixture Tutor"


@pytest.mark.parametrize(
    "body",
    [
        "<html>no data</html>",
        profile_html().replace("Klasa", "unknown"),
        profile_html().replace("<td>12</td>", "<td>invalid</td>"),
        profile_html().replace("7</span>", "invalid</span>"),
        profile_html() + profile_html(),
    ],
)
def test_profile_parser_never_fabricates_partial_success(body: str) -> None:
    with pytest.raises(ParseError):
        parse_profile(body.encode())


def test_factory_covers_all_error_kinds_without_arbitrary_messages() -> None:
    for kind in ErrorKind:
        error = error_for(kind)
        assert type(error) is not LibrusError
        assert error.kind == kind
        assert str(error) == kind.value


def test_loguru_sink_emits_allowlisted_structured_fields() -> None:
    import json

    from loguru import logger

    messages: list[str] = []
    sink_id = logger.add(messages.append, serialize=True)
    try:
        loguru_sink(DiagnosticEvent("identity", "ok", 0.25, 7, 100))
    finally:
        logger.remove(sink_id)
    extra = json.loads(messages[0])["record"]["extra"]
    assert extra == {
        "component": "librus_python_api",
        "operation": "identity",
        "outcome": "ok",
        "elapsed_seconds": 0.25,
        "budget_requests_dispatched": 7,
        "budget_response_bytes": 100,
    }


def test_explicit_budgets_share_only_by_object_identity() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                shared = RequestBudget()
                a, b = await asyncio.gather(
                    client.student_information(budget=shared),
                    client.student_information(budget=shared),
                )
                assert a is b
                assert shared.requests_dispatched == 6
                independent = (RequestBudget(), RequestBudget())
                a, b = await asyncio.gather(
                    *(
                        client.student_information(budget=budget)
                        for budget in independent
                    )
                )
                assert a is not b
                assert [budget.requests_dispatched for budget in independent] == [1, 1]
                assert len(fixture.calls) == 8

    asyncio.run(scenario())


def test_freshness_expiry_and_reauthentication_invalidate_cached_profile() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.student_information()
                assert await client.student_information(max_age_seconds=60) is first
                await asyncio.sleep(0.02)
                expired = await client.student_information(max_age_seconds=0.01)
                assert expired is not first
                fixture.expire_profile["student"] = 1
                recovered = await client.student_information()
                assert recovered.observation.session_generation == 2
                assert await client.student_information(max_age_seconds=60) is recovered
                assert fixture.logins == {"student": 2}

    asyncio.run(scenario())


def test_deadline_covers_authentication_and_body_wait() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.wait_profile = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                with pytest.raises(LibrusError, match="^timeout$"):
                    await service.account("student").student_information(
                        budget=RequestBudget(timeout_seconds=0.05),
                    )
                assert service.snapshot().active == 0
                fixture.wait_profile.set()
                assert (
                    await service.account("student").student_information()
                ).register_number == 12

    asyncio.run(scenario())


def test_parse_pool_bounds_bytes_and_joins_actual_thread_on_cancellation() -> None:
    from threading import Event

    from librus_python_api.parsing import ParserPool

    async def scenario() -> None:
        entered = asyncio.Event()
        release, exited = Event(), Event()
        loop = asyncio.get_running_loop()

        def parser(body: bytes) -> int:
            loop.call_soon_threadsafe(entered.set)
            release.wait(2)
            exited.set()
            return len(body)

        pool = ParserPool(256 * 1024)
        try:
            with pytest.raises(LimitError):
                await pool.run(parser, b"x" * (256 * 1024 + 1), RequestBudget())
            assert not entered.is_set()
            task = asyncio.create_task(pool.run(parser, b"accepted", RequestBudget()))
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert exited.is_set()
        finally:
            release.set()
            pool.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [429, 503])
def test_shared_backoff_pauses_other_accounts_without_replaying_failed_read(
    status: int,
) -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.profile_status["parent"] = status
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(
                ("parent", "student"),
                scheduler_limits=SchedulerLimits(),
                transport_limits=TransportLimits(cooldown_seconds=0.05),
            ) as service:
                with pytest.raises(LibrusError) as caught:
                    await service.account("parent").student_information()
                assert caught.value.kind in (ErrorKind.THROTTLED, ErrorKind.MAINTENANCE)
                before = len(fixture.calls)
                task = asyncio.create_task(service.account("student").identity())
                await asyncio.sleep(0.015)
                assert len(fixture.calls) == before
                assert (await task).owner.id == "student"
                assert sum(path == "/informacja" for path, _ in fixture.calls) == 1
                assert fixture.logins == {"parent": 1, "student": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["html", "login_redirect", "foreign_redirect"])
def test_only_proven_session_expiry_can_trigger_credential_recovery(mode: str) -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                fixture.identity_mode = mode
                if mode == "login_redirect":
                    result = await client.identity()
                    assert result.observation.session_generation == 2
                    assert fixture.logins == {"student": 2}
                else:
                    expected = ParseError if mode == "html" else AccessDeniedError
                    with pytest.raises(expected):
                        await client.identity()
                    assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_profile_reads_student_rows_and_ignores_login_owner_rows() -> None:
    # Observed layout: student rows, then the logged-in user's own rows.
    body = """<html><body><h2>Informacja</h2>
    <table class="decorated big center form"><thead><tr><td>Uczeń</td></tr></thead>
    <tr><th>Imię i nazwisko ucznia</th><td>Fixture Student</td></tr>
    <tr><th>Klasa</th><td>5 X</td></tr>
    <tr><th>Nr w dzienniku</th><td>9</td></tr>
    <tr><th>Wychowawca</th><td>Fixture Tutor</td></tr>
    <tr><th>Szkoła</th><td>Fixture School</td></tr>
    <tr><td colspan="2">Użytkownik</td></tr>
    <tr><th>Imię i nazwisko użytkownika</th><td>Fixture Parent</td></tr>
    <tr><th>Login</th><td>fixture-login</td></tr>
    <tr><th>Hasło</th><td>********</td></tr>
    </table></body></html>"""
    fields = parse_profile(body.encode())
    assert (fields.name, fields.class_name, fields.register_number) == (
        "Fixture Student",
        "5 X",
        9,
    )
    assert fields.lucky_number.availability == Availability.UNAVAILABLE
