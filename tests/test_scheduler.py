import asyncio
import time
from collections import Counter
from collections.abc import Awaitable
from contextlib import AsyncExitStack
from functools import partial

import pytest
from aiohttp import ClientSession, web

from librus_python_api.budget import RequestBudget
from librus_python_api.config import SchedulerLimits
from librus_python_api.errors import ErrorKind, LibrusError
from librus_python_api.scheduler import RequestScheduler


def run[T](awaitable: Awaitable[T]) -> T:
    async def bounded() -> T:
        async with asyncio.timeout(10):
            return await awaitable

    return asyncio.run(bounded())


def fast_limits(**overrides: int | float) -> SchedulerLimits:
    values: dict[str, int | float] = {
        "requests_per_second": 1000,
        "burst": 10,
        "active_requests": 1,
        "active_requests_per_account": 1,
        "queued_requests": 8,
        "queued_requests_per_account": 4,
    }
    values.update(overrides)
    return SchedulerLimits(**values)  # type: ignore[arg-type]


def test_round_robin_admission_under_saturation() -> None:
    async def scenario() -> None:
        started, release = asyncio.Event(), asyncio.Event()
        order: list[str] = []

        async def block() -> None:
            started.set()
            await release.wait()

        async def record(account: str) -> str:
            order.append(account)
            return account

        async with RequestScheduler(("a", "b", "c"), limits=fast_limits()) as scheduler:
            budget = RequestBudget()
            first = asyncio.create_task(scheduler.run("a", budget, block))
            await started.wait()
            tasks = []
            for account in ("a", "a", "b", "b", "c", "c"):
                tasks.append(
                    asyncio.create_task(
                        scheduler.run(account, budget, partial(record, account))
                    )
                )
            await asyncio.sleep(0)
            assert scheduler.snapshot().queued == 6
            release.set()
            await asyncio.gather(first, *tasks)
            assert order == ["a", "b", "c", "a", "b", "c"]
            assert budget.requests_dispatched == 7
            assert scheduler.snapshot().active == 0

    run(scenario())


def test_global_and_account_queue_limits_reject_without_dispatch() -> None:
    async def scenario() -> None:
        started, release = asyncio.Event(), asyncio.Event()
        calls: list[str] = []

        async def action() -> None:
            calls.append("request")
            started.set()
            await release.wait()

        limits = fast_limits(queued_requests=2, queued_requests_per_account=1)
        async with RequestScheduler(("a", "b", "c"), limits=limits) as scheduler:
            budget = RequestBudget()
            first = asyncio.create_task(scheduler.run("a", budget, action))
            await started.wait()
            queued_a = asyncio.create_task(scheduler.run("a", budget, action))
            await asyncio.sleep(0)
            with pytest.raises(LibrusError, match="^limit$"):
                await scheduler.run("a", budget, action)
            queued_b = asyncio.create_task(scheduler.run("b", budget, action))
            await asyncio.sleep(0)
            with pytest.raises(LibrusError, match="^limit$"):
                await scheduler.run("c", budget, action)
            assert calls == ["request"]
            assert budget.requests_dispatched == 1
            release.set()
            await asyncio.gather(first, queued_a, queued_b)
            assert len(calls) == 3
            assert scheduler.snapshot().queued == 0

    run(scenario())


def test_shared_request_budget_is_not_multiplied_by_accounts() -> None:
    async def scenario() -> None:
        calls: list[str] = []

        async def action() -> str:
            calls.append("dispatch")
            return "ok"

        async with RequestScheduler(("a", "b"), limits=fast_limits()) as scheduler:
            budget = RequestBudget(max_requests=1)
            results = await asyncio.gather(
                scheduler.run("a", budget, action),
                scheduler.run("b", budget, action),
                return_exceptions=True,
            )
            assert results[0] == "ok"
            assert isinstance(results[1], LibrusError)
            assert results[1].kind == ErrorKind.LIMIT
            assert calls == ["dispatch"]
            assert budget.requests_dispatched == 1

    run(scenario())


def test_queued_deadline_and_cancellation_release_capacity() -> None:
    async def scenario() -> None:
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def action() -> None:
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()

        async with RequestScheduler(("a", "b"), limits=fast_limits()) as scheduler:
            budget = RequestBudget()
            first = asyncio.create_task(scheduler.run("a", budget, action))
            await started.wait()
            short = RequestBudget(timeout_seconds=0.02)
            with pytest.raises(LibrusError, match="^timeout$"):
                await scheduler.run("b", short, action)
            assert short.requests_dispatched == 0
            queued = asyncio.create_task(scheduler.run("b", budget, action))
            await asyncio.sleep(0)
            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queued
            assert scheduler.snapshot().queued == 0
            assert calls == 1
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            release.set()
            await scheduler.run("b", budget, action)
            assert calls == 2
            assert scheduler.snapshot().active == 0

    run(scenario())


