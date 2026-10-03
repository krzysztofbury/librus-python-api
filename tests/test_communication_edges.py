"""Completed wire receipts and paused consumer bounds through public workflows."""

import asyncio
import threading
import time
from pathlib import Path

import pytest

from librus_python_api import (
    RequestBudget,
    SchedulerLimits,
    SendStatus,
    TransportLimits,
)
from librus_python_api.exceptions import (
    InvalidInputError,
    OperationTimeoutError,
    UnsupportedCapabilityError,
)
from librus_python_api.persistence import PersistenceStore
from tests.attachments_support import queued, reference, rig
from tests.http_support import serve
from tests.modern_support import ModernFixture
from tests.sending_support import SendFixture
from tests.test_modern_messages import prepare as prepare_modern
from tests.test_persistence import prepare


@pytest.mark.parametrize(
    "location", ["", "/GetFile/", "/new-layout/key", "/GetFile/key/get"]
)
def test_unsupported_attachment_shape_has_no_download_or_permission_cooldown(
    location: str,
) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            fixture.location = (
                fixture.download_origin + location
                if location.startswith("/")
                else location
            )
            client = service.account("student")
            with pytest.raises(UnsupportedCapabilityError):
                async with client.stream_attachment(reference()):
                    pytest.fail("Unsupported destination was followed")
            assert fixture.downloads == [] and len(fixture.resolutions) == 1
            fixture.location = None
            async with client.stream_attachment(reference()) as stream:
                assert b"".join([chunk async for chunk in stream]) == fixture.body
            assert len(fixture.resolutions) == 2 and len(fixture.downloads) == 1
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_idle_consumer_releases_shared_slot_before_long_budget_expires() -> None:
    async def scenario() -> None:
        async with rig(
            ("student", "parent"),
            scheduler_limits=SchedulerLimits(
                requests_per_second=1000, burst=40, active_requests=1
            ),
            transport_limits=TransportLimits(attachment_idle_timeout_seconds=0.05),
        ) as (fixture, service):
            await service.account("parent").identity()
            budget = RequestBudget(timeout_seconds=30)
            stream = service.account("student").stream_attachment(
                reference(), budget=budget
            )
            async with stream:
                other = asyncio.create_task(
                    service.account("parent").student_information()
                )
                await queued(service)
                await asyncio.wait_for(other, 2)
                assert budget.remaining_seconds() > 20
                with pytest.raises(OperationTimeoutError):
                    await anext(stream)
                assert not stream.complete
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


class ReceiptDeadlineBudget(RequestBudget):
    """Expire the operation immediately after charging the final wire chunk.

    The body is delivered by a real local HTTP server. This deterministic clock
    boundary tests return-time expiry, not a mocked send result or parser.
    """

    chunks_remaining = 1

    def _receive(self, count: int) -> None:
        super()._receive(count)
        self.chunks_remaining -= 1
        if self.chunks_remaining == 0:
            self._deadline = time.monotonic()


@pytest.mark.parametrize("durable", [False, True])
def test_completed_legacy_send_receipt_survives_return_deadline(
    tmp_path: Path, durable: bool
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                attempt = prepare(client)
                budget = ReceiptDeadlineBudget(max_requests=1)
                async with PersistenceStore(tmp_path / "state") as store:
                    if durable:
                        confirmation = await store.preview_send(attempt)
                        result = await store.execute_send(
                            confirmation.token, attempt, budget=budget
                        )
                        assert (await store.send_history(context=client.context))[
                            0
                        ].outcome.phase == "accepted"
                    else:
                        result = await attempt.execute(budget=budget)
                    assert result.status is SendStatus.ACCEPTED
                    assert attempt.outcome is result
                    assert (
                        len(fixture.send_calls) == 1 and budget.requests_dispatched == 1
                    )
                    with pytest.raises(InvalidInputError):
                        await attempt.execute()
                    assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_complete_modern_rejection_survives_return_deadline_without_replaying() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        fixture.responses["send"] = (
            422,
            b'{"errors":[{"code":"DUPLICATED_RECEIVERS"}]}',
            "application/json",
            {},
        )
        async with fixture.running() as service:
            client = service.account("student")
            await client.modern_identity()
            budget = ReceiptDeadlineBudget(max_requests=2)
            budget.chunks_remaining = 2  # Warm identity GET, then the rejected POST.
            result = await prepare_modern(client).execute(budget=budget)
            assert result.status is SendStatus.REJECTED
            assert len(fixture.sends) == 1 and budget.requests_dispatched == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("interruption", ["deadline", "cancel", "receipt_timeout"])
def test_complete_receipt_local_parsing_is_bounded_and_external_cancel_still_propagates(
    interruption: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from librus_python_api.sending import parse_send_acknowledgement

    started, release = threading.Event(), threading.Event()

    def parse(body: bytes) -> SendStatus:
        started.set()
        assert release.wait(5)
        return parse_send_acknowledgement(body)

    monkeypatch.setattr("librus_python_api.service.parse_send_acknowledgement", parse)

    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(
                transport_limits=TransportLimits(
                    request_timeout_seconds=0.05
                    if interruption == "receipt_timeout"
                    else 30,
                    connect_timeout_seconds=0.02,
                )
            ) as service:
                client = service.account("student")
                await client.identity()
                attempt = prepare(client)
                task = asyncio.create_task(
                    attempt.execute(budget=RequestBudget(timeout_seconds=0.1))
                )
                try:
                    for _ in range(200):
                        if started.is_set():
                            break
                        await asyncio.sleep(0.001)
                    assert started.is_set()
                    if interruption == "cancel":
                        task.cancel()
                        await asyncio.sleep(0)
                    else:
                        await asyncio.sleep(0.15)
                    assert (
                        not task.done()
                    )  # Thread must be joined even at cancellation.
                finally:
                    release.set()
                if interruption == "cancel":
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert attempt.outcome.status is SendStatus.UNKNOWN
                else:
                    result = await task
                    assert result.status is (
                        SendStatus.UNKNOWN
                        if interruption == "receipt_timeout"
                        else SendStatus.ACCEPTED
                    )
                assert len(fixture.send_calls) == 1
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())
