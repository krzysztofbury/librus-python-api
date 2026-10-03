"""Optional public workflows with original payloads and disposable real SQLite."""

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import (
    AccountClient,
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    RecipientReference,
    RequestBudget,
    SendAttempt,
    SendStatus,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import PersistenceLimits, PersistenceStore
from tests.http_support import FIXTURE_SECRET, serve
from tests.sending_support import SendFixture, acknowledgement


def prepare(client: AccountClient, **changes: Any) -> SendAttempt:
    return client.prepare_send(
        **(
            {
                "recipients": (RecipientReference("101", "student", "nauczyciel"),),
                "subject": "Original fixture subject",
                "body": "Original fixture body",
            }
            | changes
        )
    )


def persisted(directory: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(directory / "state.sqlite3") as connection:
        return connection.execute("SELECT * FROM send_attempts").fetchall()


class ClaimCrashFixture(SendFixture):
    async def portal(self, request: web.Request) -> web.Response:
        response = await super().portal(request)
        # The durable claim has committed; no credentials or send reached wire.
        self.send_started.set()
        assert self.send_hold is not None
        await self.send_hold.wait()
        return response


@pytest.mark.parametrize("tampering", ["trigger", "journal_symlink"])
def test_unsafe_existing_storage_stops_before_network(
    tmp_path: Path, tampering: str
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "state"
        async with PersistenceStore(directory):
            pass
        target = tmp_path / "untouched"
        target.write_bytes(b"original bytes")
        if tampering == "trigger":
            with sqlite3.connect(directory / "state.sqlite3") as connection:
                connection.execute("""CREATE TRIGGER reset_claim AFTER UPDATE
                    ON send_attempts WHEN NEW.status='claimed' BEGIN
                    UPDATE send_attempts SET status='pending'
                    WHERE token_hash=NEW.token_hash; END""")
        else:
            (directory / "state.sqlite3-journal").symlink_to(target)
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                with pytest.raises(LibrusError):
                    async with PersistenceStore(directory) as store:
                        await store.preview_send(prepare(service.account("student")))
                assert fixture.calls == []
        assert target.read_bytes() == b"original bytes"

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", [{}, False, 0])
def test_invalid_store_limits_are_not_silently_defaulted(
    tmp_path: Path, invalid: Any
) -> None:
    with pytest.raises(LibrusError) as error:
        PersistenceStore(tmp_path / "state", limits=invalid)
    assert error.value.kind is ErrorKind.INVALID_INPUT
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("mode", ["unknown", "rejected"])
def test_modern_public_attempts_use_same_durable_workflow_without_legacy_fallback(
    tmp_path: Path, mode: str
) -> None:
    from librus_python_api import ModernRecipientReference
    from tests.modern_support import ModernFixture

    async def scenario() -> None:
        fixture = ModernFixture()
        if mode == "rejected":
            fixture.responses["send"] = (
                422,
                b'{"errors":[{"code":"DUPLICATED_RECEIVERS"}]}',
                "application/json",
                {},
            )
        async with fixture.running() as service:
            client = service.account("student")

            def modern() -> SendAttempt:
                return client.prepare_modern_send(
                    recipients=(
                        ModernRecipientReference(
                            "701", "901", "student", "parentsCouncil", "Fixture class"
                        ),
                    ),
                    subject="Original fixture subject",
                    body="Original fixture body",
                )

            async with PersistenceStore(tmp_path / "state") as store:
                attempt = modern()
                confirmation = await store.preview_send(attempt)
                assert fixture.calls == [] and fixture.modern_calls == []
                result = await store.execute_send(
                    confirmation.token, attempt, budget=RequestBudget(max_requests=9)
                )
                expected = (
                    SendStatus.UNKNOWN if mode == "unknown" else SendStatus.REJECTED
                )
                assert result.status is expected
                assert (
                    await store.send_outcome(confirmation.token, context=client.context)
                ).status is expected
                if mode == "unknown":
                    with pytest.raises(LibrusError):
                        await store.preview_send(modern())
                else:
                    await store.preview_send(modern())
                # A backend-specific block does not prohibit another backend's
                # independent approval, but cannot dispatch that backend itself.
                await store.preview_send(prepare(client))
                assert len(fixture.sends) == 1
                assert all(path != "/wiadomosci/1/6" for path, _ in fixture.calls)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "crash, same_token, before_send",
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, False, True),
    ],
)
def test_independent_process_claims_and_killed_sender_never_replay(
    tmp_path: Path, crash: bool, same_token: bool, before_send: bool
) -> None:
    async def scenario() -> None:
        fixture = ClaimCrashFixture() if before_send else SendFixture()
        if crash:
            fixture.send_hold = asyncio.Event()
        directory = tmp_path / "state"
        workers: list[asyncio.subprocess.Process] = []
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with PersistenceStore(directory) as store:
                    first = await store.preview_send(prepare(client))
                    second = await store.preview_send(prepare(client))
                    if same_token:
                        second = first
                try:
                    for confirmation in (first,) if crash else (first, second):
                        process = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "tests.persistence_worker",
                            str(directory),
                            origin,
                            confirmation.token,
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        workers.append(process)
                        assert process.stdout is not None
                        assert (
                            await asyncio.wait_for(process.stdout.readline(), 10)
                            == b"ready\n"
                        )
                    for process in workers:
                        assert process.stdin is not None
                        process.stdin.write(b"go\n")
                        await process.stdin.drain()
                    if crash:
                        await asyncio.wait_for(fixture.send_started.wait(), 10)
                        workers[0].kill()
                        await asyncio.wait_for(workers[0].wait(), 10)
                    else:
                        output = await asyncio.wait_for(
                            asyncio.gather(
                                *(process.communicate() for process in workers)
                            ),
                            10,
                        )
                        results = [
                            json.loads(stdout)
                            for stdout, stderr in output
                            if not stderr
                        ]
                        assert len(results) == 2
                        assert sorted(results, key=str) == sorted(
                            [{"status": "accepted"}, {"error": "invalid_input"}],
                            key=str,
                        )
                        assert all(process.returncode == 0 for process in workers)
                    async with PersistenceStore(directory) as recovered:
                        if crash:
                            history = await recovered.send_history(
                                context=client.context
                            )
                            assert len(history) == 2
                            assert (
                                sum(
                                    record.outcome.phase == "claimed"
                                    for record in history
                                )
                                == 1
                            )
                            outcome = await recovered.send_outcome(
                                first.token, context=client.context
                            )
                            assert (
                                outcome.phase == "claimed"
                                and outcome.status is SendStatus.UNKNOWN
                            )
                            assert outcome.requires_reconciliation
                            with pytest.raises(LibrusError):
                                await recovered.execute_send(
                                    second.token, prepare(client)
                                )
                        with pytest.raises(LibrusError):
                            await recovered.preview_send(prepare(client))
                    assert len(fixture.send_calls) == (not before_send)
                    if before_send:
                        assert fixture.logins == {}
                finally:
                    if fixture.send_hold is not None:
                        fixture.send_hold.set()
                    for process in workers:
                        if process.returncode is None:
                            process.kill()
                        await process.communicate()

    asyncio.run(scenario())


