"""Public receipt, durability, decoding and cancellation invariants on loopback."""

import asyncio
import base64
import gzip
import json
import os
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import (
    Identity,
    NotificationCategory,
    Observation,
    Person,
    RequestBudget,
    ScheduleEventResponse,
    ScheduleEventWire,
    SchedulerLimits,
    TransportLimits,
)
from librus_python_api.exceptions import (
    AccessDeniedError,
    CheckpointError,
    ClosedError,
    ConnectionError,
    InvalidInputError,
    LibrusError,
    LimitError,
    OperationTimeoutError,
    ParseError,
    SessionExpiredError,
    ThrottledError,
    UnsupportedCapabilityError,
)
from librus_python_api.models import DiagnosticEvent
from librus_python_api.notifications import (
    parse_notification_counts,
    parse_schedule_events,
)
from librus_python_api.transport import AiohttpTransport
from tests.notifications_support import counts_html, event_row, events_html, rig


def durable_write(path: Path, body: bytes) -> None:
    # A consumer-owned test sink, not library storage or consumer integration.
    with path.open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def serialize_envelope(response: ScheduleEventResponse) -> bytes:
    record = asdict(response)
    record["wire"]["body"] = base64.b64encode(response.wire.body).decode("ascii")
    record["observation"]["observed_at"] = response.observation.observed_at.isoformat()
    record["identity"]["observation"]["observed_at"] = (
        response.identity.observation.observed_at.isoformat()
    )
    return json.dumps(record).encode()


def restore_envelope(path: Path) -> ScheduleEventResponse:
    record = json.loads(path.read_bytes())

    def observation(fields: dict[str, Any]) -> Observation:
        return Observation(
            fields["account"],
            datetime.fromisoformat(fields["observed_at"]),
            fields["session_generation"],
            fields["source"],
        )

    identity = record["identity"]
    wire = record["wire"]
    return ScheduleEventResponse(
        record["version"],
        Identity(
            Person(**identity["owner"]),
            Person(**identity["student"]),
            observation(identity["observation"]),
        ),
        ScheduleEventWire(
            base64.b64decode(wire["body"], validate=True),
            wire["content_type"],
            tuple(wire["content_codings"]),
            tuple(wire["transfer_codings"]),
        ),
        observation(record["observation"]),
    )


@pytest.mark.parametrize("compressed", [False, True])
def test_complete_batch_checkpoint_precedes_parsing_and_restart_replay_is_offline(
    tmp_path: Path,
    compressed: bool,
) -> None:
    async def scenario() -> None:
        recorded: list[ScheduleEventResponse] = []
        async with rig() as (fixture, service):
            fixture.payload = events_html(event_row() * 2)
            if compressed:
                fixture.payload = gzip.compress(fixture.payload)
                fixture.encoding = "gzip"

            async def persist(response: ScheduleEventResponse) -> None:
                assert response.wire.body == fixture.payload
                assert "private-cookie" not in repr(response)
                assert not hasattr(response.wire, "headers") and not hasattr(
                    response.wire, "url"
                )
                durable_write(tmp_path / "complete.payload", response.wire.body)
                durable_write(tmp_path / "envelope.json", serialize_envelope(response))
                recorded.append(response)

            result = await service.account("student").consume_schedule_events(
                checkpoint=persist, allow_consume_events=True
            )
            assert len(result.items) == 2
            assert [(r.date_added, r.type, r.data) for r in result.items] == [
                ("2026-10-02 08:00", "Added fixture", "Fixture event\nSecond line")
            ] * 2
            assert (
                result.identity == recorded[0].identity
                and result.observation == recorded[0].observation
            )
            assert fixture.calls_by_account == ["student"]
        async with rig() as (fixture, restarted):
            replay = restore_envelope(tmp_path / "envelope.json")
            assert replay.wire.body == (tmp_path / "complete.payload").read_bytes()
            budget = RequestBudget(max_requests=1)
            replayed = await restarted.account("student").decode_schedule_events(
                replay, budget=budget
            )
            assert replayed.items[0].data == "Fixture event\nSecond line"
            assert replayed == result
            assert fixture.calls == [] and budget.requests_dispatched == 0

    asyncio.run(scenario())


