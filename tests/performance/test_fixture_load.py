"""Opt-in loopback workload measurements; no claim about upstream throughput."""

import asyncio
import json
import statistics
import time
import tracemalloc
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import RequestBudget, SchedulerLimits
from librus_python_api.exceptions import StaleCursorError
from tests.http_support import profile_html, serve
from tests.messages_support import message_row, messages_html
from tests.reads_support import ReadsFixture

pytestmark = pytest.mark.performance
ACCOUNTS = ("student", "parent", "other-student", "other-parent")
LIMITS = SchedulerLimits(
    active_requests=2,
    active_requests_per_account=1,
    queued_requests=4,
    queued_requests_per_account=1,
    requests_per_second=1000,
    burst=16,
)


class Measurement:
    def __init__(self) -> None:
        self.times: dict[str, list[float]] = {}
        self.active = self.queued = 0

    async def timed(self, name: str, call: Awaitable[Any]) -> Any:
        start = time.monotonic()
        try:
            return await call
        finally:
            self.times.setdefault(name, []).append(time.monotonic() - start)

    async def sample(self, service: Any, done: asyncio.Event) -> None:
        while not done.is_set():
            snapshot = service.snapshot()
            self.active = max(self.active, snapshot.active)
            self.queued = max(self.queued, snapshot.queued)
            await asyncio.sleep(0.001)


def mailboxes(fixture: ReadsFixture) -> None:
    for number in range(5):
        body = messages_html(
            page=number,
            count=5,
            footer=True,
            rows="".join(message_row(str(100 + number * 50 + i)) for i in range(50)),
        )
        fixture.page_bodies[("messages_received", number)] = (
            body.encode(),
            "text/html",
        )


async def mailbox_workload(measurement: Measurement) -> dict[str, int]:
    fixture = ReadsFixture()
    mailboxes(fixture)
    async with serve(fixture.app()) as origin:
        fixture.origin = origin
        async with fixture.service(ACCOUNTS, scheduler_limits=LIMITS) as service:
            done = asyncio.Event()
            monitor = asyncio.create_task(measurement.sample(service, done))
            budget = RequestBudget(max_requests=60, timeout_seconds=30)
            try:

                async def batch(alias: str, age: float, phase: str) -> Any:
                    result = await measurement.timed(
                        phase,
                        service.account(alias).messages(
                            max_pages=8,
                            limit=256,
                            budget=budget,
                            max_age_seconds=age,
                        ),
                    )
                    assert len(result.items) == 250 and result.next_cursor is None
                    assert {item.reference.account for item in result.items} == {alias}
                    return result

                cold = await asyncio.gather(*(batch(a, 60, "cold") for a in ACCOUNTS))
                assert budget.requests_dispatched == len(fixture.calls) == 40
                warm = await asyncio.gather(*(batch(a, 60, "warm") for a in ACCOUNTS))
                assert all(a is b for a, b in zip(cold, warm, strict=True))
                assert budget.requests_dispatched == len(fixture.calls) == 40
                await asyncio.gather(*(batch(a, 0, "fresh") for a in ACCOUNTS))
                assert budget.requests_dispatched == len(fixture.calls) == 60

                drift_budget = RequestBudget(max_requests=8)
                first = await asyncio.gather(
                    *(
                        service.account(a).messages(
                            limit=1,
                            max_pages=1,
                            budget=drift_budget,
                        )
                        for a in ACCOUNTS
                    )
                )
                body, kind = fixture.page_bodies[("messages_received", 0)]
                fixture.page_bodies[("messages_received", 0)] = (
                    body.replace(b"Fixture subject", b"Changed subject", 1),
                    kind,
                )

                async def resume(alias: str, result: Any) -> None:
                    with pytest.raises(StaleCursorError):
                        await measurement.timed(
                            "changing-page",
                            service.account(alias).messages(
                                cursor=result.next_cursor,
                                budget=drift_budget,
                            ),
                        )

                await asyncio.gather(
                    *(resume(a, r) for a, r in zip(ACCOUNTS, first, strict=True))
                )
                assert drift_budget.requests_dispatched == 8
                assert service.snapshot().active == service.snapshot().queued == 0
            finally:
                done.set()
                await monitor
    return {
        "cold_requests": 40,
        "warm_requests": 0,
        "fresh_requests": 20,
        "changing_page_requests": 8,
    }


