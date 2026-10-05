"""Neutral offline import preserves mapped baselines and explicit missing provenance."""

import asyncio
import hashlib
import json
import sqlite3
import sys
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import NotificationCategory, RecentScheduleEvent, RequestBudget
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import (
    NotificationBaselineMapping,
    NotificationBootstrap,
    NotificationLimits,
    NotificationProvenance,
    NotificationStore,
    NotificationWorkflow,
)
from tests.test_notification_persistence import offline_service

AGENDA = (NotificationCategory.AGENDA,)
EVENT = RecentScheduleEvent("fixture date", "fixture type", "fixture α\nline")
EVENT_ID = hashlib.sha256(
    b'{"data":"fixture \xce\xb1\\nline","date_added":"fixture date",'
    b'"type":"fixture type"}'
).hexdigest()


def test_imported_history_restart_archive_replay_and_ack_need_no_http(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            client = service.account("student")
            mappings = tuple(
                NotificationBaselineMapping(
                    category, "external fixture id", str(index + 1) * 64
                )
                for index, category in enumerate(NotificationCategory)
            )
            plan = NotificationBootstrap(client.context, mappings, (EVENT,))
            directory = tmp_path / "state"
            async with NotificationStore(directory) as store:
                result = await store.bootstrap(plan, context=client.context)
                assert result.imported and result.unmapped == ()
                batch = result.pending
                assert batch is not None and not batch.first_run
                assert batch.items[0].identifier == EVENT_ID
                assert batch.items[0].value == EVENT
                assert batch.items[0].identity is None
                assert batch.items[0].observation is None
                assert (
                    batch.items[0].provenance is NotificationProvenance.IMPORTED_HISTORY
                )
                state = await store.state(context=client.context)
                assert state.initialized
                assert tuple(entry.identifiers for entry in state.seen) == tuple(
                    (mapping.native_identifier,) for mapping in mappings
                )
                archive = await store.export_archive(context=client.context)
                with pytest.raises(LibrusError) as error:
                    await store.bootstrap(plan, context=client.context)
                assert error.value.kind is ErrorKind.INVALID_INPUT
            for target in (directory, tmp_path / "restored"):
                async with NotificationStore(target) as reopened:
                    if target != directory:
                        await reopened.import_archive(archive)
                    workflow = NotificationWorkflow(client, reopened)
                    budget = RequestBudget(max_requests=1)
                    assert (
                        await workflow.poll(categories=AGENDA, budget=budget) == batch
                    )
                    assert budget.requests_dispatched == 0
                    await workflow.acknowledge(batch.receipt)
                    await workflow.acknowledge(batch.receipt)
                    acknowledged = await reopened.state(context=client.context)
                    expected = tuple(
                        replace(entry, identifiers=(*entry.identifiers, EVENT_ID))
                        if entry.category is NotificationCategory.AGENDA
                        else entry
                        for entry in state.seen
                    )
                    assert acknowledged.seen == expected
                    with pytest.raises(LibrusError):
                        await reopened.bootstrap(plan, context=client.context)
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "damage",
    [
        "context",
        "category",
        "source",
        "native",
        "duplicate_source",
        "collision",
        "event",
        "duplicate_event",
        "already_seen",
    ],
)
def test_malformed_or_ambiguous_plan_cannot_seed_a_baseline(
    tmp_path: Path, damage: str
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            mapping = NotificationBaselineMapping(
                NotificationCategory.GRADES, "fixture external", "a" * 64
            )
            plan = NotificationBootstrap(context, (mapping,), (EVENT,))
            if damage == "context":
                plan = replace(plan, context=replace(context, identifier="b" * 64))
            elif damage == "category":
                plan = replace(plan, mappings=(replace(mapping, category="unknown"),))  # type: ignore[arg-type]
            elif damage == "source":
                plan = replace(plan, mappings=(replace(mapping, source_identifier=""),))
            elif damage == "native":
                plan = replace(
                    plan,
                    mappings=(replace(mapping, native_identifier="not-a-native-id"),),
                )
            elif damage == "duplicate_source":
                plan = replace(
                    plan,
                    mappings=(mapping, replace(mapping, native_identifier="b" * 64)),
                )
            elif damage == "collision":
                plan = replace(
                    plan,
                    mappings=(
                        mapping,
                        replace(mapping, source_identifier="other external"),
                    ),
                )
            elif damage == "event":
                plan = replace(plan, pending_events=(replace(EVENT, type=""),))
            elif damage == "duplicate_event":
                plan = replace(plan, pending_events=(EVENT, EVENT))
            else:
                plan = replace(
                    plan,
                    mappings=(
                        NotificationBaselineMapping(
                            NotificationCategory.AGENDA, "already seen", EVENT_ID
                        ),
                    ),
                )
            async with NotificationStore(tmp_path / "state") as store:
                with pytest.raises(LibrusError) as error:
                    await store.bootstrap(plan, context=context)
                assert error.value.kind is ErrorKind.INVALID_INPUT
                assert (
                    await store.bootstrap(
                        NotificationBootstrap(context, (), ()), context=context
                    )
                ).imported
                assert (await store.state(context=context)).initialized
                assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "limit", ["batch_items", "batch_bytes", "state_bytes", "seen_ids_per_category"]
)
def test_import_capacity_failure_leaves_no_partial_state_or_context(
    tmp_path: Path, limit: str
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            plan = NotificationBootstrap(
                context,
                (
                    NotificationBaselineMapping(
                        NotificationCategory.GRADES, "fixture baseline", "a" * 64
                    ),
                ),
                (EVENT,),
            )
            if limit == "batch_items":
                plan = replace(
                    plan, pending_events=(EVENT, replace(EVENT, data="other"))
                )
            elif limit == "seen_ids_per_category":
                plan = replace(
                    plan,
                    mappings=tuple(
                        NotificationBaselineMapping(
                            NotificationCategory.GRADES, f"fixture {i}", str(i) * 64
                        )
                        for i in (1, 2)
                    ),
                )
            directory = tmp_path / "state"
            async with NotificationStore(
                directory, limits=NotificationLimits(contexts=1, **{limit: 1})
            ) as store:
                with pytest.raises(LibrusError) as error:
                    await store.bootstrap(plan, context=context)
                assert error.value.kind is ErrorKind.LIMIT
            with sqlite3.connect(directory / "notifications.sqlite3") as db:
                for table in (
                    "notification_contexts",
                    "notification_state",
                    "notification_deliveries",
                ):
                    assert db.execute(f"SELECT count(*) FROM {table}").fetchone() == (
                        0,
                    )
            async with NotificationStore(directory) as reopened:
                assert (
                    await reopened.bootstrap(
                        NotificationBootstrap(context, (), (EVENT,)), context=context
                    )
                ).imported

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "damage",
    ["provenance", "missing_provenance", "observation", "raw_binding", "uncertainty"],
)
def test_historical_archive_cannot_invent_observation_or_native_raw_progress(
    tmp_path: Path, damage: str
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            async with NotificationStore(tmp_path / "source") as source:
                plan = NotificationBootstrap(context, (), (EVENT,))
                result = await source.bootstrap(plan, context=context)
                archive = await source.export_archive(context=context)
            record = json.loads(archive.payload)
            delivery = record["delivery"]
            item = delivery["batch"]["items"][0]["item"]
            if damage == "provenance":
                item["provenance"] = "observed"
            elif damage == "missing_provenance":
                item.pop("provenance")
            elif damage == "observation":
                item["observation"] = {
                    "account": "student",
                    "observed_at": "2026-10-01T00:00:00Z",
                    "session_generation": 0,
                    "source": "external fixture",
                }
            else:
                if damage == "raw_binding":
                    delivery["raw_identifier"] = "b" * 64
                else:
                    record["reservation"] = 1
            async with NotificationStore(tmp_path / "target") as target:
                with pytest.raises(LibrusError) as error:
                    await target.import_archive(
                        replace(archive, payload=json.dumps(record).encode())
                    )
                assert error.value.kind is ErrorKind.PARSE
                await target.import_archive(archive)
                assert (
                    await NotificationWorkflow(service.account("student"), target).poll(
                        categories=AGENDA
                    )
                    == result.pending
                )

    asyncio.run(scenario())


def test_failure_after_staging_rolls_back_the_whole_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            directory = tmp_path / "state"
            async with NotificationStore(directory) as store:
                original = store._delivery

                def fail(*args: Any) -> None:
                    assert original(*args) is not None
                    raise OSError("Original fixture commit barrier")

                monkeypatch.setattr(store, "_delivery", fail)
                plan = NotificationBootstrap(context, (), (EVENT,))
                with pytest.raises(LibrusError) as error:
                    await store.bootstrap(plan, context=context)
                assert error.value.kind is ErrorKind.STORAGE
                with sqlite3.connect(directory / "notifications.sqlite3") as db:
                    for table in (
                        "notification_contexts",
                        "notification_state",
                        "notification_deliveries",
                    ):
                        assert db.execute(
                            f"SELECT count(*) FROM {table}"
                        ).fetchone() == (0,)
                monkeypatch.setattr(store, "_delivery", original)
                assert (await store.bootstrap(plan, context=context)).imported

    asyncio.run(scenario())


@pytest.mark.parametrize("interruption", ["cancel", "shutdown"])
def test_interrupted_bootstrap_joins_commit_and_replays_the_original_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: str
) -> None:
    async def scenario() -> None:
        entered, release = threading.Event(), threading.Event()
        directory = tmp_path / "state"
        async with offline_service("http://127.0.0.1:9") as service:
            client = service.account("student")
            async with NotificationStore(directory) as store:
                original = store._bootstrap

                def hold(*args: Any) -> Any:
                    result = original(*args)
                    entered.set()
                    if not release.wait(5):
                        raise TimeoutError("Original fixture barrier")
                    return result

                monkeypatch.setattr(store, "_bootstrap", hold)
                plan = NotificationBootstrap(client.context, (), (EVENT,))
                task = asyncio.create_task(
                    store.bootstrap(plan, context=client.context)
                )
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
            async with NotificationStore(directory) as reopened:
                workflow = NotificationWorkflow(client, reopened)
                replay = await workflow.poll(categories=AGENDA)
                assert replay.items[0].value == EVENT and not replay.first_run
                assert await workflow.poll(categories=AGENDA) == replay
                with pytest.raises(LibrusError):
                    await reopened.bootstrap(plan, context=client.context)
                await workflow.acknowledge(replay.receipt)
                assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