def test_cancel_at_exact_complete_receipt_boundary_still_hands_off_raw_body(
    tmp_path: Path,
) -> None:
    class ReceiptCancellation(AiohttpTransport):
        async def _read_payload(self, *args: Any, **kwargs: Any) -> bytes:
            body = await super()._read_payload(*args, **kwargs)
            owner = asyncio.current_task()
            assert owner is not None
            owner.cancel()
            return body

    async def scenario() -> None:
        async with rig(transport_factory=ReceiptCancellation) as (fixture, service):
            callbacks = 0

            async def persist(response: ScheduleEventResponse) -> None:
                nonlocal callbacks
                callbacks += 1
                durable_write(tmp_path / "receipt.payload", response.wire.body)

            with pytest.raises(asyncio.CancelledError):
                await service.account("student").consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            assert (
                callbacks == 1
                and (tmp_path / "receipt.payload").read_bytes() == fixture.payload
            )
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_callback_suppressing_timeout_keeps_capacity_until_its_work_stops() -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            timeout_seen, stop = asyncio.Event(), asyncio.Event()

            async def persist(response: ScheduleEventResponse) -> None:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    timeout_seen.set()
                    await stop.wait()

            task = asyncio.create_task(
                service.account("student").consume_schedule_events(
                    checkpoint=persist,
                    allow_consume_events=True,
                    checkpoint_timeout_seconds=0.02,
                )
            )
            await asyncio.wait_for(timeout_seen.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            assert not task.done() and service.snapshot().active == 1
            stop.set()
            with pytest.raises(CheckpointError):
                await task
            assert fixture.calls_by_account == ["student"]
            assert service.snapshot().active == 0

    asyncio.run(scenario())


def test_checkpoint_backpressure_and_cancelled_queue_share_read_admission() -> None:
    async def scenario() -> None:
        limits = SchedulerLimits(requests_per_second=1000, burst=40, active_requests=1)
        async with rig(("student", "parent"), scheduler_limits=limits) as (
            fixture,
            service,
        ):
            await service.account("student").identity()
            await service.account("parent").identity()
            entered, release = asyncio.Event(), asyncio.Event()

            async def persist(response: ScheduleEventResponse) -> None:
                entered.set()
                await release.wait()

            first = asyncio.create_task(
                service.account("student").consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            )
            await asyncio.wait_for(entered.wait(), 2)
            second = asyncio.create_task(
                service.account("parent").consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            )
            for _ in range(200):
                if service.snapshot().queued == 1:
                    break
                await asyncio.sleep(0.001)
            assert service.snapshot().queued == 1
            second.cancel()
            with pytest.raises(asyncio.CancelledError):
                await second
            assert fixture.calls_by_account == ["student"]
            other = asyncio.create_task(service.account("parent").notification_counts())
            for _ in range(200):
                if service.snapshot().queued == 1:
                    break
                await asyncio.sleep(0.001)
            assert not other.done() and service.snapshot().active == 1
            release.set()
            assert len((await first).items) == 1
            assert len((await other).items) == 6
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_replay_rejects_foreign_or_invalid_envelopes_without_authentication() -> None:
    async def scenario() -> None:
        recorded = []
        async with rig() as (_, service):

            async def persist(response: ScheduleEventResponse) -> None:
                recorded.append(response)

            await service.account("student").consume_schedule_events(
                checkpoint=persist, allow_consume_events=True
            )
        original = recorded[0]
        invalid = [
            replace(original, version=True),
            replace(original, version=2),
            replace(
                original, observation=replace(original.observation, account="parent")
            ),
            replace(original, wire=replace(original.wire, body=bytearray(b"x"))),  # type: ignore[arg-type]
            replace(original, wire=replace(original.wire, content_codings=["gzip"])),  # type: ignore[arg-type]
            replace(original, identity=replace(original.identity, observation=None)),  # type: ignore[arg-type]
        ]
        async with rig() as (fixture, service):
            for response in invalid:
                with pytest.raises(InvalidInputError):
                    await service.account("student").decode_schedule_events(response)
            assert fixture.calls == [] and service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body,error",
    [
        (
            events_html().replace(b"<th>Lp.</th>", b'<th colspan="2">Lp.</th>'),
            ParseError,
        ),
        (
            events_html().replace(
                b"</div>", b"<p class='msgEmptyTable'>Brak zdarze\xc5\x84</p></div>"
            ),
            ParseError,
        ),
        (
            events_html().replace(
                b"<tbody>",
                b"<tbody><tr><th>Lp.</th><th>Czas dodania</th>"
                b"<th>Rodzaj zdarzenia</th><th>Dane</th></tr>",
            ),
            ParseError,
        ),
        (
            events_html(event_row("<script>unsafe()</script>")),
            UnsupportedCapabilityError,
        ),
        (
            events_html(event_row()).replace(b"Czas dodania", b"Unknown header"),
            ParseError,
        ),
        (
            events_html(event_row()).replace(b"<td>Added fixture</td>", b"<td></td>"),
            ParseError,
        ),
        (
            events_html(event_row()).replace(b"<td>1</td>", b'<td colspan="2">1</td>'),
            ParseError,
        ),
        (events_html(event_row("x" * 65537)), LimitError),
        (events_html(event_row() * 1025), LimitError),
        (
            b"<html><body><div class='container-background'></div></body></html>",
            ParseError,
        ),
    ],
)
def test_event_semantics_reject_unknown_or_partial_layouts(
    body: bytes, error: type[LibrusError]
) -> None:
    with pytest.raises(error):
        parse_schedule_events(body)


