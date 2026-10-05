"""Explicit retention and versioned store-local pseudonyms on actual SQLite."""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import NotificationCategory
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import (
    NotificationLimits,
    NotificationStore,
    NotificationWorkflow,
    PersistenceLimits,
    PersistenceStore,
)
from tests.http_support import serve
from tests.notification_persistence_support import NotificationWorkflowFixture
from tests.notifications_support import event_row, events_html
from tests.sending_support import SendFixture
from tests.test_persistence import prepare


def test_send_retention_frees_capacity_only_after_explicit_accepted_risk(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with PersistenceStore(
                    tmp_path / "state",
                    limits=PersistenceLimits(send_records=1, pending_confirmations=1),
                ) as store:
                    confirmation = await store.preview_send(prepare(client))
                    await store.execute_send(confirmation.token, prepare(client))
                    (record,) = await store.send_history(context=client.context)
                    with pytest.raises(LibrusError):
                        await store.prune_send_history(
                            context=client.context, identifiers=(record.identifier,)
                        )
                    with pytest.raises(LibrusError):
                        await store.preview_send(prepare(client))
                    before = len(fixture.calls)
                    assert (
                        await store.prune_send_history(
                            context=client.context,
                            identifiers=(record.identifier,),
                            allow_accepted=True,
                        )
                        == 1
                    )
                    assert await store.send_history(context=client.context) == ()
                    await store.preview_send(prepare(client))
                    assert len(fixture.calls) == before and len(fixture.send_calls) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["pending", "claimed", "unknown"])
def test_send_pruning_never_removes_live_or_uncertain_claims(
    tmp_path: Path, phase: str
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        directory = tmp_path / "state"
        async with fixture.service() as service:
            client = service.account("student")
            async with PersistenceStore(directory) as store:
                await store.preview_send(prepare(client))
                (record,) = await store.send_history(context=client.context)
                with sqlite3.connect(directory / "state.sqlite3") as connection:
                    connection.execute("UPDATE send_attempts SET status=?", (phase,))
                for accepted in (False, True):
                    with pytest.raises(LibrusError):
                        await store.prune_send_history(
                            context=client.context,
                            identifiers=(record.identifier,),
                            allow_accepted=accepted,
                        )
                assert (await store.send_history(context=client.context))[
                    0
                ].outcome.phase == phase
                assert fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["not_dispatched", "rejected", "invalidated"])
