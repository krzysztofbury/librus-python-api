"""Bounded, round-robin admission across isolated configured accounts."""

import asyncio
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

from librus_python_api.budget import RequestBudget
from librus_python_api.config import SchedulerLimits
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.lifecycle import join_owned
from librus_python_api.models import SchedulerSnapshot


@dataclass(slots=True)
class _Waiter:
    ready: asyncio.Future[None]
    granted: bool = False


@dataclass(slots=True)
class _Account:
    queue: deque[_Waiter] = field(default_factory=deque)
    active: int = 0


class RequestScheduler:
    """One event-loop-local scheduler reused by all account clients in a service.

    Only admitted work gets an owned worker task. Excess work fails immediately;
    no hidden semaphore waiters or unbounded worker queue is created. Calls are
    scheduled FIFO within accounts and round-robin between eligible accounts.
    `aclose` cancels and joins active workers before returning. This does not
    enforce a distributed quota across independent services/processes.
    """

    def __init__(
        self, accounts: tuple[str, ...], *, limits: SchedulerLimits | None = None
    ) -> None:
        self._limits = limits or SchedulerLimits()
        if not accounts or len(accounts) > self._limits.accounts:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if any(
            not isinstance(key, str) or not key or len(key) > 80 for key in accounts
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if len(set(accounts)) != len(accounts):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._accounts = {key: _Account() for key in accounts}
        self._ring: deque[str] = deque()
        self._active = self._queued = self._requests_dispatched = 0
        self._tokens = float(self._limits.burst)
        self._updated_at = time.monotonic()
        self._pause_until = 0.0
        self._resuming_without_burst = False
        self._timer: asyncio.TimerHandle | None = None
        self._workers: set[asyncio.Future[Any]] = set()
        self._close_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    def snapshot(self) -> SchedulerSnapshot:
        return SchedulerSnapshot(self._active, self._queued, self._requests_dispatched)

    def _bind_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._loop = loop
        if self._closed:
            raise LibrusError(ErrorKind.CLOSED)
        return loop

    async def run[T](
        self, account: str, budget: RequestBudget, action: Callable[[], Awaitable[T]]
    ) -> T:
        loop = self._bind_loop()
        state = self._accounts.get(account)
        if state is None:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        budget._bind_loop()
        budget.check()
        waiter = _Waiter(loop.create_future())
        self._enqueue(account, state, waiter)
        try:
            async with asyncio.timeout(budget.remaining_seconds()):
                await waiter.ready
                if self._closed:
                    raise LibrusError(ErrorKind.CLOSED)
                budget._consume()
                self._requests_dispatched += 1
                worker = asyncio.ensure_future(action())
                self._workers.add(worker)
                try:
                    await asyncio.wait((worker,))
                    result = worker.result()
                    budget.remaining_seconds()
                    return result
                except asyncio.CancelledError:
                    if not isinstance(worker, asyncio.Task) or not worker.cancelling():
                        worker.cancel()
                    await join_owned(worker)
                    if self._closed:
                        raise LibrusError(ErrorKind.CLOSED) from None
                    raise
                finally:
                    self._workers.discard(worker)
        except TimeoutError:
            raise LibrusError(ErrorKind.TIMEOUT) from None
        finally:
            self._release(account, state, waiter)

    def _enqueue(self, account: str, state: _Account, waiter: _Waiter) -> None:
        self._refill()
        immediate = (
            not self._ring
            and self._active < self._limits.active_requests
            and state.active < self._limits.active_requests_per_account
            and self._tokens >= 1
            and time.monotonic() >= self._pause_until
        )
        if immediate:
            self._grant(state, waiter)
            return
        if (
            self._queued >= self._limits.queued_requests
            or len(state.queue) >= self._limits.queued_requests_per_account
        ):
            raise LibrusError(ErrorKind.LIMIT)
        if not state.queue:
            self._ring.append(account)
        state.queue.append(waiter)
        self._queued += 1
        self._drain()

    def _grant(self, state: _Account, waiter: _Waiter) -> None:
        assert self._active < self._limits.active_requests
        assert state.active < self._limits.active_requests_per_account
        assert self._tokens >= 1
        self._tokens -= 1
        state.active += 1
        self._active += 1
        waiter.granted = True
        waiter.ready.set_result(None)

    def _release(self, account: str, state: _Account, waiter: _Waiter) -> None:
        if waiter.granted:
            state.active -= 1
            self._active -= 1
            assert state.active >= 0
            assert self._active >= 0
        elif waiter in state.queue:
            state.queue.remove(waiter)
            self._queued -= 1
            if not state.queue:
                self._ring.remove(account)
        if not waiter.ready.done():
            waiter.ready.cancel()
        self._drain()
        if (
            waiter.granted
            and self._active == 0
            and not self._ring
            and time.monotonic() >= self._pause_until
        ):
            self._resuming_without_burst = False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self._updated_at)
        capacity = 1 if self._resuming_without_burst else self._limits.burst
        self._tokens = min(
            float(capacity),
            self._tokens + elapsed * self._limits.requests_per_second,
        )
        self._updated_at = max(now, self._pause_until)

    def _drain(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._closed:
            return
        self._refill()
        while self._ring and self._active < self._limits.active_requests:
            state = self._next_eligible()
            if state is None:
                return
            delay = max(
                self._pause_until - time.monotonic(),
                (1 - self._tokens) / self._limits.requests_per_second,
            )
            if delay > 0:
                assert self._loop is not None
                self._timer = self._loop.call_later(delay, self._drain)
                return
            waiter = state.queue.popleft()
            self._queued -= 1
            account = self._ring.popleft()
            if state.queue:
                self._ring.append(account)
            self._grant(state, waiter)

    def _next_eligible(self) -> _Account | None:
        for _ in range(len(self._ring)):
            if not self._ring:
                return None
            state = self._accounts[self._ring[0]]
            while state.queue and state.queue[0].ready.done():
                state.queue.popleft()
                self._queued -= 1
            if not state.queue:
                self._ring.popleft()
                continue
            if state.active < self._limits.active_requests_per_account:
                return state
            self._ring.rotate(-1)
        return None

    def pause_for(self, seconds: float) -> None:
        """Pause shared dispatch and resume gradually, without a full burst."""
        self._bind_loop()
        if (
            type(seconds) not in (int, float)
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._pause_until = max(self._pause_until, time.monotonic() + seconds)
        # Keep resume credit capped until admitted work and its backlog drain.
        # A delayed event-loop timer must not rebuild a burst during a pause.
        self._resuming_without_burst = True
        self._tokens = 0.0
        self._updated_at = self._pause_until
        self._drain()

    async def aclose(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._loop = loop
        if asyncio.current_task() in self._workers:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if self._close_task is None:
            self._closed = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            for state in self._accounts.values():
                for waiter in state.queue:
                    if not waiter.ready.done():
                        waiter.ready.set_exception(LibrusError(ErrorKind.CLOSED))
            self._close_task = asyncio.create_task(self._finish_close())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            await join_owned(self._close_task)
            raise

    async def _finish_close(self) -> None:
        workers = tuple(self._workers)
        for worker in workers:
            if not isinstance(worker, asyncio.Task) or not worker.cancelling():
                worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async def __aenter__(self) -> Self:
        self._bind_loop()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
