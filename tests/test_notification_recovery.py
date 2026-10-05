"""Offline recovery discovers original delivery without remembered selection."""

import asyncio
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import (
    MessagingBackend,
    NotificationCategory,
    RecentScheduleEvent,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import (
    NotificationBootstrap,
    NotificationLimits,
    NotificationRecoveryStatus,
    NotificationStore,
    NotificationWorkflow,
)
from tests.http_support import serve
from tests.notification_persistence_support import NotificationWorkflowFixture
from tests.notifications_support import event_row, events_html
from tests.test_modern_communication import CommunicationFixture
from tests.test_notification_persistence import offline_service


def test_history_recovery_discovers_exact_batch_without_category_selection(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "state"
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            async with NotificationStore(directory) as store:
                empty = await store.recovery_status(context=context)
                assert isinstance(empty, NotificationRecoveryStatus)
                assert empty.context == context and not empty.initialized
                assert not empty.has_pending_work
                assert empty.pending is None and empty.raw is None
                assert empty.last_acknowledged_receipt is None
                assert not empty.uncertain_consume
                assert await store.pending_batch(context=context) is None
                result = await store.bootstrap(
                    NotificationBootstrap(
                        context,
                        (),
                        (
                            RecentScheduleEvent(
                                "fixture date", "fixture type", "private fixture data"
                            ),
                        ),
                    ),
                    context=context,
                )
                batch = result.pending
                assert batch is not None
                status = await store.recovery_status(context=context)
                assert status.initialized and status.has_pending_work
                assert (
                    status.pending is not None
                    and status.pending.receipt == batch.receipt
                )
                assert status.pending.categories == batch.categories
                assert status.pending.item_count == 1
                assert status.raw is None and not status.uncertain_consume
                assert "private fixture data" not in repr(status)
                assert await store.pending_batch(context=context) == batch
            async with NotificationStore(directory) as restarted:
                assert await restarted.recovery_status(context=context) == status
                for _ in range(3):
                    assert await restarted.pending_batch(context=context) == batch
                foreign = replace(context, identifier="b" * 64)
                assert not (
                    await restarted.recovery_status(context=foreign)
                ).has_pending_work
                assert await restarted.pending_batch(context=foreign) is None
                await restarted.acknowledge(batch.receipt, context=context)
                acknowledged = await restarted.recovery_status(context=context)
                assert not acknowledged.has_pending_work and acknowledged.initialized
                assert acknowledged.last_acknowledged_receipt == batch.receipt
                assert await restarted.pending_batch(context=context) is None
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


def test_modern_recovery_does_not_require_configuring_the_original_backend(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.message_count = 1
        directory = tmp_path / "state"
        async with fixture.running() as service:
            context = service.account("student").context
            async with NotificationStore(directory) as store:
                batch = await NotificationWorkflow(
                    service.account("student"),
                    store,
                    messages_backend=MessagingBackend.MODERN,
                ).poll(categories=(NotificationCategory.MESSAGES,))
        before = len(fixture.calls) + len(fixture.modern_calls)
        async with NotificationStore(directory) as restarted:
            status = await restarted.recovery_status(context=context)
            assert status.pending is not None
            assert status.pending.messages_backend is MessagingBackend.MODERN
            assert status.pending.categories == (NotificationCategory.MESSAGES,)
            assert status.pending.first_run and status.pending.item_count == 1
            assert await restarted.pending_batch(context=context) == batch
            for operation in (restarted.recovery_status, restarted.pending_batch):
                with pytest.raises(LibrusError) as error:
                    await operation(context=replace(context, alias="parent"))
                assert error.value.kind is ErrorKind.PARSE
            await restarted.acknowledge(batch.receipt, context=context)
        assert len(fixture.calls) + len(fixture.modern_calls) == before

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["raw", "uncertain", "delivery_raw"])
def test_recovery_distinguishes_retained_raw_uncertainty_and_delivery_without_mutation(
    tmp_path: Path, phase: str
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        if phase == "raw":
            fixture.payload = b"<html>Original malformed event fixture</html>"
        elif phase == "uncertain":
            fixture.disconnect = True
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with NotificationStore(tmp_path / "state") as store:
                    workflow = NotificationWorkflow(client, store)
                    batch = None
                    if phase == "delivery_raw":
                        batch = await workflow.poll(
                            categories=(NotificationCategory.AGENDA,),
                            allow_consume_events=True,
                        )
                    else:
                        with pytest.raises(LibrusError) as error:
                            await workflow.poll(
                                categories=(NotificationCategory.AGENDA,),
                                allow_consume_events=True,
                            )
                        assert error.value.kind is (
                            ErrorKind.PARSE if phase == "raw" else ErrorKind.CONNECTION
                        )
                    before = len(fixture.calls)
                    archive = await store.export_archive(context=client.context)
                    status = await store.recovery_status(context=client.context)
                    assert status.has_pending_work and not status.initialized
                    assert status.uncertain_consume is (phase == "uncertain")
                    assert (status.pending is not None) is (phase == "delivery_raw")
                    if phase != "uncertain":
                        assert status.raw is not None and status.raw.cursor == 0
                        assert status.raw.wire_bytes == len(fixture.payload)
                        assert status.raw.total == (None if phase == "raw" else 1)
                    else:
                        assert status.raw is None
                    for _ in range(3):
                        assert (
                            await store.recovery_status(context=client.context)
                            == status
                        )
                        assert (
                            await store.pending_batch(context=client.context) == batch
                        )
                    assert await store.export_archive(context=client.context) == archive
                    assert len(
                        fixture.calls
                    ) == before and fixture.calls_by_account == ["student"]
                    if phase == "uncertain":
                        ordinary = await workflow.poll(
                            categories=(NotificationCategory.MESSAGES,)
                        )
                        both = await store.recovery_status(context=client.context)
                        assert (
                            both.pending is not None
                            and both.uncertain_consume
                            and both.raw is None
                        )
                        assert (
                            await store.pending_batch(context=client.context)
                            == ordinary
                        )
                        await workflow.acknowledge(ordinary.receipt)
                        assert (
                            await store.recovery_status(context=client.context)
                        ).uncertain_consume

    asyncio.run(scenario())


def test_status_during_active_poll_cannot_clear_its_conservative_marker(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.body_hold = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                context = service.account("student").context
                async with NotificationStore(tmp_path / "state") as store:
                    task = asyncio.create_task(
                        NotificationWorkflow(service.account("student"), store).poll(
                            categories=(NotificationCategory.AGENDA,),
                            allow_consume_events=True,
                        )
                    )
                    try:
                        await asyncio.wait_for(fixture.pending.wait(), 5)
                        status = await store.recovery_status(context=context)
                        assert status.uncertain_consume
                        assert status.raw is None and status.pending is None
                        assert await store.pending_batch(context=context) is None
                        with pytest.raises(LibrusError) as error:
                            await store.resolve_uncertain_consume(
                                context=context, accept_possible_loss=True
                            )
                        assert error.value.kind is ErrorKind.LIMIT
                    finally:
                        fixture.body_hold.set()
                        await asyncio.wait_for(task, 5)
                    completed = await store.recovery_status(context=context)
                    assert (
                        not completed.uncertain_consume
                        and completed.pending is not None
                    )
                    assert await store.pending_batch(context=context) == task.result()
                    assert fixture.calls_by_account == ["student"]

    asyncio.run(scenario())


def test_raw_cursor_advances_only_at_ack_and_compact_status_omits_content(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(
            "".join(event_row(f"private fixture {i}") for i in range(5))
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                context = service.account("student").context
                async with NotificationStore(
                    tmp_path / "state",
                    limits=NotificationLimits(batch_items=2, replay_events=2),
                ) as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    batch = await workflow.poll(
                        categories=(NotificationCategory.AGENDA,),
                        allow_consume_events=True,
                    )
                    before = len(fixture.calls)
                    status = await store.recovery_status(context=context)
                    assert status.pending is not None and status.raw is not None
                    assert (
                        status.pending.item_count == 2
                        and status.pending.has_more_schedule
                    )
                    assert status.raw.cursor == 0 and status.raw.total == 5
                    assert (
                        "private fixture" not in repr(status)
                        and len(repr(status)) < 1000
                    )
                    await workflow.acknowledge(batch.receipt)
                    status = await store.recovery_status(context=context)
                    assert status.pending is None and status.raw is not None
                    assert status.raw.cursor == 2 and status.raw.total == 5
                    assert status.last_acknowledged_receipt == batch.receipt
                    assert await store.pending_batch(context=context) is None
                    assert len(fixture.calls) == before

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["recovery_status", "pending_batch"])
def test_recovery_rejects_invalid_context_and_corrupt_seen_state(
    tmp_path: Path, operation: str
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            directory = tmp_path / "state"
            async with NotificationStore(directory) as store:
                read = getattr(store, operation)
                for invalid in (None, replace(context, identifier="invalid")):
                    with pytest.raises(LibrusError) as error:
                        await read(context=invalid)
                    assert error.value.kind is ErrorKind.INVALID_INPUT
                with pytest.raises(TypeError):
                    await read()
                await store.bootstrap(
                    NotificationBootstrap(context, (), ()), context=context
                )
                with sqlite3.connect(directory / "notifications.sqlite3") as db:
                    db.execute("UPDATE notification_state SET payload=?", (b"{",))
                with pytest.raises(LibrusError) as error:
                    await read(context=context)
                assert error.value.kind is ErrorKind.PARSE
                with sqlite3.connect(directory / "notifications.sqlite3") as db:
                    assert db.execute(
                        "SELECT payload FROM notification_state"
                    ).fetchone() == (b"{",)
                assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


def test_missing_context_recovery_does_not_use_registration_capacity(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            async with NotificationStore(
                tmp_path / "state", limits=NotificationLimits(contexts=1)
            ) as store:
                for number in range(10):
                    foreign = replace(context, identifier=f"{number:064x}")
                    assert not (
                        await store.recovery_status(context=foreign)
                    ).has_pending_work
                    assert await store.pending_batch(context=foreign) is None
                assert list((tmp_path / "state").glob("notification-*.lock")) == []
                assert (
                    await store.bootstrap(
                        NotificationBootstrap(context, (), ()), context=context
                    )
                ).imported
                assert (await store.recovery_status(context=context)).initialized

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["recovery_status", "pending_batch"])
def test_cancelled_recovery_joins_worker_and_leaves_original_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    async def scenario() -> None:
        entered, release = threading.Event(), threading.Event()
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            async with NotificationStore(tmp_path / "state") as store:
                imported = await store.bootstrap(
                    NotificationBootstrap(
                        context,
                        (),
                        (
                            RecentScheduleEvent(
                                "fixture date", "fixture type", "private fixture event"
                            ),
                        ),
                    ),
                    context=context,
                )
                original = store._recovery

                def hold(*args: Any) -> Any:
                    result = original(*args)
                    entered.set()
                    if not release.wait(5):
                        raise TimeoutError("Original fixture barrier")
                    return result

                monkeypatch.setattr(store, "_recovery", hold)
                task = asyncio.create_task(getattr(store, operation)(context=context))
                try:
                    assert await asyncio.to_thread(entered.wait, 5)
                    for _ in range(4):
                        task.cancel()
                        await asyncio.sleep(0)
                    assert not task.done()
                finally:
                    release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
                monkeypatch.setattr(store, "_recovery", original)
                assert await store.pending_batch(context=context) == imported.pending
                assert imported.pending is not None
                status = await store.recovery_status(context=context)
                assert (
                    status.pending is not None
                    and status.pending.receipt == imported.pending.receipt
                )
                assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())