def test_full_payloads_at_maximum_storage_worker_admission(tmp_path: Path) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        aliases = tuple(f"fixture-{i}" for i in range(16))
        from librus_python_api import SchedulerLimits

        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(
                aliases,
                scheduler_limits=SchedulerLimits(
                    requests_per_second=10000,
                    burst=256,
                    active_requests=4,
                    queued_requests=64,
                    queued_requests_per_account=4,
                    operations=64,
                    operations_per_account=4,
                ),
            ) as service:
                attempts = [
                    service.account(alias).prepare_send(
                        recipients=tuple(
                            RecipientReference(str(i + 101), alias, "nauczyciel")
                            for i in range(50)
                        ),
                        subject=f"{item:03}" + "s" * 197,
                        body="b" * 15000,
                    )
                    for alias in aliases
                    for item in range(4)
                ]
                async with PersistenceStore(
                    tmp_path / "state",
                    limits=PersistenceLimits(
                        operations=64,
                        pending_confirmations=256,
                        send_records=4096,
                    ),
                ) as store:
                    confirmations = await asyncio.gather(
                        *(store.preview_send(attempt) for attempt in attempts)
                    )
                    assert fixture.calls == []
                    budget = RequestBudget(max_requests=144)
                    results = await asyncio.gather(
                        *(
                            store.execute_send(
                                confirmation.token, attempt, budget=budget
                            )
                            for confirmation, attempt in zip(
                                confirmations, attempts, strict=True
                            )
                        )
                    )
                    assert all(
                        result.status is SendStatus.ACCEPTED for result in results
                    )
                    outcomes = await asyncio.gather(
                        *(
                            store.send_outcome(
                                confirmation.token, context=attempt.account_context
                            )
                            for confirmation, attempt in zip(
                                confirmations, attempts, strict=True
                            )
                        )
                    )
                    assert all(
                        outcome.status is SendStatus.ACCEPTED for outcome in outcomes
                    )
                assert (
                    len(fixture.send_calls) == 64 and budget.requests_dispatched == 144
                )
                assert fixture.logins == dict.fromkeys(aliases, 1)
                assert service.snapshot().active == service.snapshot().queued == 0
                assert len(persisted(tmp_path / "state")) == 64

    asyncio.run(scenario())


