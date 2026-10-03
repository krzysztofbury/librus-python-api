"""Durable notification save/cancel/import faults using real native loopback."""

import asyncio
import base64
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import NotificationCategory
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import (
    NotificationLimits,
    NotificationStore,
    NotificationWorkflow,
)
from tests.http_support import serve
from tests.notification_persistence_support import NotificationWorkflowFixture
from tests.notifications_support import event_row, events_html

AGENDA = (NotificationCategory.AGENDA,)


@pytest.mark.parametrize("commit", [False, True])
def test_checkpoint_failure_preserves_raw_or_conservative_consume_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commit: bool
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(tmp_path / "state") as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    original = store._checkpoint

                    def fail(*args: Any) -> None:
                        if commit:
                            original(*args)
                        raise OSError("Original private fixture path")

                    monkeypatch.setattr(store, "_checkpoint", fail)
                    with pytest.raises(LibrusError) as error:
                        await workflow.poll(
                            categories=AGENDA, allow_consume_events=True
                        )
                    assert error.value.kind is ErrorKind.CHECKPOINT
                    monkeypatch.setattr(store, "_checkpoint", original)
                    record = json.loads(
                        (
                            await store.export_archive(context=workflow.client.context)
                        ).payload
                    )
                    assert (record["raw"] is not None) is commit
                    assert (record["reservation"] is not None) is (not commit)
                    before = len(fixture.calls)
                    if commit:
                        batch = await workflow.poll(categories=AGENDA)
                        assert batch.items and len(fixture.calls) == before
                    else:
                        with pytest.raises(LibrusError) as error:
                            await workflow.poll(
                                categories=AGENDA, allow_consume_events=True
                            )
                        assert error.value.kind is ErrorKind.CHECKPOINT
                        with pytest.raises(LibrusError):
                            await store.resolve_uncertain_consume(
                                context=workflow.client.context
                            )
                        assert len(fixture.calls) == before
                        await store.resolve_uncertain_consume(
                            context=workflow.client.context, accept_possible_loss=True
                        )
                        resolved = json.loads(
                            (
                                await store.export_archive(
                                    context=workflow.client.context
                                )
                            ).payload
                        )
                        assert resolved["reservation"] is None
                        with pytest.raises(LibrusError):
                            await workflow.poll(categories=AGENDA)
                        assert len(fixture.calls) == before
                    assert fixture.calls_by_account == ["student"]

    asyncio.run(scenario())


@pytest.mark.parametrize("commit", [False, True])
def test_acknowledgement_failure_preserves_batch_or_inspectable_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commit: bool
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(tmp_path / "state") as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    batch = await workflow.poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                    original = store._ack

                    def fail(*args: Any) -> None:
                        if commit:
                            original(*args)
                        raise OSError("Original private fixture save")

                    monkeypatch.setattr(store, "_ack", fail)
                    with pytest.raises(LibrusError) as error:
                        await workflow.acknowledge(batch.receipt)
                    assert error.value.kind is ErrorKind.STORAGE
                    assert error.value.__context__ is None
                    monkeypatch.setattr(store, "_ack", original)
                    state = await store.state(context=workflow.client.context)
                    assert state.initialized is commit
                    before = len(fixture.calls)
                    if not commit:
                        assert await workflow.poll(categories=AGENDA) == batch
                    await workflow.acknowledge(batch.receipt)
                    assert len(fixture.calls) == before
                    cleaned = json.loads(
                        (
                            await store.export_archive(context=workflow.client.context)
                        ).payload
                    )
                    assert cleaned["raw"] is None and cleaned["delivery"] is None

    asyncio.run(scenario())


