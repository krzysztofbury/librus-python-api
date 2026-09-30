"""A bounded parser executor whose canceled work is joined before release."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from librus_python_api.budget import RequestBudget
from librus_python_api.errors import ErrorKind, LibrusError
from librus_python_api.lifecycle import join_owned


class ParserPool:
    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._slots = asyncio.Semaphore(2)
        self._executor: ThreadPoolExecutor | None = None

    async def run[T](
        self,
        parser: Callable[[bytes], T],
        body: bytes,
        budget: RequestBudget,
    ) -> T:
        if len(body) > self._max_bytes:
            raise LibrusError(ErrorKind.LIMIT)
        # Service admission bounds waiting coroutines; acquire before submit so
        # the executor never develops an unbounded hidden queue.
        async with self._slots:
            budget.remaining_seconds()
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="librus-parse"
                )
            future = asyncio.get_running_loop().run_in_executor(
                self._executor, parser, body
            )
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                # Threads cannot be preempted. Pure parsing cannot mutate session
                # state; release the slot only after actual bounded completion.
                await join_owned(future)
                raise
            budget.remaining_seconds()
            return result

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
