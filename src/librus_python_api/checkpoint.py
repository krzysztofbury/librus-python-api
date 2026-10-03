"""Owned checkpoint attempts: defer cancellation, never detach persistence."""

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass

from librus_python_api.config import CHECKPOINT_MAX_TIMEOUT_SECONDS
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.lifecycle import join_owned

CHECKPOINT_SERVICE: ContextVar[object | None] = ContextVar(
    "checkpoint_service", default=None
)


def validate_checkpoint(callback: object, seconds: float) -> None:
    if (
        not callable(callback)
        or type(seconds) not in (int, float)
        or not math.isfinite(seconds)
        or not 0 < seconds <= CHECKPOINT_MAX_TIMEOUT_SECONDS
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)


@dataclass(slots=True)
class CheckpointState:
    failed: bool = False


async def handoff(
    callback: Callable[[], Awaitable[None]], seconds: float, state: CheckpointState
) -> None:
    """The callback must cooperate with cancellation and join its own work.

    If it blocks or suppresses cancellation, ownership is retained until it ends;
    the library cannot make arbitrary persistence preemptible or exactly-once.
    """

    async def attempt() -> None:
        started = time.monotonic()
        try:
            async with asyncio.timeout(seconds):
                await callback()
            if time.monotonic() - started >= seconds:
                state.failed = True
        except BaseException:
            state.failed = True

    # No cancellable await between complete receipt and establishing ownership.
    owned = asyncio.create_task(attempt())
    interrupted = await join_owned(owned)
    if owned.cancelled():
        state.failed = True
    if state.failed:
        raise LibrusError(ErrorKind.CHECKPOINT)
    if interrupted:
        raise asyncio.CancelledError