def test_safe_terminal_send_pruning_is_atomic_and_context_bound(
    tmp_path: Path, phase: str
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        directory = tmp_path / "state"
        async with fixture.service(("student", "parent")) as service:
            client = service.account("student")
            async with PersistenceStore(directory) as store:
                await store.preview_send(prepare(client))
                (record,) = await store.send_history(context=client.context)
                with sqlite3.connect(directory / "state.sqlite3") as connection:
                    connection.execute("UPDATE send_attempts SET status=?", (phase,))
                for context, ids in (
                    (client.context, (record.identifier, "0" * 64)),
                    (service.account("parent").context, (record.identifier,)),
                ):
                    with pytest.raises(LibrusError):
                        await store.prune_send_history(context=context, identifiers=ids)
                    assert len(await store.send_history(context=client.context)) == 1
                assert (
                    await store.prune_send_history(
                        context=client.context, identifiers=(record.identifier,)
                    )
                    == 1
                )
                await store.preview_send(prepare(client))
                assert fixture.calls == []

    asyncio.run(scenario())


def test_seen_retention_preserves_other_categories_and_requires_drained_recovery(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with NotificationStore(tmp_path / "state") as store:
                    workflow = NotificationWorkflow(client, store)
                    categories = (
                        NotificationCategory.GRADES,
                        NotificationCategory.ANNOUNCEMENTS,
                    )
                    batch = await workflow.poll(categories=categories)
                    grade = next(
                        item.identifier
                        for item in batch.items
                        if item.category is NotificationCategory.GRADES
                    )
                    with pytest.raises(LibrusError):
                        await store.prune_seen(
                            context=client.context,
                            category=NotificationCategory.GRADES,
                            identifiers=(grade,),
                        )
                    await workflow.acknowledge(batch.receipt)
                    before = await store.state(context=client.context)
                    with pytest.raises(LibrusError):
                        await store.prune_seen(
                            context=client.context,
                            category=NotificationCategory.GRADES,
                            identifiers=(grade, "0" * 64),
                        )
                    assert await store.state(context=client.context) == before
                    assert (
                        await store.prune_seen(
                            context=client.context,
                            category=NotificationCategory.GRADES,
                            identifiers=(grade,),
                        )
                        == 1
                    )
                    after = await store.state(context=client.context)
                    assert after.initialized and after.seen[0].identifiers == ()
                    assert after.seen[3] == before.seen[3]
                    again = await workflow.poll(categories=categories)
                    assert not again.first_run
                    assert [item.category for item in again.items] == [
                        NotificationCategory.GRADES
                    ]

    asyncio.run(scenario())


@pytest.mark.parametrize("identifiers", [((),), (), ("invalid",), ("0" * 64, "0" * 64)])
def test_invalid_prune_selection_fails_without_http(
    tmp_path: Path, identifiers: Any
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            context = service.account("student").context
            async with PersistenceStore(tmp_path / "send") as send:
                with pytest.raises(LibrusError) as error:
                    await send.prune_send_history(
                        context=context, identifiers=identifiers
                    )
                assert error.value.kind is ErrorKind.INVALID_INPUT
            async with NotificationStore(tmp_path / "notifications") as notifications:
                with pytest.raises(LibrusError) as error:
                    await notifications.prune_seen(
                        context=context,
                        category=NotificationCategory.GRADES,
                        identifiers=identifiers,
                    )
                assert error.value.kind is ErrorKind.INVALID_INPUT
            assert fixture.calls == []

    asyncio.run(scenario())


def test_expired_unused_confirmation_is_prunable_without_accepting_send_risk(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        directory = tmp_path / "state"
        async with fixture.service() as service:
            client = service.account("student")
            async with PersistenceStore(directory) as store:
                await store.preview_send(prepare(client))
                (record,) = await store.send_history(context=client.context)
                with sqlite3.connect(directory / "state.sqlite3") as connection:
                    connection.execute(
                        "UPDATE send_attempts SET created_at=1,expires_at=301"
                    )
                assert (
                    await store.prune_send_history(
                        context=client.context, identifiers=(record.identifier,)
                    )
                    == 1
                )
                assert await store.send_history(context=client.context) == ()
                assert fixture.calls == []

    asyncio.run(scenario())


def test_context_salts_are_durable_independent_and_not_leaked_as_plain_context(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                keys = []
                for name in ("first", "second"):
                    directory = tmp_path / name
                    async with NotificationStore(directory) as store:
                        key = store.context_identifier(client.context.identifier)
                        keys.append(key)
                        batch = await NotificationWorkflow(client, store).poll(
                            categories=(NotificationCategory.AGENDA,),
                            allow_consume_events=True,
                        )
                        assert batch.context == client.context
                        archive = await store.export_archive(context=client.context)
                        assert archive.version == 3
                        assert client.context.identifier.encode() not in archive.payload
                    assert (
                        client.context.identifier.encode()
                        not in (directory / "notifications.sqlite3").read_bytes()
                    )
                    assert (directory / f"notification-{key}.lock").exists()
                    async with NotificationStore(directory) as store:
                        assert (
                            store.context_identifier(client.context.identifier) == key
                        )
                        assert (
                            await NotificationWorkflow(client, store).poll(
                                categories=(NotificationCategory.AGENDA,)
                            )
                            == batch
                        )
                assert keys[0] != keys[1]
                async with PersistenceStore(tmp_path / "send") as store:
                    await store.preview_send(prepare(client))
                assert (
                    client.context.identifier.encode()
                    not in (tmp_path / "send" / "state.sqlite3").read_bytes()
                )

    asyncio.run(scenario())


def test_seen_saturation_can_prune_and_replay_retained_raw_without_reconsuming(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(
            event_row("Original old one") + event_row("Original old two")
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with NotificationStore(
                    tmp_path / "state",
                    limits=NotificationLimits(seen_ids_per_category=2, batch_items=1),
                ) as store:
                    workflow = NotificationWorkflow(client, store)
                    categories = (NotificationCategory.AGENDA,)
                    old = []
                    for _ in range(2):
                        batch = await workflow.poll(
                            categories=categories, allow_consume_events=True
                        )
                        old.append(batch.items[0].identifier)
                        await workflow.acknowledge(batch.receipt)
                    fixture.payload = events_html(
                        event_row("Original new one") + event_row("Original new two")
                    )
                    for index in range(2):
                        with pytest.raises(LibrusError) as error:
                            await workflow.poll(
                                categories=categories, allow_consume_events=True
                            )
                        assert error.value.kind is ErrorKind.LIMIT
                        before = json.loads(
                            (await store.export_archive(context=client.context)).payload
                        )
                        assert before["raw"]["cursor"] == index
                        requests = len(fixture.calls)
                        assert (
                            await store.prune_seen(
                                context=client.context,
                                category=NotificationCategory.AGENDA,
                                identifiers=(old[index],),
                            )
                            == 1
                        )
                        after = json.loads(
                            (await store.export_archive(context=client.context)).payload
                        )
                        assert after["raw"] == before["raw"]
                        batch = await workflow.poll(categories=categories)
                        assert len(fixture.calls) == requests
                        assert len(batch.items) == 1
                        await workflow.acknowledge(batch.receipt)
                        if index == 0:
                            state = await store.state(context=client.context)
                            with pytest.raises(LibrusError) as protected:
                                await store.prune_seen(
                                    context=client.context,
                                    category=NotificationCategory.AGENDA,
                                    identifiers=(batch.items[0].identifier,),
                                )
                            assert protected.value.kind is ErrorKind.INVALID_INPUT
                            assert await store.state(context=client.context) == state
                            async with NotificationStore(tmp_path / "copy") as copied:
                                await copied.import_archive(
                                    await store.export_archive(context=client.context)
                                )
                                assert (
                                    await copied.state(context=client.context) == state
                                )
                    assert len(fixture.calls_by_account) == 2
                    assert (
                        json.loads(
                            (await store.export_archive(context=client.context)).payload
                        )["raw"]
                        is None
                    )

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", [PersistenceStore, NotificationStore])
@pytest.mark.parametrize("version", [1, 2])
def test_previous_schema_is_not_silently_migrated_or_reset(
    tmp_path: Path, kind: type, version: int
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "state"
        async with kind(directory):
            pass
        filename = (
            "state.sqlite3" if kind is PersistenceStore else "notifications.sqlite3"
        )
        with sqlite3.connect(directory / filename) as connection:
            connection.execute(f"PRAGMA user_version={version}")
        original = (directory / filename).read_bytes()
        with pytest.raises(LibrusError) as error:
            async with kind(directory):
                pass
        assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
        assert (directory / filename).read_bytes() == original

    asyncio.run(scenario())