@pytest.mark.parametrize(
    "body",
    [
        events_html(""),
        b"<html><body><div class='container-background'>"
        b"<p class='msgEmptyTable'>Brak zdarze\xc5\x84</p></div></body></html>",
    ],
)
def test_explicit_empty_event_shapes_are_distinct_from_missing_markup(
    body: bytes,
) -> None:
    assert parse_schedule_events(body) == ()


@pytest.mark.parametrize("consent", [False, True, 1, "yes"])
def test_invalid_consent_callback_and_deadline_fail_before_authentication(
    consent: Any,
) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            client = service.account("student")

            async def persist(response: ScheduleEventResponse) -> None:
                pytest.fail("Invalid input invoked callback")

            if consent is not True:
                with pytest.raises(InvalidInputError):
                    await client.consume_schedule_events(
                        checkpoint=persist, allow_consume_events=consent
                    )
            for callback, deadline in (
                (None, 5),
                (persist, 0),
                (persist, float("nan")),
                (persist, 31),
                (persist, True),
            ):
                with pytest.raises(InvalidInputError):
                    await client.consume_schedule_events(
                        checkpoint=callback,  # type: ignore[arg-type]
                        allow_consume_events=True,
                        checkpoint_timeout_seconds=deadline,
                    )
            assert fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode", ["markup", "parser_limit", "gzip", "invalid_gzip", "encoding", "mime"]
)
def test_encoded_payload_is_durable_before_decoding_or_parser_failure(
    mode: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        limits = TransportLimits(
            parse_max_bytes=1024 if mode == "parser_limit" else 262144
        )
        async with rig(transport_limits=limits) as (fixture, service):
            if mode == "parser_limit":
                fixture.payload = events_html(event_row("x" * 2048))
            elif mode == "markup":
                fixture.payload = b"<html><body>unrecognized structure</body></html>"
            elif mode == "gzip":
                fixture.payload = gzip.compress(fixture.payload)
                fixture.encoding = "gzip"
            elif mode == "invalid_gzip":
                fixture.payload = b"not gzip data"
                fixture.encoding = "gzip"
            elif mode == "encoding":
                fixture.encoding = "br"
            elif mode == "mime":
                fixture.mime = "application/octet-stream"
            envelopes = []

            async def persist(response: ScheduleEventResponse) -> None:
                durable_write(tmp_path / "raw.payload", response.wire.body)
                envelopes.append(response)

            call = service.account("student").consume_schedule_events(
                checkpoint=persist, allow_consume_events=True
            )
            if mode == "gzip":
                result = await call
                assert result.items[0].data == "Fixture event\nSecond line"
            else:
                expected = (
                    LimitError
                    if mode == "parser_limit"
                    else UnsupportedCapabilityError
                    if mode == "encoding"
                    else ParseError
                )
                with pytest.raises(expected):
                    await call
            assert (tmp_path / "raw.payload").read_bytes() == fixture.payload
            assert len(envelopes) == 1 and fixture.calls_by_account == ["student"]
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("commit", [False, True])
@pytest.mark.parametrize("interrupt", ["none", "cancel", "close"])
def test_checkpoint_exception_has_unknown_acknowledgement_and_wins_over_cancel(
    commit: bool, interrupt: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        loop_errors: list[dict[str, Any]] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: loop_errors.append(context)
        )
        async with rig() as (fixture, service):
            entered, release = asyncio.Event(), asyncio.Event()

            async def persist(response: ScheduleEventResponse) -> None:
                entered.set()
                await release.wait()
                if commit:
                    durable_write(tmp_path / "uncertain.payload", response.wire.body)
                raise RuntimeError("private callback and account detail")

            task = asyncio.create_task(
                service.account("student").consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            )
            await asyncio.wait_for(entered.wait(), 2)
            closer = None
            if interrupt == "cancel":
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
            elif interrupt == "close":
                closer = asyncio.create_task(service.aclose())
                await asyncio.sleep(0)
            release.set()
            with pytest.raises(CheckpointError) as caught:
                await task
            if closer is not None:
                await closer
            assert caught.value.__cause__ is None and caught.value.__suppress_context__
            assert str(caught.value) == "checkpoint" and "private" not in repr(
                caught.value
            )
            assert (tmp_path / "uncertain.payload").exists() is commit
            assert fixture.calls_by_account == ["student"]
            assert service.snapshot().active == service.snapshot().queued == 0

        await asyncio.sleep(0)
        assert loop_errors == []

    asyncio.run(scenario())


@pytest.mark.parametrize("commit", [False, True])
def test_self_cancelling_checkpoint_reports_unknown_ack_not_caller_cancellation(
    commit: bool, tmp_path: Path
) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):

            async def persist(response: ScheduleEventResponse) -> None:
                if commit:
                    durable_write(tmp_path / "self-cancel.payload", response.wire.body)
                task = asyncio.current_task()
                assert task is not None
                task.cancel()

            with pytest.raises(CheckpointError):
                await service.account("student").consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            assert (tmp_path / "self-cancel.payload").exists() is commit
            assert (
                fixture.calls_by_account == ["student"]
                and service.snapshot().active == 0
            )

    asyncio.run(scenario())


