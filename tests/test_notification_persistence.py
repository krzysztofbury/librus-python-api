"""Real SQLite and original public native notification runtime/fault proofs."""

import asyncio
import base64
import gzip
import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    NotificationCategory,
    RecentScheduleEvent,
    RequestBudget,
)
from librus_python_api.exceptions import LibrusError
from librus_python_api.persistence import (
    NotificationLimits,
    NotificationStore,
    NotificationWorkflow,
    canonical_notification_id,
)
from tests.http_support import FIXTURE_SECRET, serve
from tests.notification_persistence_support import NotificationWorkflowFixture
from tests.notifications_support import event_row, events_html

AGENDA = (NotificationCategory.AGENDA,)


def offline_service(origin: str) -> LibrusService:
    return LibrusService(
        context_key=bytes(range(32)),
        accounts={
            "student": AccountCredentials(login="student", password=FIXTURE_SECRET)
        },
        connection=ConnectionSettings(synergia_origin=origin, api_origin=origin),
    )


def test_schedule_identity_covers_all_three_visible_fields_and_preserves_unicode() -> (
    None
):
    event = RecentScheduleEvent("fixture date", "fixture type", "fixture α\nline")
    expected = hashlib.sha256(
        b'{"data":"fixture \xce\xb1\\nline","date_added":"fixture date",'
        b'"type":"fixture type"}'
    ).hexdigest()
    assert canonical_notification_id(NotificationCategory.AGENDA, event) == expected
    for changes in (
        {"date_added": "different"},
        {"type": "different"},
        {"data": "different"},
    ):
        assert (
            canonical_notification_id(
                NotificationCategory.AGENDA, replace(event, **changes)
            )
            != expected
        )