class SlowFixture(ReadsFixture):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

    def handler(self, operation: str) -> Callable[[web.Request], Awaitable[Any]]:
        if operation != "student_information":
            return super().handler(operation)

        async def slow(request: web.Request) -> web.StreamResponse:
            self.record(request)
            response = web.StreamResponse(headers={"Content-Type": "text/html"})
            await response.prepare(request)
            try:
                body = profile_html().encode()
                await response.write(body[:64])
                await self.release.wait()
                await asyncio.sleep(0.02)
                await response.write(body[64:])
                await response.write_eof()
            except ConnectionResetError:
                pass
            return response

        return slow


async def cancellation_workload(measurement: Measurement) -> dict[str, int]:
    fixture = SlowFixture()
    async with serve(fixture.app()) as origin:
        fixture.origin = origin
        async with fixture.service(ACCOUNTS, scheduler_limits=LIMITS) as service:
            for alias in ACCOUNTS:
                await service.account(alias).identity()
            done = asyncio.Event()
            monitor = asyncio.create_task(measurement.sample(service, done))
            budget = RequestBudget(max_requests=4)
            tasks = [
                asyncio.create_task(
                    measurement.timed(
                        "cancelled",
                        service.account(a).student_information(budget=budget),
                    )
                )
                for a in ACCOUNTS
            ]
            try:
                async with asyncio.timeout(5):
                    # Sample public scheduler counters and server receipt together.
                    while (  # noqa: ASYNC110
                        (service.snapshot().active, service.snapshot().queued) != (2, 2)
                        or len(fixture.calls) < 22
                    ):
                        await asyncio.sleep(0.001)
                # Both active slow bodies and queued work are cancelled together.
                for task in tasks:
                    task.cancel()
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                assert all(
                    isinstance(result, asyncio.CancelledError) for result in outcomes
                )
                assert budget.requests_dispatched == 2
                assert service.snapshot().active == service.snapshot().queued == 0
                fixture.release.set()
                recovery = RequestBudget(max_requests=4)
                await asyncio.gather(
                    *(
                        measurement.timed(
                            "slow-recovery",
                            service.account(a).student_information(budget=recovery),
                        )
                        for a in ACCOUNTS
                    )
                )
                assert recovery.requests_dispatched == 4
                assert service.snapshot().active == service.snapshot().queued == 0
            finally:
                fixture.release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                done.set()
                await monitor
    return {"cancelled_dispatched": 2, "slow_recovery_requests": 4}


def test_representative_fixture_load(
    record_property: Callable[[str, object], None],
) -> None:
    assert not tracemalloc.is_tracing()
    measurement = Measurement()
    tracemalloc.start()
    start = time.monotonic()
    try:

        async def run() -> list[dict[str, int]]:
            records = []
            for _ in range(3):
                records.append(
                    await mailbox_workload(measurement)
                    | await cancellation_workload(measurement)
                )
            return records

        requests = asyncio.run(run())
        elapsed = time.monotonic() - start
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    distributions = {
        name: {
            "samples": len(values),
            "p50": statistics.median(values),
            "p95": statistics.quantiles(values, n=100, method="inclusive")[94],
            "max": max(values),
        }
        for name, values in measurement.times.items()
    }
    report = {
        "requests_per_repetition": requests,
        "elapsed_seconds": elapsed,
        "traced_peak_bytes": peak,
        "max_active": measurement.active,
        "max_queued": measurement.queued,
        "latency_seconds": distributions,
    }
    print(json.dumps(report, sort_keys=True))
    record_property("fixture_load", json.dumps(report, sort_keys=True))
    assert measurement.active == 2 and 2 <= measurement.queued <= 4
    assert elapsed < 25 and peak < 32 * 1024 * 1024
    thresholds = {
        "cold": 3,
        "fresh": 3,
        "warm": 0.05,
        "changing-page": 0.5,
        "cancelled": 0.5,
        "slow-recovery": 0.5,
    }
    assert all(row["max"] < thresholds[name] for name, row in distributions.items())
