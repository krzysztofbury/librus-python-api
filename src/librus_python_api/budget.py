"""Caller-shareable operation budgets with no I/O or implicit configuration."""

import asyncio
import time

from librus_python_api.config import DEFAULT_OPERATION_LIMITS, OperationLimits
from librus_python_api.errors import ErrorKind, LibrusError


class RequestBudget:
    """Single-event-loop request/deadline budget shared across account calls.

    The deadline starts at construction, including admission wait. Every actual
    dispatch consumes one request; rejected or canceled queued work consumes none.
    A reserved rate token can still be spent when its waiter is canceled. Budgets
    are never refunded after dispatch, including connection failure or timeout.
    """

    def __init__(
        self,
        *,
        max_requests: int = DEFAULT_OPERATION_LIMITS.max_requests,
        timeout_seconds: float = DEFAULT_OPERATION_LIMITS.timeout_seconds,
        max_response_bytes: int = DEFAULT_OPERATION_LIMITS.max_response_bytes,
    ) -> None:
        limits = OperationLimits(
            max_requests=max_requests,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        self._max_requests = limits.max_requests
        self._deadline = time.monotonic() + limits.timeout_seconds
        self._requests_dispatched = 0
        self._max_response_bytes = limits.max_response_bytes
        self._response_bytes = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def requests_dispatched(self) -> int:
        return self._requests_dispatched

    @property
    def response_bytes(self) -> int:
        return self._response_bytes

    @property
    def remaining_response_bytes(self) -> int:
        return max(0, self._max_response_bytes - self._response_bytes)

    def _receive(self, count: int) -> None:
        self._bind_loop()
        self.remaining_seconds()
        self._response_bytes += count
        if self._response_bytes > self._max_response_bytes:
            raise LibrusError(ErrorKind.LIMIT)

    def remaining_seconds(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise LibrusError(ErrorKind.TIMEOUT)
        return remaining

    def check(self) -> None:
        self.remaining_seconds()
        if self._requests_dispatched >= self._max_requests:
            raise LibrusError(ErrorKind.LIMIT)
        if self.remaining_response_bytes == 0:
            raise LibrusError(ErrorKind.LIMIT)

    def _consume(self) -> None:
        # Synchronous check/update is atomic on the service's single event loop.
        self.check()
        self._requests_dispatched += 1

    def _bind_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._loop = loop