@pytest.mark.parametrize("compressed", [False, True])
def test_raw_delivery_restart_offline_replay_ack_and_first_run(
    tmp_path: Path, compressed: bool
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        if compressed:
            fixture.payload = gzip.compress(fixture.payload)
            fixture.encoding = "gzip"
        directory = tmp_path / "state"
        store = NotificationStore(directory)
        assert not directory.exists()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with store:
                    batch = await NotificationWorkflow(client, store).poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                    assert batch.first_run and not batch.has_more_schedule
                    assert batch.items[0].value == RecentScheduleEvent(
                        "2026-10-02 08:00",
                        "Added fixture",
                        "Fixture event\nSecond line",
                    )
                    assert not (await store.state(context=client.context)).initialized
                    archive = await store.export_archive(context=client.context)
                    record = json.loads(archive.payload)
                    assert base64.b64decode(record["raw"]["body"]) == fixture.payload
                    assert record["raw"]["cursor"] == 0
                    assert fixture.calls_by_account == ["student"]
        before = len(fixture.calls)
        async with offline_service(origin) as service:
            async with NotificationStore(directory) as reopened:
                workflow = NotificationWorkflow(service.account("student"), reopened)
                budget = RequestBudget(max_requests=1)
                replay = await workflow.poll(categories=AGENDA, budget=budget)
                assert replay == batch and budget.requests_dispatched == 0
                await workflow.acknowledge(replay.receipt)
                await workflow.acknowledge(replay.receipt)
                state = await reopened.state(context=workflow.client.context)
                assert state.initialized and state.seen[4].identifiers == (
                    batch.items[0].identifier,
                )
                cleaned = json.loads(
                    (
                        await reopened.export_archive(context=workflow.client.context)
                    ).payload
                )
                assert cleaned["raw"] is None and cleaned["delivery"] is None
        assert len(fixture.calls) == before
        database = (directory / "notifications.sqlite3").read_bytes()
        assert FIXTURE_SECRET.encode() not in database
        assert b"private-cookie" not in database
        assert "Fixture event" not in repr(batch) and "Fixture event" not in repr(
            archive
        )

    asyncio.run(scenario())


def test_fresh_receipt_is_parsed_once_with_one_response_byte_budget(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(
            "".join(event_row("x" * 999 + str(i)) for i in range(100))
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(tmp_path / "state") as store:
                    budget = RequestBudget(
                        max_requests=6, max_response_bytes=len(fixture.payload) + 2048
                    )
                    batch = await NotificationWorkflow(
                        service.account("student"), store
                    ).poll(categories=AGENDA, allow_consume_events=True, budget=budget)
                    assert len(batch.items) == 100 and budget.requests_dispatched == 6

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["markup", "gzip", "mime", "encoding"])
def test_malformed_complete_raw_is_retained_and_prevents_fresh_consume(
    tmp_path: Path, mode: str
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        if mode == "markup":
            fixture.payload = (
                b"<html><body>Original unsupported structure</body></html>"
            )
        elif mode == "gzip":
            fixture.encoding, fixture.payload = "gzip", b"original non-gzip bytes"
        elif mode == "mime":
            fixture.mime = "application/octet-stream"
        else:
            fixture.encoding = "br"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(tmp_path / "state") as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    with pytest.raises(LibrusError):
                        await workflow.poll(
                            categories=AGENDA, allow_consume_events=True
                        )
                    archive = await store.export_archive(
                        context=workflow.client.context
                    )
                    record = json.loads(archive.payload)
                    assert base64.b64decode(record["raw"]["body"]) == fixture.payload
                    assert record["delivery"] is None and record["reservation"] is None
                    before = len(fixture.calls)
                    with pytest.raises(LibrusError):
                        await workflow.poll(
                            categories=AGENDA, allow_consume_events=True
                        )
                    assert len(fixture.calls) == before
                    assert fixture.calls_by_account == ["student"]

    asyncio.run(scenario())


def test_six_categories_through_native_api_and_unrequested_state_survives(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(tmp_path / "state") as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    categories = tuple(NotificationCategory)
                    batch = await workflow.poll(
                        categories=categories,
                        allow_consume_events=True,
                        homework_window=(date(2026, 9, 1), date(2026, 9, 30)),
                        budget=RequestBudget(max_requests=11),
                    )
                    assert set(item.category for item in batch.items) == set(categories)
                    before = len(fixture.calls)
                    assert await workflow.poll(categories=categories) == batch
                    assert len(fixture.calls) == before
                    await workflow.acknowledge(batch.receipt)
                    seen = await store.state(context=workflow.client.context)
                    grades = await workflow.poll(
                        categories=(NotificationCategory.GRADES,)
                    )
                    assert not grades.first_run and grades.items == ()
                    await workflow.acknowledge(grades.receipt)
                    assert await store.state(context=workflow.client.context) == seen
                    assert fixture.calls_by_account == ["student"]
                    assert all(path != "/uczen/index" for path, _ in fixture.calls)
                    assert all(
                        "szczegoly" not in path and "/f0" not in path
                        for path, _ in fixture.calls
                    )

    asyncio.run(scenario())


@pytest.mark.parametrize("byte_bound", [False, True])
def test_bounded_raw_slices_require_ack_and_drain_without_live_calls(
    tmp_path: Path,
    byte_bound: bool,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(
            "".join(event_row(f"Original event {i}") for i in range(5))
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(
                    tmp_path / "state",
                    limits=(
                        NotificationLimits(replay_bytes=200)
                        if byte_bound
                        else NotificationLimits(replay_events=2)
                    ),
                ) as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    first = await workflow.poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                    assert len(first.items) == 2 and first.has_more_schedule
                    await workflow.acknowledge(first.receipt)
                    before = len(fixture.calls)
                    second = await workflow.poll(categories=AGENDA)
                    assert (
                        len(second.items) == 2
                        and second.has_more_schedule
                        and not second.first_run
                    )
                    # A late retry of the last committed receipt must not discard
                    # or accidentally acknowledge the newer staged delivery.
                    await workflow.acknowledge(first.receipt)
                    assert await workflow.poll(categories=AGENDA) == second
                    await workflow.acknowledge(second.receipt)
                    third = await workflow.poll(categories=AGENDA)
                    assert len(third.items) == 1 and not third.has_more_schedule
                    await workflow.acknowledge(third.receipt)
                    assert len(fixture.calls) == before
                    assert (
                        len(
                            {
                                item.identifier
                                for b in (first, second, third)
                                for item in b.items
                            }
                        )
                        == 5
                    )
                    assert fixture.calls_by_account == ["student"]

    asyncio.run(scenario())
