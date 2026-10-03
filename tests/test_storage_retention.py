"""Explicit retention and versioned store-local pseudonyms on actual SQLite."""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import NotificationCategory
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import (
    NotificationStore,
    NotificationWorkflow,
    PersistenceLimits,
    PersistenceStore,
)
from tests.http_support import serve
from tests.notification_persistence_support import NotificationWorkflowFixture
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
                        assert archive.version == 2
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


@pytest.mark.parametrize("kind", [PersistenceStore, NotificationStore])
def test_previous_unsalted_schema_is_not_silently_migrated_or_reset(
    tmp_path: Path, kind: type
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "state"
        async with kind(directory):
            pass
        filename = (
            "state.sqlite3" if kind is PersistenceStore else "notifications.sqlite3"
        )
        with sqlite3.connect(directory / filename) as connection:
            connection.execute("PRAGMA user_version=1")
        original = (directory / filename).read_bytes()
        with pytest.raises(LibrusError) as error:
            async with kind(directory):
                pass
        assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
        assert (directory / filename).read_bytes() == original

    asyncio.run(scenario())
