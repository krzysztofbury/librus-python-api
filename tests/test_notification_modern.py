"""Explicit mailbox sources share durable delivery, never namespaces or fallback."""

import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    MessageSummary,
    MessagingBackend,
    ModernMessageSummary,
    NotificationCategory,
    RequestBudget,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import (
    NotificationLimits,
    NotificationStore,
    NotificationWorkflow,
    canonical_notification_id,
)
from tests.http_support import FIXTURE_SECRET
from tests.notification_persistence_support import NotificationWorkflowFixture
from tests.test_modern_communication import CommunicationFixture

MESSAGES = (NotificationCategory.MESSAGES,)


class ModernNotificationFixture(CommunicationFixture, NotificationWorkflowFixture):
    """Reuse original mailbox and schedule routes on the same native session."""


@pytest.mark.parametrize("backend", list(MessagingBackend))
def test_selected_mailbox_survives_restart_archive_and_offline_ack(
    tmp_path: Path, backend: MessagingBackend
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.message_count = 1
        directory = tmp_path / "source"
        async with fixture.running() as service:
            client = service.account("student")
            async with NotificationStore(directory) as store:
                workflow = NotificationWorkflow(client, store, messages_backend=backend)
                budget = RequestBudget(max_requests=9)
                batch = await workflow.poll(categories=MESSAGES, budget=budget)
                assert batch.messages_backend is backend
                assert batch.first_run and batch.items
                assert isinstance(batch.items[0].value, ModernMessageSummary) == (
                    backend is MessagingBackend.MODERN
                )
                assert all(
                    "/messages/" not in path for path, _, _ in fixture.modern_calls
                )
                mailbox = [
                    path
                    for path, _, _ in fixture.modern_calls
                    if path == "/api/inbox/messages"
                ]
                assert len(mailbox) == (1 if backend is MessagingBackend.MODERN else 0)
                assert fixture.count("messages_received") == (
                    1 if backend is MessagingBackend.LEGACY else 0
                )
                assert budget.requests_dispatched == (
                    9 if backend is MessagingBackend.MODERN else 6
                )
                assert not fixture.sends
                archive = await store.export_archive(context=client.context)
        before = len(fixture.calls) + len(fixture.modern_calls)
        async with LibrusService(
            context_key=bytes(range(32)),
            accounts={
                "student": AccountCredentials(login="student", password=FIXTURE_SECRET)
            },
            connection=ConnectionSettings(
                synergia_origin=fixture.origin,
                api_origin=fixture.origin,
                messages_origin=fixture.modern_origin,
            ),
        ) as offline:
            for target in (directory, tmp_path / "imported"):
                async with NotificationStore(target) as store:
                    if target != directory:
                        await store.import_archive(archive)
                    workflow = NotificationWorkflow(
                        offline.account("student"), store, messages_backend=backend
                    )
                    budget = RequestBudget(max_requests=1)
                    assert (
                        await workflow.poll(categories=MESSAGES, budget=budget) == batch
                    )
                    assert budget.requests_dispatched == 0
                    opposite = (
                        MessagingBackend.MODERN
                        if backend is MessagingBackend.LEGACY
                        else MessagingBackend.LEGACY
                    )
                    with pytest.raises(LibrusError) as error:
                        await NotificationWorkflow(
                            workflow.client, store, messages_backend=opposite
                        ).poll(categories=MESSAGES)
                    assert error.value.kind is ErrorKind.INVALID_INPUT
                    await workflow.acknowledge(batch.receipt)
                    state = await store.state(context=workflow.client.context)
                    assert next(
                        s.identifiers
                        for s in state.seen
                        if s.category is NotificationCategory.MESSAGES
                    ) == tuple(item.identifier for item in batch.items)
        assert len(fixture.calls) + len(fixture.modern_calls) == before

    asyncio.run(scenario())


def test_modern_and_legacy_same_reference_ids_cannot_share_seen_state(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.message_count = 1
        fixture.responses["/api/inbox/messages"] = (
            200,
            json.dumps({"data": [fixture.message(101)], "total": 1}).encode(),
            "application/json",
            {},
        )
        async with fixture.running() as service:
            client = service.account("student")
            async with NotificationStore(tmp_path / "state") as store:
                legacy = NotificationWorkflow(client, store)
                original = await legacy.poll(categories=MESSAGES)
                original_value = original.items[0].value
                assert isinstance(original_value, MessageSummary)
                await legacy.acknowledge(original.receipt)
                modern = NotificationWorkflow(
                    client, store, messages_backend=MessagingBackend.MODERN
                )
                result = await modern.poll(categories=MESSAGES)
                value = result.items[0].value
                assert isinstance(value, ModernMessageSummary)
                assert value.reference.identifier == original_value.reference.identifier
                assert (
                    canonical_notification_id(NotificationCategory.MESSAGES, value)
                    != original.items[0].identifier
                )
                assert result.items[0].identifier != original.items[0].identifier
                assert (
                    result.items[0].identifier
                    == hashlib.sha256(
                        b'[2,"messages","modern","received","101"]'
                    ).hexdigest()
                )
                await modern.acknowledge(result.receipt)
                assert (await legacy.poll(categories=MESSAGES)).items == ()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["parse", "capacity"])
def test_modern_failure_never_falls_back_or_initializes_seen_state(
    tmp_path: Path, failure: str
) -> None:
    async def scenario() -> None:
        fixture = ModernNotificationFixture()
        fixture.message_count = 2
        if failure == "parse":
            fixture.responses["/api/inbox/messages"] = (
                200,
                b'{"data":[],"total":2}',
                "application/json",
                {},
            )
        async with fixture.running() as service:
            async with NotificationStore(
                tmp_path / "state", limits=NotificationLimits(batch_items=1)
            ) as store:
                workflow = NotificationWorkflow(
                    service.account("student"),
                    store,
                    messages_backend=MessagingBackend.MODERN,
                )
                with pytest.raises(LibrusError) as error:
                    await workflow.poll(
                        categories=(*MESSAGES, NotificationCategory.AGENDA),
                        allow_consume_events=True,
                    )
                assert error.value.kind is (
                    ErrorKind.PARSE if failure == "parse" else ErrorKind.LIMIT
                )
                state = await store.state(context=workflow.client.context)
                assert not state.initialized and all(
                    not seen.identifiers for seen in state.seen
                )
                assert fixture.count("messages_received") == 0
                assert not fixture.sends
                assert fixture.calls_by_account == []

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["backend", "reference_account"])
def test_modern_archive_rejects_incompatible_source_atomically(
    tmp_path: Path, damage: str
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.message_count = 1
        async with fixture.running() as service:
            client = service.account("student")
            async with NotificationStore(tmp_path / "source") as source:
                workflow = NotificationWorkflow(
                    client, source, messages_backend=MessagingBackend.MODERN
                )
                batch = await workflow.poll(categories=MESSAGES)
                archive = await source.export_archive(context=client.context)
            record = json.loads(archive.payload)
            encoded = record["delivery"]["batch"]
            if damage == "backend":
                encoded["messages_backend"] = "legacy"
            else:
                encoded["items"][0]["item"]["value"]["reference"]["account"] = "parent"
            async with NotificationStore(tmp_path / "target") as target:
                with pytest.raises(LibrusError) as error:
                    await target.import_archive(
                        replace(archive, payload=json.dumps(record).encode())
                    )
                assert error.value.kind is ErrorKind.PARSE
                await target.import_archive(archive)
                assert (
                    await NotificationWorkflow(
                        client, target, messages_backend=MessagingBackend.MODERN
                    ).poll(categories=MESSAGES)
                    == batch
                )

    asyncio.run(scenario())


def test_modern_seen_ids_remain_independent_per_configured_login(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.message_count = 1
        async with fixture.running(("student", "parent")) as service:
            async with NotificationStore(tmp_path / "state") as store:
                batches = []
                for alias in ("student", "parent"):
                    workflow = NotificationWorkflow(
                        service.account(alias),
                        store,
                        messages_backend=MessagingBackend.MODERN,
                    )
                    batch = await workflow.poll(categories=MESSAGES)
                    assert batch.first_run and len(batch.items) == 1
                    identity = batch.items[0].identity
                    assert (
                        identity is not None and identity.observation.account == alias
                    )
                    await workflow.acknowledge(batch.receipt)
                    assert (await workflow.poll(categories=MESSAGES)).items == ()
                    batches.append(batch)
                assert batches[0].context != batches[1].context
                assert batches[0].items[0].identifier == batches[1].items[0].identifier

    asyncio.run(scenario())


def test_all_categories_with_modern_mailbox_use_one_shared_budget(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = ModernNotificationFixture()
        fixture.message_count = 1
        async with fixture.running() as service:
            async with NotificationStore(tmp_path / "state") as store:
                workflow = NotificationWorkflow(
                    service.account("student"),
                    store,
                    messages_backend=MessagingBackend.MODERN,
                )
                budget = RequestBudget(max_requests=14)
                batch = await workflow.poll(
                    categories=tuple(NotificationCategory),
                    allow_consume_events=True,
                    budget=budget,
                )
                assert {item.category for item in batch.items} == set(
                    NotificationCategory
                )
                assert budget.requests_dispatched == 14
                assert fixture.count("messages_received") == 0
                assert fixture.calls_by_account == ["student"]
                before = len(fixture.calls) + len(fixture.modern_calls)
                assert (
                    await workflow.poll(categories=tuple(NotificationCategory)) == batch
                )
                assert len(fixture.calls) + len(fixture.modern_calls) == before
                await workflow.acknowledge(batch.receipt)

    asyncio.run(scenario())


def test_existing_format_three_legacy_delivery_remains_importable(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            async with NotificationStore(tmp_path / "source") as source:
                batch = await NotificationWorkflow(client, source).poll(
                    categories=MESSAGES
                )
                archive = await source.export_archive(context=client.context)
            record = json.loads(archive.payload)
            record["delivery"]["batch"].pop("messages_backend")
            for item in record["delivery"]["batch"]["items"]:
                item["item"].pop("provenance")
            old = replace(archive, payload=json.dumps(record).encode())
            async with NotificationStore(tmp_path / "destination") as target:
                await target.import_archive(old)
                assert (
                    await NotificationWorkflow(client, target).poll(categories=MESSAGES)
                    == batch
                )

    asyncio.run(scenario())