def test_expired_unused_previews_reclaim_only_unused_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        directory = tmp_path / "state"
        async with fixture.service() as service:
            client = service.account("student")
            async with PersistenceStore(
                directory,
                limits=PersistenceLimits(send_records=2, pending_confirmations=2),
            ) as store:
                first = await store.preview_send(prepare(client))
                await store.preview_send(prepare(client))
                monkeypatch.setattr(
                    "librus_python_api.persistence._now",
                    lambda: int(first.expires_at.timestamp()),
                )
                third = await store.preview_send(prepare(client))
                assert len(persisted(directory)) == 1
                with pytest.raises(LibrusError):
                    await store.send_outcome(first.token, context=client.context)
                assert (
                    await store.send_outcome(third.token, context=client.context)
                ).phase == "pending"
                assert fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("boundary", ["claim", "final_save"])
def test_repeated_cancellation_joins_storage_and_preserves_conservative_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        started, release = threading.Event(), threading.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with PersistenceStore(tmp_path / "state") as store:
                    attempt = prepare(client)
                    confirmation = await store.preview_send(attempt)
                    method = "_claim" if boundary == "claim" else "_finish"
                    original = getattr(store, method)

                    def hold(*args: Any) -> None:
                        original(*args)
                        started.set()
                        if not release.wait(5):
                            raise TimeoutError("Fixture barrier timed out")

                    monkeypatch.setattr(store, method, hold)
                    task = asyncio.create_task(
                        store.execute_send(confirmation.token, attempt)
                    )
                    try:
                        assert await asyncio.to_thread(started.wait, 5)
                        for _ in range(4):
                            task.cancel()
                            await asyncio.sleep(0)
                        assert not task.done()
                    finally:
                        release.set()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    outcome = await store.send_outcome(
                        confirmation.token, context=client.context
                    )
                    assert outcome.status is (
                        SendStatus.UNKNOWN
                        if boundary == "claim"
                        else SendStatus.ACCEPTED
                    )
                    assert len(fixture.send_calls) == (boundary == "final_save")
                    with pytest.raises(LibrusError):
                        await store.preview_send(prepare(client))

    asyncio.run(scenario())


def test_storage_admission_saturation_and_shutdown_joins_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        started, release = threading.Event(), threading.Event()
        async with fixture.service() as service:
            client = service.account("student")
            store = PersistenceStore(
                tmp_path / "state", limits=PersistenceLimits(operations=1)
            )
            await store.open()
            original = store._issue

            def hold(*args: Any) -> Any:
                started.set()
                if not release.wait(5):
                    raise TimeoutError("Fixture barrier timed out")
                return original(*args)

            monkeypatch.setattr(store, "_issue", hold)
            preview = asyncio.create_task(store.preview_send(prepare(client)))
            closing: asyncio.Task[None] | None = None
            try:
                assert await asyncio.to_thread(started.wait, 5)
                with pytest.raises(LibrusError) as error:
                    await store.preview_send(prepare(client))
                assert error.value.kind is ErrorKind.LIMIT
                closing = asyncio.create_task(store.aclose())
                await asyncio.sleep(0)
                assert not closing.done()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await preview
            assert closing is not None
            await asyncio.wait_for(closing, 5)
            with pytest.raises(LibrusError) as error:
                await store.preview_send(prepare(client))
            assert error.value.kind is ErrorKind.CLOSED
            assert fixture.calls == []
            await store.aclose()

    asyncio.run(scenario())