def test_imported_history_is_recovered_and_acknowledged_in_a_fresh_process(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            directory = tmp_path / "state"
            async with NotificationStore(directory) as store:
                result = await store.bootstrap(
                    NotificationBootstrap(context, (), (EVENT,)), context=context
                )
                assert result.pending is not None
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "tests.notification_bootstrap_worker",
                str(directory),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), 10)
                assert process.returncode == 0 and stderr == b""
                assert json.loads(stdout) == {
                    "receipt": result.pending.receipt,
                    "identifier": EVENT_ID,
                    "event": {
                        "date_added": EVENT.date_added,
                        "type": EVENT.type,
                        "data": EVENT.data,
                    },
                    "requests": 0,
                }
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.communicate()
            async with NotificationStore(directory) as reopened:
                state = await reopened.state(context=context)
                assert next(
                    entry.identifiers
                    for entry in state.seen
                    if entry.category is NotificationCategory.AGENDA
                ) == (EVENT_ID,)
                with pytest.raises(LibrusError):
                    await NotificationWorkflow(
                        service.account("student"), reopened
                    ).poll(categories=AGENDA)

    asyncio.run(scenario())


def test_unmapped_baseline_is_reported_without_partial_import_or_fresh_reset(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            unknown = NotificationBaselineMapping(
                NotificationCategory.GRADES, "unmappable external id", None
            )
            plan = NotificationBootstrap(context, (unknown,), (EVENT,))
            async with NotificationStore(tmp_path / "state") as store:
                result = await store.bootstrap(plan, context=context)
                assert not result.imported and result.pending is None
                assert result.unmapped == (unknown,)
                assert not (await store.state(context=context)).initialized
                mapped = replace(
                    plan, mappings=(replace(unknown, native_identifier="a" * 64),)
                )
                assert (await store.bootstrap(mapped, context=context)).imported

    asyncio.run(scenario())