def test_unexpected_transport_error_is_redacted_and_diagnostic_is_failure() -> None:
    class BrokenTransport(AiohttpTransport):
        async def consume_schedule_events(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("fixture-private transport detail")

    async def scenario() -> None:
        reports: list[DiagnosticEvent] = []
        async with rig(
            transport_factory=BrokenTransport, diagnostic_sink=reports.append
        ) as (fixture, service):

            async def persist(response: ScheduleEventResponse) -> None:
                pytest.fail("Broken transport invoked checkpoint")

            with pytest.raises(ConnectionError) as caught:
                await service.account("student").consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            assert caught.value.__cause__ is caught.value.__context__ is None
            assert str(caught.value) == "connection"
            assert reports[-1].outcome == "connection"
            assert fixture.calls_by_account == [] and service.snapshot().active == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["cancel", "close", "deadline"])
def test_received_response_handoff_survives_cancel_close_and_operation_deadline(
    stage: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            client = service.account("student")
            await client.identity()
            entered, release = asyncio.Event(), asyncio.Event()
            callbacks = 0

            async def persist(response: ScheduleEventResponse) -> None:
                nonlocal callbacks
                callbacks += 1
                entered.set()
                await release.wait()
                durable_write(tmp_path / "durable.payload", response.wire.body)

            budget = RequestBudget(timeout_seconds=0.04 if stage == "deadline" else 2)
            task = asyncio.create_task(
                client.consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True, budget=budget
                )
            )
            await asyncio.wait_for(entered.wait(), 2)
            closer = None
            if stage == "cancel":
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
            elif stage == "close":
                closer = asyncio.create_task(service.aclose())
            else:
                await asyncio.sleep(0.06)
            await asyncio.sleep(0)
            assert not task.done() and service.snapshot().active == 1
            with pytest.raises(InvalidInputError):
                await client.consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            release.set()
            expected = (
                ClosedError
                if stage == "close"
                else OperationTimeoutError
                if stage == "deadline"
                else asyncio.CancelledError
            )
            with pytest.raises(expected):
                await task
            if closer:
                await closer
            assert (
                callbacks == 1
                and (tmp_path / "durable.payload").read_bytes() == fixture.payload
            )
            assert service.snapshot().active == service.snapshot().queued == 0
            if stage != "close":
                await client.student_information()

    asyncio.run(scenario())