def test_cancel_while_final_save_queues_preserves_acknowledgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.send_hold = asyncio.Event()
        started, release = threading.Event(), threading.Event()
        waiting_final = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                async with PersistenceStore(tmp_path / "state") as store:
                    attempt = prepare(client)
                    confirmation = await store.preview_send(attempt)
                    original_issue, original_io = store._issue, store._io

                    def hold_issue(*args: Any) -> Any:
                        started.set()
                        if not release.wait(5):
                            raise TimeoutError("Fixture barrier timed out")
                        return original_issue(*args)

                    async def observe_io(*args: Any, **kwargs: Any) -> Any:
                        if kwargs.get("finishing"):
                            waiting_final.set()
                        return await original_io(*args, **kwargs)

                    monkeypatch.setattr(store, "_issue", hold_issue)
                    monkeypatch.setattr(store, "_io", observe_io)
                    send = asyncio.create_task(
                        store.execute_send(confirmation.token, attempt)
                    )
                    preview: asyncio.Task[Any] | None = None
                    try:
                        await asyncio.wait_for(fixture.send_started.wait(), 5)
                        preview = asyncio.create_task(
                            store.preview_send(prepare(client, subject="Other preview"))
                        )
                        assert await asyncio.to_thread(started.wait, 5)
                        fixture.send_hold.set()
                        await asyncio.wait_for(waiting_final.wait(), 5)
                        assert attempt.outcome.status is SendStatus.ACCEPTED
                        for _ in range(4):
                            send.cancel()
                            await asyncio.sleep(0)
                        assert not send.done()
                    finally:
                        fixture.send_hold.set()
                        release.set()
                    assert preview is not None
                    await preview
                    with pytest.raises(asyncio.CancelledError):
                        await send
                    assert (
                        await store.send_outcome(
                            confirmation.token, context=client.context
                        )
                    ).status is SendStatus.ACCEPTED
                    assert len(fixture.send_calls) == 1

    asyncio.run(scenario())


def test_maximum_record_load_preserves_history_and_refuses_overflow(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        directory = tmp_path / "state"
        async with fixture.service() as service:
            client = service.account("student")
            async with PersistenceStore(directory):
                pass
            # Populate the actual accepted schema with independent original
            # consumed history. No network is needed to qualify storage capacity.
            with sqlite3.connect(directory / "state.sqlite3") as connection:
                connection.executemany(
                    "INSERT INTO send_attempts VALUES (?,?,?,?,?,?)",
                    [
                        (
                            f"{index:064x}",
                            client.context.identifier,
                            f"{index + 4096:064x}",
                            1,
                            301,
                            "unknown",
                        )
                        for index in range(4096)
                    ],
                )
            async with PersistenceStore(
                directory, limits=PersistenceLimits(send_records=4096)
            ) as store:
                history = await store.send_history(context=client.context)
                assert len(history) == 4096
                assert all(record.outcome.requires_reconciliation for record in history)
                with pytest.raises(LibrusError) as error:
                    await store.preview_send(prepare(client))
                assert error.value.kind is ErrorKind.LIMIT
            assert len(persisted(directory)) == 4096 and fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "damage",
    [
        "database_symlink",
        "directory_symlink",
        "permissions",
        "corrupt",
        "future_schema",
        "changed_schema",
        "oversize",
    ],
)
def test_invalid_existing_storage_is_not_reset(tmp_path: Path, damage: str) -> None:
    async def scenario() -> None:
        directory = tmp_path / "state"
        async with PersistenceStore(directory):
            pass
        database = directory / "state.sqlite3"
        if damage == "database_symlink":
            target = tmp_path / "original.sqlite3"
            database.rename(target)
            database.symlink_to(target)
        elif damage == "directory_symlink":
            target = tmp_path / "original"
            directory.rename(target)
            directory.symlink_to(target, target_is_directory=True)
        elif damage == "permissions":
            os.chmod(database, 0o644)
        elif damage == "corrupt":
            database.write_bytes(b"original invalid database bytes")
        elif damage == "oversize":
            with database.open("r+b") as stream:
                stream.truncate(8 * 1024 * 1024 + 1)
        else:
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "PRAGMA user_version=77"
                    if damage == "future_schema"
                    else "ALTER TABLE send_attempts ADD COLUMN extra TEXT"
                )
        before = database.read_bytes()
        with pytest.raises(LibrusError):
            async with PersistenceStore(directory):
                pass
        assert database.read_bytes() == before

    asyncio.run(scenario())


