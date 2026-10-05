"""Maximum accepted loads, bounded overflow and send/notification isolation."""

import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from librus_python_api import (
    NotificationCategory,
    RecipientReference,
    RequestBudget,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import (
    NotificationLimits,
    NotificationStore,
    NotificationWorkflow,
    PersistenceStore,
)
from tests.http_support import serve
from tests.notification_persistence_support import NotificationWorkflowFixture
from tests.notifications_support import event_row, events_html

AGENDA = (NotificationCategory.AGENDA,)


def test_four_maximum_batches_share_exact_traffic_budget_and_isolated_state(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(
            "".join(event_row(f"Original full event {i}") for i in range(1024))
        )
        aliases = ("student", "parent", "second-student", "second-parent")
        limits = NotificationLimits(
            checkpoint_bytes=32 * 1024 * 1024,
            batch_items=1024,
            replay_events=1024,
            replay_bytes=1024 * 1024,
            batch_bytes=2 * 1024 * 1024,
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(aliases) as service:
                async with NotificationStore(
                    tmp_path / "state", limits=limits
                ) as store:
                    workflows = [
                        NotificationWorkflow(service.account(alias), store)
                        for alias in aliases
                    ]
                    budget = RequestBudget(
                        max_requests=24, max_response_bytes=2 * 1024 * 1024
                    )
                    batches = await asyncio.gather(
                        *(
                            workflow.poll(
                                categories=AGENDA,
                                allow_consume_events=True,
                                budget=budget,
                            )
                            for workflow in workflows
                        )
                    )
                    assert budget.requests_dispatched == 24
                    assert all(
                        len(batch.items) == 1024 and not batch.has_more_schedule
                        for batch in batches
                    )
                    assert len({batch.receipt for batch in batches}) == 4
                    for alias, batch in zip(aliases, batches, strict=True):
                        assert all(
                            item.identity is not None
                            and item.identity.owner.id == alias
                            for item in batch.items
                        )
                    await asyncio.gather(
                        *(
                            workflow.acknowledge(batch.receipt)
                            for workflow, batch in zip(workflows, batches, strict=True)
                        )
                    )
                    states = await asyncio.gather(
                        *(
                            store.state(context=workflow.client.context)
                            for workflow in workflows
                        )
                    )
                    assert all(
                        state.initialized and len(state.seen[4].identifiers) == 1024
                        for state in states
                    )
                    assert fixture.logins == dict.fromkeys(aliases, 1)
                    assert sorted(fixture.calls_by_account) == sorted(aliases)
                    assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_maximum_wire_checkpoint_and_global_capacity_refuse_next_consume(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = b" " * (4 * 1024 * 1024)
        directory = tmp_path / "state"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student", "parent")) as service:
                async with NotificationStore(
                    directory,
                    limits=NotificationLimits(checkpoint_bytes=8 * 1024 * 1024),
                ) as store:
                    with pytest.raises(LibrusError):
                        await NotificationWorkflow(
                            service.account("student"), store
                        ).poll(
                            categories=AGENDA,
                            allow_consume_events=True,
                            budget=RequestBudget(max_response_bytes=8 * 1024 * 1024),
                        )
                    with sqlite3.connect(
                        directory / "notifications.sqlite3"
                    ) as connection:
                        body = connection.execute(
                            "SELECT body FROM notification_raw"
                        ).fetchone()[0]
                    assert len(body) == 4 * 1024 * 1024
                    assert (
                        hashlib.sha256(body).digest()
                        == hashlib.sha256(fixture.payload).digest()
                    )
                    before = len(fixture.calls)
                    with pytest.raises(LibrusError) as error:
                        await NotificationWorkflow(
                            service.account("parent"), store
                        ).poll(categories=AGENDA, allow_consume_events=True)
                    assert (
                        error.value.kind is ErrorKind.LIMIT
                        and len(fixture.calls) == before
                    )
                    assert fixture.calls_by_account == ["student"]

    asyncio.run(scenario())


def test_saturated_workflows_and_incomplete_receipt_keep_uncertainty(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.body_hold = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student", "parent")) as service:
                async with NotificationStore(
                    tmp_path / "state", limits=NotificationLimits(operations=1)
                ) as store:
                    first = NotificationWorkflow(service.account("student"), store)
                    task = asyncio.create_task(
                        first.poll(categories=AGENDA, allow_consume_events=True)
                    )
                    try:
                        await asyncio.wait_for(fixture.pending.wait(), 5)
                        before = len(fixture.calls)
                        with pytest.raises(LibrusError) as error:
                            await NotificationWorkflow(
                                service.account("parent"), store
                            ).poll(categories=AGENDA, allow_consume_events=True)
                        assert error.value.kind is ErrorKind.LIMIT
                        task.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await task
                        with pytest.raises(LibrusError) as error:
                            await first.poll(
                                categories=AGENDA, allow_consume_events=True
                            )
                        assert error.value.kind is ErrorKind.CHECKPOINT
                        assert len(fixture.calls) == before
                    finally:
                        fixture.body_hold.set()
                    assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_seen_overflow_preserves_raw_for_explicit_larger_limits(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(
            event_row("Original first") + event_row("Original second")
        )
        directory = tmp_path / "state"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with NotificationStore(
                    directory, limits=NotificationLimits(seen_ids_per_category=1)
                ) as store:
                    with pytest.raises(LibrusError) as error:
                        await NotificationWorkflow(client, store).poll(
                            categories=AGENDA, allow_consume_events=True
                        )
                    assert error.value.kind is ErrorKind.LIMIT
                    record = json.loads(
                        (await store.export_archive(context=client.context)).payload
                    )
                    assert record["raw"] is not None and record["delivery"] is None
                    assert not record["state"]["initialized"]
                before = len(fixture.calls)
                async with NotificationStore(
                    directory, limits=NotificationLimits(seen_ids_per_category=2)
                ) as store:
                    workflow = NotificationWorkflow(client, store)
                    batch = await workflow.poll(categories=AGENDA)
                    assert len(batch.items) == 2
                    await workflow.acknowledge(batch.receipt)
                assert len(fixture.calls) == before

    asyncio.run(scenario())


def test_duplicate_rows_do_not_duplicate_delivery_or_change_send_state(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(event_row() * 1024)
        directory = tmp_path / "state"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with PersistenceStore(directory) as sends:
                    confirmation = await sends.preview_send(
                        client.prepare_send(
                            recipients=(
                                RecipientReference("101", "student", "nauczyciel"),
                            ),
                            subject="Original subject",
                            body="Original body",
                        )
                    )
                before = (directory / "state.sqlite3").read_bytes()
                async with NotificationStore(directory) as notifications:
                    workflow = NotificationWorkflow(client, notifications)
                    batch = await workflow.poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                    assert len(batch.items) == 1 and not batch.has_more_schedule
                    await workflow.acknowledge(batch.receipt)
                    again = await workflow.poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                    assert again.items == () and not again.first_run
                    await workflow.acknowledge(again.receipt)
                assert (directory / "state.sqlite3").read_bytes() == before
                async with PersistenceStore(directory) as sends:
                    assert (
                        await sends.send_outcome(
                            confirmation.token, context=client.context
                        )
                    ).phase == "pending"
                assert fixture.calls_by_account == ["student", "student"]

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["lock_symlink", "raw_digest", "schema"])
def test_notification_specific_corruption_fails_closed_before_http(
    tmp_path: Path, damage: str
) -> None:
    if os.name == "nt" and damage == "lock_symlink":
        pytest.skip("POSIX symlink; Windows lock reparse case is separate")

    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        directory = tmp_path / "state"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with NotificationStore(directory) as store:
                    await NotificationWorkflow(client, store).poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                if damage == "lock_symlink":
                    lock = next(directory.glob("notification-*.lock"))
                    lock.unlink()
                    target = tmp_path / "untouched"
                    target.write_bytes(b"Original bytes")
                    lock.symlink_to(target)
                else:
                    with sqlite3.connect(
                        directory / "notifications.sqlite3"
                    ) as connection:
                        connection.execute(
                            "UPDATE notification_raw SET body=x'31'"
                            if damage == "raw_digest"
                            else "CREATE TRIGGER arbitrary AFTER UPDATE ON "
                            "notification_state BEGIN SELECT 1; END"
                        )
                before = len(fixture.calls)
                with pytest.raises(LibrusError):
                    async with NotificationStore(directory) as reopened:
                        await NotificationWorkflow(client, reopened).poll(
                            categories=AGENDA, allow_consume_events=True
                        )
                assert len(fixture.calls) == before
                if damage == "lock_symlink":
                    assert target.read_bytes() == b"Original bytes"

    asyncio.run(scenario())