@pytest.mark.parametrize("boundary", ["checkpoint", "delivery", "acknowledgement"])
@pytest.mark.parametrize("interruption", ["cancel", "shutdown"])
def test_repeated_cancellation_and_shutdown_join_durable_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str, interruption: str
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        entered, release = threading.Event(), threading.Event()
        directory = tmp_path / "state"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(directory) as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    if boundary == "acknowledgement":
                        batch = await workflow.poll(
                            categories=AGENDA, allow_consume_events=True
                        )
                    method = {
                        "checkpoint": "_checkpoint",
                        "delivery": "_stage",
                        "acknowledgement": "_ack",
                    }[boundary]
                    original = getattr(store, method)

                    def hold(*args: Any) -> None:
                        original(*args)
                        entered.set()
                        if not release.wait(5):
                            raise TimeoutError("Original fixture barrier")

                    monkeypatch.setattr(store, method, hold)
                    operation = (
                        workflow.poll(categories=AGENDA, allow_consume_events=True)
                        if boundary != "acknowledgement"
                        else workflow.acknowledge(batch.receipt)
                    )
                    task = asyncio.create_task(operation)
                    closing: asyncio.Task[None] | None = None
                    try:
                        assert await asyncio.to_thread(entered.wait, 5)
                        if interruption == "shutdown":
                            closing = asyncio.create_task(store.aclose())
                        else:
                            for _ in range(4):
                                task.cancel()
                                await asyncio.sleep(0)
                        await asyncio.sleep(0)
                        assert not task.done()
                    finally:
                        release.set()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    if closing is not None:
                        await asyncio.wait_for(closing, 5)
                before = len(fixture.calls)
                async with NotificationStore(directory) as reopened:
                    recovered = NotificationWorkflow(workflow.client, reopened)
                    if boundary != "acknowledgement":
                        replay = await recovered.poll(categories=AGENDA)
                        assert replay.items and replay.first_run
                        await recovered.acknowledge(replay.receipt)
                    assert (
                        await reopened.state(context=workflow.client.context)
                    ).initialized
                assert len(fixture.calls) == before
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("commit", [False, True])
def test_delivery_save_failure_retains_raw_or_replayable_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit: bool,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(tmp_path / "state") as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    original = store._stage

                    def fail(*args: Any) -> None:
                        if commit:
                            original(*args)
                        raise OSError("Original fixture staging error")

                    monkeypatch.setattr(store, "_stage", fail)
                    with pytest.raises(LibrusError) as error:
                        await workflow.poll(
                            categories=AGENDA, allow_consume_events=True
                        )
                    assert error.value.kind is ErrorKind.STORAGE
                    monkeypatch.setattr(store, "_stage", original)
                    archive = json.loads(
                        (
                            await store.export_archive(context=workflow.client.context)
                        ).payload
                    )
                    assert archive["raw"] is not None
                    assert (archive["delivery"] is not None) is commit
                    before = len(fixture.calls)
                    replay = await workflow.poll(categories=AGENDA)
                    if commit:
                        assert replay.receipt == archive["delivery"]["batch"]["receipt"]
                    assert len(replay.items) == 1
                    await workflow.acknowledge(replay.receipt)
                    assert len(fixture.calls) == before

    asyncio.run(scenario())


@pytest.mark.parametrize("initialized", [False, True])
def test_archive_context_binding_includes_empty_and_seen_only_state(
    tmp_path: Path,
    initialized: bool,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student", "parent")) as service:
                context = service.account("student").context
                async with NotificationStore(tmp_path / "source") as source:
                    if initialized:
                        workflow = NotificationWorkflow(
                            service.account("student"), source
                        )
                        batch = await workflow.poll(
                            categories=(NotificationCategory.GRADES,)
                        )
                        await workflow.acknowledge(batch.receipt)
                    archive = await source.export_archive(context=context)
                before = len(fixture.calls)
                async with NotificationStore(tmp_path / "target") as target:
                    with pytest.raises(LibrusError):
                        await target.import_archive(
                            replace(archive, context=service.account("parent").context)
                        )
                    assert not (await target.state(context=context)).initialized
                    await target.import_archive(archive)
                    assert (
                        await target.state(context=context)
                    ).initialized is initialized
                assert len(fixture.calls) == before

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid",
    [
        (),
        [NotificationCategory.AGENDA],
        ("agenda",),
        (NotificationCategory.AGENDA, NotificationCategory.AGENDA),
    ],
)
def test_invalid_categories_fail_before_transport(tmp_path: Path, invalid: Any) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            async with NotificationStore(tmp_path / "state") as store:
                workflow = NotificationWorkflow(service.account("student"), store)
                with pytest.raises(LibrusError) as error:
                    await workflow.poll(categories=invalid, allow_consume_events=True)
                assert (
                    error.value.kind is ErrorKind.INVALID_INPUT and fixture.calls == []
                )

    asyncio.run(scenario())