def test_close_joins_canceled_workers_and_rejects_new_work() -> None:
    async def scenario() -> None:
        started, cleanup = asyncio.Event(), asyncio.Event()

        async def action() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleanup.set()

        scheduler = RequestScheduler(("a", "b"), limits=fast_limits())
        budget = RequestBudget()
        active = asyncio.create_task(scheduler.run("a", budget, action))
        await started.wait()
        queued = asyncio.create_task(scheduler.run("b", budget, action))
        await asyncio.sleep(0)
        await asyncio.gather(scheduler.aclose(), scheduler.aclose())
        results = await asyncio.gather(active, queued, return_exceptions=True)
        assert cleanup.is_set()
        assert all(isinstance(error, LibrusError) for error in results)
        assert scheduler.snapshot().active == scheduler.snapshot().queued == 0
        with pytest.raises(LibrusError, match="^closed$"):
            await scheduler.run("a", budget, action)

    run(scenario())


def test_four_account_http_workload_obeys_combined_rate_and_concurrency() -> None:
    async def scenario() -> None:
        timestamps: list[float] = []
        active: Counter[str] = Counter()
        peak_global = peak_account = 0

        async def handler(request: web.Request) -> web.Response:
            nonlocal peak_global, peak_account
            account = request.match_info["account"]
            timestamps.append(time.monotonic())
            active[account] += 1
            peak_global = max(peak_global, active.total())
            peak_account = max(peak_account, active[account])
            try:
                await asyncio.sleep(0.04)
                return web.Response(text=account)
            finally:
                active[account] -= 1

        app = web.Application()
        app.router.add_get("/fixture/{account}", handler)
        runner = web.AppRunner(app)
        async with AsyncExitStack() as stack:
            await runner.setup()
            stack.push_async_callback(runner.cleanup)
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            url = f"http://127.0.0.1:{runner.addresses[0][1]}/fixture"
            accounts = ("student_a", "parent_a", "student_b", "parent_b")
            limits = SchedulerLimits(
                requests_per_second=40,
                burst=2,
                active_requests=2,
                active_requests_per_account=1,
                queued_requests=12,
                queued_requests_per_account=3,
            )
            scheduler = await stack.enter_async_context(
                RequestScheduler(accounts, limits=limits)
            )
            session = await stack.enter_async_context(ClientSession(trust_env=False))

            async def fetch(account: str) -> str:
                async with session.get(f"{url}/{account}") as response:
                    return await response.text()

            budget = RequestBudget(max_requests=12)
            results = await asyncio.gather(
                *(
                    scheduler.run(key, budget, partial(fetch, key))
                    for key in accounts
                    for _ in range(3)
                )
            )
            assert Counter(results) == Counter({key: 3 for key in accounts})
            assert peak_global == 2
            assert peak_account == 1
            assert budget.requests_dispatched == len(timestamps) == 12
            # Check the token-bucket envelope over every observed subinterval.
            # 20ms tolerance accounts for loopback connection/event-loop jitter.
            for start in range(len(timestamps)):
                for end in range(start, len(timestamps)):
                    count = end - start + 1
                    allowance = 2 + 40 * (timestamps[end] - timestamps[start] + 0.02)
                    assert count <= allowance

    run(scenario())


def test_shared_pause_resumes_without_accumulated_burst() -> None:
    async def scenario() -> None:
        timestamps: list[float] = []

        async def action() -> None:
            timestamps.append(time.monotonic())

        limits = fast_limits(requests_per_second=50, burst=5)
        async with RequestScheduler(("a", "b"), limits=limits) as scheduler:
            budget = RequestBudget()
            started = time.monotonic()
            scheduler.pause_for(0.04)
            await asyncio.gather(
                scheduler.run("a", budget, action),
                scheduler.run("b", budget, action),
            )
            assert timestamps[0] - started >= 0.05
            assert timestamps[1] - timestamps[0] >= 0.015

    run(scenario())


def test_delayed_pause_timer_cannot_release_a_queued_burst() -> None:
    async def scenario() -> None:
        timestamps: list[float] = []

        async def action() -> None:
            timestamps.append(time.monotonic())

        limits = fast_limits(requests_per_second=50, burst=5)
        async with RequestScheduler(("a", "b", "c"), limits=limits) as scheduler:
            budget = RequestBudget()

            async def throttle() -> None:
                scheduler.pause_for(0.01)
                raise LibrusError(ErrorKind.THROTTLED)

            with pytest.raises(LibrusError, match="^throttled$"):
                await scheduler.run("a", budget, throttle)
            tasks = [
                asyncio.create_task(scheduler.run(key, budget, action))
                for key in ("a", "b", "c")
            ]
            await asyncio.sleep(0)
            # Delay the resume timer beyond several refill intervals. Backlogged
            # accounts must still resume gradually when the loop becomes free.
            time.sleep(0.08)  # noqa: ASYNC251 - intentional timer-delay fixture
            await asyncio.gather(*tasks)
            assert timestamps[1] - timestamps[0] >= 0.015
            assert timestamps[2] - timestamps[1] >= 0.015
            assert budget.requests_dispatched == 4

    run(scenario())