def test_checkpoint_timeout_joins_cooperative_callback_and_never_returns_events() -> (
    None
):
    async def scenario() -> None:
        async with rig() as (fixture, service):
            cleanup = asyncio.Event()

            async def persist(response: ScheduleEventResponse) -> None:
                try:
                    await asyncio.Event().wait()
                finally:
                    cleanup.set()

            with pytest.raises(CheckpointError):
                await service.account("student").consume_schedule_events(
                    checkpoint=persist,
                    allow_consume_events=True,
                    checkpoint_timeout_seconds=0.02,
                )
            assert cleanup.is_set() and fixture.calls_by_account == ["student"]
            assert service.snapshot().active == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    [
        "expiry",
        "login_redirect",
        "foreign_redirect",
        "throttle",
        "disconnect",
        "partial_cancel",
        "body_limit",
    ],
)
def test_no_implicit_consume_replay_or_checkpoint_of_incomplete_or_denied_response(
    mode: str,
) -> None:
    async def scenario() -> None:
        async with rig(transport_limits=TransportLimits(response_max_bytes=4096)) as (
            fixture,
            service,
        ):
            if mode == "expiry":
                fixture.status = 401
            elif mode == "login_redirect":
                fixture.status = 302
            elif mode == "foreign_redirect":
                fixture.status, fixture.location = 302, "https://example.invalid"
            elif mode == "throttle":
                fixture.status = 429
            elif mode == "disconnect":
                fixture.disconnect = True
            elif mode == "partial_cancel":
                fixture.body_hold = asyncio.Event()
            else:
                fixture.payload = b"x" * 4097
            callbacks = 0

            async def persist(response: ScheduleEventResponse) -> None:
                nonlocal callbacks
                callbacks += 1

            task = asyncio.create_task(
                service.account("student").consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            )
            if mode == "partial_cancel":
                await asyncio.wait_for(fixture.pending.wait(), 2)
                task.cancel()
            expected = {
                "expiry": SessionExpiredError,
                "login_redirect": SessionExpiredError,
                "foreign_redirect": AccessDeniedError,
                "throttle": ThrottledError,
                "disconnect": ConnectionError,
                "partial_cancel": asyncio.CancelledError,
                "body_limit": LimitError,
            }[mode]
            with pytest.raises(expected):
                await task
            assert callbacks == 0 and fixture.calls_by_account == ["student"]
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_consume_is_uncached_but_simultaneous_same_login_is_rejected() -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            records = []

            async def persist(response: ScheduleEventResponse) -> None:
                records.append(response)

            client = service.account("student")
            first = await client.consume_schedule_events(
                checkpoint=persist, allow_consume_events=True
            )
            second = await client.consume_schedule_events(
                checkpoint=persist, allow_consume_events=True
            )
            assert first is not second and len(records) == 2
            assert fixture.calls_by_account == ["student", "student"]

            # A second consume while the first is inside its checkpoint is refused
            # before any request, so one process never consumes twice at once.
            entered, release = asyncio.Event(), asyncio.Event()

            async def held(response: ScheduleEventResponse) -> None:
                entered.set()
                await release.wait()

            task = asyncio.create_task(
                client.consume_schedule_events(
                    checkpoint=held, allow_consume_events=True
                )
            )
            await asyncio.wait_for(entered.wait(), 5)
            with pytest.raises(InvalidInputError):
                await client.consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            release.set()
            await task
            assert fixture.calls_by_account == ["student"] * 3
            assert len(records) == 2

    asyncio.run(scenario())