def test_ordinary_read_failure_and_capacity_refusal_do_not_consume(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.failures["grades"] = [403]
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                async with NotificationStore(tmp_path / "normal") as store:
                    workflow = NotificationWorkflow(service.account("student"), store)
                    with pytest.raises(LibrusError):
                        await workflow.poll(
                            categories=(NotificationCategory.GRADES, *AGENDA),
                            allow_consume_events=True,
                        )
                    record = json.loads(
                        (
                            await store.export_archive(context=workflow.client.context)
                        ).payload
                    )
                    assert (
                        record["raw"]
                        is record["delivery"]
                        is record["reservation"]
                        is None
                    )
                    assert not record["state"]["initialized"]
                before = len(fixture.calls)
                async with NotificationStore(
                    tmp_path / "full", limits=NotificationLimits(checkpoint_bytes=1)
                ) as store:
                    with pytest.raises(LibrusError) as error:
                        await NotificationWorkflow(
                            service.account("student"), store
                        ).poll(categories=AGENDA, allow_consume_events=True)
                    assert error.value.kind is ErrorKind.LIMIT
                assert fixture.calls_by_account == [] and len(fixture.calls) == before

    asyncio.run(scenario())


def test_neutral_archive_roundtrip_staged_delivery_and_progress(tmp_path: Path) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.payload = events_html(
            "".join(event_row(f"Original {i}") for i in range(3))
        )
        limits = NotificationLimits(replay_events=1)
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with NotificationStore(
                    tmp_path / "original", limits=limits
                ) as original:
                    workflow = NotificationWorkflow(client, original)
                    first = await workflow.poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                    await workflow.acknowledge(first.receipt)
                    staged = await workflow.poll(categories=AGENDA)
                    archive = await original.export_archive(context=client.context)
                before = len(fixture.calls)
                async with NotificationStore(
                    tmp_path / "copy", limits=limits
                ) as copied:
                    await copied.import_archive(archive)
                    assert (
                        await copied.export_archive(context=client.context) == archive
                    )
                    replay = NotificationWorkflow(client, copied)
                    assert await replay.poll(categories=AGENDA) == staged
                    await replay.acknowledge(staged.receipt)
                    last = await replay.poll(categories=AGENDA)
                    assert len(last.items) == 1 and not last.has_more_schedule
                    await replay.acknowledge(last.receipt)
                    before_import = await copied.export_archive(context=client.context)
                    with pytest.raises(LibrusError):
                        await copied.import_archive(archive)
                    assert (
                        await copied.export_archive(context=client.context)
                        == before_import
                    )
                assert len(fixture.calls) == before

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "damage", ["body", "total", "missing_event", "legacy_id", "version", "alias"]
)
def test_invalid_archive_import_rolls_back_without_state_reset(
    tmp_path: Path, damage: str
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with NotificationStore(tmp_path / "original") as original:
                    await NotificationWorkflow(client, original).poll(
                        categories=AGENDA, allow_consume_events=True
                    )
                    archive = await original.export_archive(context=client.context)
                record = json.loads(archive.payload)
                if damage == "body":
                    record["raw"]["body"] = base64.b64encode(
                        b"Changed original bytes"
                    ).decode()
                elif damage == "total":
                    record["delivery"] = None
                    record["raw"]["total"] = 0
                elif damage == "legacy_id":
                    record["state"]["initialized"] = True
                    record["state"]["seen"][0]["identifiers"] = [
                        "unmapped-original-legacy-id"
                    ]
                elif damage == "missing_event":
                    record["delivery"]["batch"]["items"] = []
                    record["delivery"]["state_after"]["seen"][4]["identifiers"] = []
                changed = replace(
                    archive,
                    payload=json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode(),
                )
                if damage == "version":
                    changed = replace(changed, version=2)
                if damage == "alias":
                    changed = replace(
                        changed, context=replace(client.context, alias="parent")
                    )
                before = len(fixture.calls)
                async with NotificationStore(tmp_path / "target") as target:
                    with pytest.raises(LibrusError):
                        await target.import_archive(changed)
                    assert not (await target.state(context=client.context)).initialized
                    restored = json.loads(
                        (await target.export_archive(context=client.context)).payload
                    )
                    assert (
                        restored["raw"]
                        is restored["delivery"]
                        is restored["reservation"]
                        is None
                    )
                assert len(fixture.calls) == before

    asyncio.run(scenario())
