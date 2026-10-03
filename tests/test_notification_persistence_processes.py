"""Real process loss and per-context flock exclusion with actual public reads."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from librus_python_api import NotificationCategory
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.persistence import NotificationStore, NotificationWorkflow
from tests.http_support import serve
from tests.notification_persistence_support import NotificationWorkflowFixture

AGENDA = (NotificationCategory.AGENDA,)


async def launch(
    directory: Path, origin: str, phase: str
) -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.notification_worker",
        str(directory),
        origin,
        phase,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None and process.stdin is not None
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 10) == b"ready\n"
        process.stdin.write(b"go\n")
        await process.stdin.drain()
        return process
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise


async def close_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.kill()
    await process.communicate()


def test_competing_process_refuses_read_once_while_context_owner_is_active(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        fixture.body_hold = asyncio.Event()
        workers: list[asyncio.subprocess.Process] = []
        directory = tmp_path / "state"
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            try:
                first = await launch(directory, origin, "normal")
                workers.append(first)
                await asyncio.wait_for(fixture.pending.wait(), 10)
                second = await launch(directory, origin, "normal")
                workers.append(second)
                stdout, stderr = await asyncio.wait_for(second.communicate(), 10)
                assert json.loads(stdout) == {"error": "limit"} and stderr == b""
                fixture.body_hold.set()
                stdout, stderr = await asyncio.wait_for(first.communicate(), 10)
                result = json.loads(stdout)
                assert result["items"] == 1 and stderr == b""
                async with fixture.service() as service:
                    async with NotificationStore(directory) as store:
                        replay = await NotificationWorkflow(
                            service.account("student"), store
                        ).poll(categories=AGENDA)
                        assert replay.receipt == result["receipt"]
                assert fixture.calls_by_account == ["student"] and fixture.logins == {
                    "student": 1
                }
            finally:
                fixture.body_hold.set()
                for worker in workers:
                    await close_process(worker)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "phase", ["partial", "checkpoint", "delivery", "acknowledgement"]
)
def test_process_loss_retains_uncertainty_raw_delivery_or_acknowledgement(
    tmp_path: Path, phase: str
) -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        if phase == "partial":
            fixture.body_hold = asyncio.Event()
        directory = tmp_path / "state"
        worker: asyncio.subprocess.Process | None = None
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            try:
                worker = await launch(directory, origin, phase)
                receipt: str | None = None
                if phase == "partial":
                    await asyncio.wait_for(fixture.pending.wait(), 10)
                    worker.kill()
                elif phase == "acknowledgement":
                    assert worker.stdout is not None and worker.stdin is not None
                    record = json.loads(
                        await asyncio.wait_for(worker.stdout.readline(), 10)
                    )
                    receipt = record["receipt"]
                    worker.stdin.write(b"acknowledge\n")
                    await worker.stdin.drain()
                await asyncio.wait_for(worker.wait(), 10)
                if phase != "partial":
                    assert (
                        worker.returncode
                        == {"checkpoint": 73, "delivery": 74, "acknowledgement": 75}[
                            phase
                        ]
                    )
                before = len(fixture.calls)
                async with fixture.service() as service:
                    async with NotificationStore(directory) as store:
                        workflow = NotificationWorkflow(
                            service.account("student"), store
                        )
                        record = json.loads(
                            (
                                await store.export_archive(
                                    context=workflow.client.context
                                )
                            ).payload
                        )
                        if phase == "partial":
                            assert (
                                record["raw"] is None
                                and record["reservation"] is not None
                            )
                            with pytest.raises(LibrusError) as error:
                                await workflow.poll(
                                    categories=AGENDA, allow_consume_events=True
                                )
                            assert error.value.kind is ErrorKind.CHECKPOINT
                        elif phase == "acknowledgement":
                            assert (
                                record["state"]["initialized"]
                                and record["raw"] is record["delivery"] is None
                            )
                            assert receipt is not None
                            await workflow.acknowledge(receipt)
                        else:
                            assert (
                                record["raw"] is not None
                                and record["reservation"] is None
                            )
                            assert (record["delivery"] is not None) is (
                                phase == "delivery"
                            )
                            batch = await workflow.poll(categories=AGENDA)
                            assert batch.first_run and len(batch.items) == 1
                            await workflow.acknowledge(batch.receipt)
                        assert len(fixture.calls) == before
                        assert fixture.calls_by_account == ["student"]
                        assert fixture.logins == {"student": 1}
            finally:
                if fixture.body_hold is not None:
                    fixture.body_hold.set()
                if worker is not None:
                    await close_process(worker)

    asyncio.run(scenario())