def test_cancellation_before_rate_grant_cannot_break_next_admission() -> None:
    async def scenario() -> None:
        calls: list[str] = []

        async def action() -> None:
            calls.append("dispatch")

        limits = fast_limits(requests_per_second=1000, burst=1)
        async with RequestScheduler(("a", "b", "c"), limits=limits) as scheduler:
            budget = RequestBudget()
            scheduler.pause_for(0.01)
            canceled = asyncio.create_task(scheduler.run("b", budget, action))
            await asyncio.sleep(0)
            # Simulate a temporarily busy loop: the rate timer is due, but the
            # canceled waiter has not resumed its cleanup when the next call runs.
            time.sleep(0.02)  # noqa: ASYNC251 - intentional busy-loop race fixture
            canceled.cancel()
            await scheduler.run("c", budget, action)
            with pytest.raises(asyncio.CancelledError):
                await canceled
            assert calls == ["dispatch"]
            assert budget.requests_dispatched == 1
            assert scheduler.snapshot().active == scheduler.snapshot().queued == 0

    run(scenario())


def test_active_deadline_waits_for_worker_cleanup() -> None:
    async def scenario() -> None:
        cleanup = asyncio.Event()

        async def action() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleanup.set()

        async with RequestScheduler(("a",), limits=fast_limits()) as scheduler:
            budget = RequestBudget(timeout_seconds=0.02)
            with pytest.raises(LibrusError, match="^timeout$"):
                await scheduler.run("a", budget, action)
            assert cleanup.is_set()
            assert budget.requests_dispatched == 1
            assert scheduler.snapshot().active == 0

    run(scenario())


def test_unknown_account_does_not_dispatch_or_grow_admission_state() -> None:
    async def scenario() -> None:
        async with RequestScheduler(("a",), limits=fast_limits()) as scheduler:
            budget = RequestBudget()
            with pytest.raises(LibrusError, match="^invalid_input$"):
                await scheduler.run("unknown", budget, lambda: asyncio.sleep(0))
            assert budget.requests_dispatched == 0
            assert scheduler.snapshot().queued == scheduler.snapshot().active == 0

    run(scenario())


def test_budget_cannot_be_shared_between_event_loops() -> None:
    budget = RequestBudget()

    async def scenario() -> None:
        async with RequestScheduler(("a",), limits=fast_limits()) as scheduler:
            await scheduler.run("a", budget, lambda: asyncio.sleep(0))

    run(scenario())
    with pytest.raises(LibrusError, match="^invalid_input$"):
        run(scenario())


def test_zero_queue_refuses_waiting_work_but_accepts_immediate_work() -> None:
    async def scenario() -> None:
        started, release = asyncio.Event(), asyncio.Event()

        async def block() -> None:
            started.set()
            await release.wait()

        limits = fast_limits(queued_requests=0, queued_requests_per_account=0)
        async with RequestScheduler(("a", "b"), limits=limits) as scheduler:
            budget = RequestBudget()
            first = asyncio.create_task(scheduler.run("a", budget, block))
            await started.wait()
            with pytest.raises(LibrusError, match="^limit$"):
                await scheduler.run("b", budget, block)
            release.set()
            await first
            await scheduler.run("b", budget, block)

    run(scenario())


def test_canceling_closer_does_not_interrupt_active_worker_cleanup() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        cleanup_started, cleanup_release, cleaned = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        async def action() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await cleanup_release.wait()
                cleaned.set()

        scheduler = RequestScheduler(("a",), limits=fast_limits())
        active = asyncio.create_task(scheduler.run("a", RequestBudget(), action))
        await started.wait()
        closer = asyncio.create_task(scheduler.aclose())
        await cleanup_started.wait()
        closer.cancel()
        await asyncio.sleep(0)
        closer.cancel()
        await asyncio.sleep(0)
        assert not closer.done()
        cleanup_release.set()
        with pytest.raises(asyncio.CancelledError):
            await closer
        with pytest.raises(LibrusError, match="^closed$"):
            await active
        assert cleaned.is_set()
        assert scheduler.snapshot().active == 0

    run(scenario())


def test_repeated_cancellation_cannot_release_active_slot_before_cleanup() -> None:
    async def scenario() -> None:
        started, cleanup_started, release, cleaned = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        async def action() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await release.wait()
                cleaned.set()

        async with RequestScheduler(("a",), limits=fast_limits()) as scheduler:
            caller = asyncio.create_task(scheduler.run("a", RequestBudget(), action))
            await started.wait()
            try:
                caller.cancel()
                await cleanup_started.wait()
                caller.cancel()
                await asyncio.sleep(0)
                assert not caller.done()
                assert scheduler.snapshot().active == 1
            finally:
                release.set()
                await asyncio.gather(caller, return_exceptions=True)
            assert cleaned.is_set()
            assert scheduler.snapshot().active == 0

    run(scenario())