@pytest.mark.parametrize("status", list(SendStatus))
def test_restart_exact_binding_redaction_outcome_and_no_duplicate_send(
    tmp_path: Path, status: SendStatus
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        if status is SendStatus.REJECTED:
            fixture.send_body = acknowledgement("Wiadomość nie została wysłana.")
        if status is SendStatus.UNKNOWN:
            fixture.disconnect = True
        directory = tmp_path / "state"
        store = PersistenceStore(directory)
        assert not directory.exists()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                attempt = prepare(client)
                async with store:
                    confirmation = await store.preview_send(attempt)
                    assert fixture.calls == []
                async with PersistenceStore(directory) as reopened:
                    if status is SendStatus.NOT_DISPATCHED:
                        with pytest.raises(LibrusError):
                            await reopened.execute_send(
                                confirmation.token,
                                attempt,
                                budget=RequestBudget(max_requests=1),
                            )
                    else:
                        result = await reopened.execute_send(
                            confirmation.token, attempt
                        )
                        assert result.status is status
                async with PersistenceStore(directory) as recovered:
                    outcome = await recovered.send_outcome(
                        confirmation.token, context=client.context
                    )
                    assert outcome.status is status
                    assert outcome.requires_reconciliation == (
                        status is SendStatus.UNKNOWN
                    )
                    with pytest.raises(LibrusError):
                        await recovered.execute_send(
                            confirmation.token, prepare(client)
                        )
                    if status in (SendStatus.ACCEPTED, SendStatus.UNKNOWN):
                        with pytest.raises(LibrusError):
                            await recovered.preview_send(prepare(client))
                    else:
                        await recovered.preview_send(prepare(client))
                assert len(fixture.send_calls) == (
                    status is not SendStatus.NOT_DISPATCHED
                )
                assert attempt.outcome.status is status
                assert confirmation.token not in repr(confirmation)
                assert FIXTURE_SECRET not in repr(client.context)
        rows = persisted(directory)
        assert rows[0][0] == hashlib.sha256(confirmation.token.encode()).hexdigest()
        wire = (directory / "state.sqlite3").read_bytes()
        for private in (
            confirmation.token,
            FIXTURE_SECRET,
            "Original fixture subject",
            "Original fixture body",
        ):
            assert private.encode() not in wire

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change", ["subject", "body", "recipient", "order", "login", "origin", "backend"]
)
def test_mismatch_consumes_confirmation_without_authentication(
    tmp_path: Path, change: str
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            client = service.account("student")
            recipients = (
                RecipientReference("101", "student", "nauczyciel"),
                RecipientReference("102", "student", "nauczyciel"),
            )
            original = prepare(client, recipients=recipients)
            attempt = prepare(client, recipients=recipients)
            if change in ("subject", "body"):
                attempt = prepare(client, recipients=recipients, **{change: "Changed"})
            if change == "recipient":
                attempt = prepare(client)
            if change == "order":
                attempt = prepare(client, recipients=tuple(reversed(recipients)))
            async with PersistenceStore(tmp_path / "state") as store:
                confirmation = await store.preview_send(original)
                if change in ("login", "origin"):
                    async with LibrusService(
                        {
                            "student": AccountCredentials(
                                login="changed" if change == "login" else "student",
                                password=FIXTURE_SECRET,
                            )
                        },
                        connection=ConnectionSettings(
                            synergia_origin="http://localhost:8081"
                            if change == "origin"
                            else fixture.origin,
                            api_origin=fixture.origin,
                        ),
                    ) as other:
                        attempt = prepare(
                            other.account("student"), recipients=recipients
                        )
                        with pytest.raises(LibrusError):
                            await store.execute_send(confirmation.token, attempt)
                else:
                    if change == "backend":
                        from librus_python_api import ModernRecipientReference

                        attempt = client.prepare_modern_send(
                            recipients=(
                                ModernRecipientReference(
                                    "701",
                                    "901",
                                    "student",
                                    "parentsCouncil",
                                    "Fixture class",
                                ),
                            ),
                            subject="Original fixture subject",
                            body="Original fixture body",
                        )
                    with pytest.raises(LibrusError):
                        await store.execute_send(confirmation.token, attempt)
                outcome = await store.send_outcome(
                    confirmation.token, context=client.context
                )
                assert outcome.phase == "invalidated"
                with pytest.raises(LibrusError):
                    await store.execute_send(confirmation.token, original)
                assert fixture.calls == [] and not original.used and not attempt.used

    asyncio.run(scenario())


def test_configured_context_stable_across_password_rotation_not_alias_or_login() -> (
    None
):
    fixture = SendFixture()
    fixture.origin = "http://localhost:8080"
    expected = fixture.service().account("student").context
    for alias, login, password, equal in (
        ("student", "student", "rotated", True),
        ("student", "other", FIXTURE_SECRET, False),
        ("other", "student", FIXTURE_SECRET, False),
    ):
        service = LibrusService(
            {alias: AccountCredentials(login=login, password=password)},
            connection=ConnectionSettings(
                synergia_origin=fixture.origin, api_origin=fixture.origin
            ),
        )
        assert (service.account(alias).context == expected) is equal


@pytest.mark.parametrize("interruption", ["cancel", "close"])
def test_joined_post_dispatch_interruption_survives_restart(
    tmp_path: Path, interruption: str
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.send_hold = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                directory = tmp_path / "state"
                async with PersistenceStore(directory) as store:
                    confirmation = await store.preview_send(prepare(client))
                    task = asyncio.create_task(
                        store.execute_send(confirmation.token, prepare(client))
                    )
                    try:
                        await asyncio.wait_for(fixture.send_started.wait(), 5)
                        if interruption == "close":
                            await asyncio.wait_for(store.aclose(), 5)
                        else:
                            task.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await task
                    finally:
                        fixture.send_hold.set()
                async with PersistenceStore(directory) as reopened:
                    assert (
                        await reopened.send_outcome(
                            confirmation.token, context=client.context
                        )
                    ).status is SendStatus.UNKNOWN
                    with pytest.raises(LibrusError):
                        await reopened.preview_send(prepare(client))
                assert len(fixture.send_calls) == 1
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_final_save_failure_retains_claim_and_acknowledged_local_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                attempt = prepare(client)
                async with PersistenceStore(tmp_path / "state") as store:
                    confirmation = await store.preview_send(attempt)

                    def fail(*args: Any) -> None:
                        raise OSError("Private path must not escape")

                    monkeypatch.setattr(store, "_finish", fail)
                    with pytest.raises(LibrusError) as error:
                        await store.execute_send(confirmation.token, attempt)
                    assert error.value.kind is ErrorKind.STORAGE
                    assert error.value.__context__ is None
                    assert attempt.outcome.status is SendStatus.ACCEPTED
                    outcome = await store.send_outcome(
                        confirmation.token, context=client.context
                    )
                    assert (
                        outcome.status is SendStatus.UNKNOWN
                        and outcome.phase == "claimed"
                    )
                    with pytest.raises(LibrusError):
                        await store.preview_send(prepare(client))
                assert len(fixture.send_calls) == 1

    asyncio.run(scenario())


def test_real_sqlite_contention_and_bounded_capacity_before_transport(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            client = service.account("student")
            directory = tmp_path / "state"
            limits = PersistenceLimits(
                send_records=2, pending_confirmations=2, busy_timeout_seconds=0.01
            )
            async with PersistenceStore(directory, limits=limits) as store:
                first = await store.preview_send(prepare(client))
                await store.preview_send(prepare(client, subject="Another"))
                with pytest.raises(LibrusError) as error:
                    await store.preview_send(prepare(client, subject="Full"))
                assert error.value.kind is ErrorKind.LIMIT
                with sqlite3.connect(directory / "state.sqlite3") as blocker:
                    blocker.execute("BEGIN IMMEDIATE")
                    with pytest.raises(LibrusError) as error:
                        await store.execute_send(first.token, prepare(client))
                    assert error.value.kind is ErrorKind.LIMIT
                assert (
                    await store.send_outcome(first.token, context=client.context)
                ).phase == "pending"
                assert fixture.calls == [] and len(persisted(directory)) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("delta", [-1, 300, 301])
def test_clock_rollback_or_expiry_invalidates_without_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delta: int
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            client = service.account("student")
            directory = tmp_path / "state"
            async with PersistenceStore(directory) as store:
                confirmation = await store.preview_send(prepare(client))
                created_at = persisted(directory)[0][3]
                monkeypatch.setattr(
                    "librus_python_api.persistence._now", lambda: created_at + delta
                )
                with pytest.raises(LibrusError):
                    await store.execute_send(confirmation.token, prepare(client))
                assert (
                    await store.send_outcome(confirmation.token, context=client.context)
                ).phase == "invalidated"
                assert fixture.calls == []

    asyncio.run(scenario())