def test_four_full_batches_share_exact_budget_and_isolated_handoffs() -> None:
    async def scenario() -> None:
        aliases = ("student", "parent", "second-student", "second-parent")
        async with rig(
            aliases,
            scheduler_limits=SchedulerLimits(requests_per_second=1000, burst=40),
        ) as (fixture, service):
            fixture.payload = events_html(event_row("fixture") * 1024)
            budget = RequestBudget(max_requests=24, max_response_bytes=2 * 1024 * 1024)
            recorded = {}

            async def consume(alias: str) -> None:
                async def persist(response: ScheduleEventResponse) -> None:
                    recorded[alias] = response

                result = await service.account(alias).consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True, budget=budget
                )
                assert len(result.items) == 1024
                assert result.identity.owner.id == alias

            await asyncio.gather(*(consume(a) for a in aliases))
            assert set(recorded) == set(aliases) and budget.requests_dispatched == 24
            assert sorted(fixture.calls_by_account) == sorted(aliases)
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["read", "close"])
def test_checkpoint_cannot_reenter_its_service_and_deadlock(action: str) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            client = service.account("student")

            async def persist(response: ScheduleEventResponse) -> None:
                if action == "close":
                    await service.aclose()
                else:
                    await client.identity()

            with pytest.raises(CheckpointError):
                await client.consume_schedule_events(
                    checkpoint=persist, allow_consume_events=True
                )
            await client.student_information()
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_counts_read_the_shared_information_page_for_student_and_parent() -> None:
    expected = [
        (NotificationCategory.GRADES, 2),
        (NotificationCategory.ATTENDANCE, 0),
        (NotificationCategory.MESSAGES, 1),
        (NotificationCategory.ANNOUNCEMENTS, 0),
        (NotificationCategory.AGENDA, 3),
        (NotificationCategory.HOMEWORK, 4),
    ]

    async def scenario() -> None:
        async with rig(("student", "parent")) as (fixture, service):
            for alias in ("student", "parent"):
                counts = await service.account(alias).notification_counts()
                assert counts.identity.owner.id == alias
                assert [(i.category, i.count) for i in counts.items] == expected
            # The student landing route denies parent logins; it is never used.
            assert [c for c in fixture.calls if c[0] == "/informacja"] == [
                ("/informacja", "student"),
                ("/informacja", "parent"),
            ]
            assert all(path != "/uczen/index" for path, _ in fixture.calls)

    asyncio.run(scenario())


def test_counts_recover_a_proven_expiry_once() -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            client = service.account("student")
            await client.identity()
            fixture.expire_profile["student"] = 1
            assert len((await client.notification_counts()).items) == 6
            assert fixture.logins == {"student": 2}

    asyncio.run(scenario())


@pytest.mark.parametrize("href", ["/wiadomosci", "/wiadomosci3"])
def test_both_message_menu_links_count_as_messages(href: str) -> None:
    menu = counts_html().replace('"/wiadomosci3"', f'"{href}"')
    items = parse_notification_counts(menu.encode())
    assert (items[2].category, items[2].count) == (NotificationCategory.MESSAGES, 1)


@pytest.mark.parametrize(
    "change,error",
    [
        (
            lambda s: s.replace(
                '<a class="button counter">2</a>', '<span class="counter">2</span>'
            ),
            UnsupportedCapabilityError,
        ),
        (lambda s: s.replace(">2</a>", ">wrong</a>"), ParseError),
        (lambda s: s.replace(">2</a>", ">1000001</a>"), LimitError),
        (
            lambda s: s.replace(
                '<a class="button counter">2</a>',
                '<a class="counter">1</a><a class="counter">2</a>',
            ),
            ParseError,
        ),
        (lambda s: s.replace("/moje_zadania", "/wiadomosci"), ParseError),
        (lambda s: s.replace('id="graphic-menu"', 'id="unexpected"'), ParseError),
    ],
)
def test_invalid_menu_counters_never_silently_become_zero(
    change: Any, error: type[LibrusError]
) -> None:
    with pytest.raises(error):
        parse_notification_counts(change(counts_html()).encode())
