"""Single-owner attachment streams with joined, service-owned resource lifetimes."""

import asyncio
import time
from collections.abc import AsyncIterator
from types import TracebackType
from typing import TYPE_CHECKING, Literal, Self

from librus_python_api.attachment_routes import (
    modern_attachment_key,
    signed_attachment_key,
    validate_attachment_reference,
    validate_max_bytes,
    validate_modern_attachment_reference,
)
from librus_python_api.budget import RequestBudget
from librus_python_api.config import ATTACHMENT_MAX_BYTES
from librus_python_api.exceptions import ErrorKind, LibrusError, SessionExpiredError
from librus_python_api.lifecycle import join_owned
from librus_python_api.models import (
    AttachmentHeaders,
    AttachmentMetadata,
    DiagnosticEvent,
    MessageAttachmentReference,
    ModernMessageAttachmentReference,
    OperationName,
)

if TYPE_CHECKING:
    from librus_python_api.service import AccountClient


class AttachmentStream(AsyncIterator[bytes]):
    """Use with async with. Uncached, non-reentrant and consumed by one task.

    Construction has no I/O. The owned worker holds shared admission until EOF,
    close or failure, even when the consumer is paused. No filesystem writes.
    """

    _operation: OperationName = "attachment_download"

    def __init__(
        self,
        client: "AccountClient",
        reference: MessageAttachmentReference | ModernMessageAttachmentReference,
        *,
        max_bytes: int = ATTACHMENT_MAX_BYTES,
        budget: RequestBudget | None = None,
    ) -> None:
        self._validate_reference(reference, client._alias)
        validate_max_bytes(max_bytes)
        if budget is not None and not isinstance(budget, RequestBudget):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._client, self._reference = client, reference
        self._max_bytes, self._budget = max_bytes, budget
        self._task: asyncio.Task[None] | None = None
        self._metadata: AttachmentMetadata | None = None
        self._ready, self._demand, self._delivery = (asyncio.Event() for _ in range(3))
        self._chunk: bytes | None = None
        self._error: ErrorKind | None = None
        self._consumer: asyncio.Task[object] | None = None
        self._entered = self._closed = self._complete = self._reading = (
            self._admitted
        ) = False

    @property
    def metadata(self) -> AttachmentMetadata:
        if self._metadata is None:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        return self._metadata

    @staticmethod
    def _validate_reference(
        reference: MessageAttachmentReference | ModernMessageAttachmentReference,
        account: str,
    ) -> None:
        if not isinstance(reference, MessageAttachmentReference):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        validate_attachment_reference(reference, account)

    @property
    def complete(self) -> bool:
        return self._complete

    async def __aenter__(self) -> Self:
        if self._entered or self._closed:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        client, service = self._client, self._client._service
        service._bind()
        budget = self._budget or service._budget()
        budget._bind_loop()
        budget.remaining_seconds()
        client._admit_operation()
        self._entered = self._admitted = True
        self._task = asyncio.create_task(self._run(budget))
        service._tasks.add(self._task)
        self._task.add_done_callback(self._finished)
        try:
            await self._ready.wait()
            self._raise_failure()
            return self
        except BaseException:
            await self.aclose()
            raise

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> bytes:
        if not self._entered or self._closed:
            raise LibrusError(ErrorKind.CLOSED)
        consumer = asyncio.current_task()
        if self._reading or (
            self._consumer is not None and self._consumer is not consumer
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._consumer = consumer
        self._reading = True
        try:
            self._raise_failure()
            if self._complete:
                raise StopAsyncIteration
            self._demand.set()
            await self._delivery.wait()
            self._delivery.clear()
            self._raise_failure()
            if self._chunk is None:
                assert self._task is not None
                await join_owned(self._task)
                self._raise_failure()
                assert self._complete
                raise StopAsyncIteration
            chunk, self._chunk = self._chunk, None
            return chunk
        except asyncio.CancelledError:
            await self.aclose()
            raise
        finally:
            self._reading = False

    def _raise_failure(self) -> None:
        if self._error is not None:
            raise LibrusError(self._error)

    def _opened(self, headers: AttachmentHeaders) -> None:
        self._metadata = AttachmentMetadata(
            self._client._session_identity(),
            self._reference,
            headers,
            self._client._observation(self._operation),
        )
        self._ready.set()

    async def _pull(self) -> None:
        async with asyncio.timeout(
            self._client._service._transport_limits.attachment_idle_timeout_seconds
        ):
            await self._demand.wait()
        self._demand.clear()

    def _deliver(self, chunk: bytes) -> None:
        assert self._chunk is None
        self._chunk = chunk
        self._delivery.set()

    async def _fetch(self, budget: RequestBudget, _: bool) -> None:
        client = self._client
        assert isinstance(self._reference, MessageAttachmentReference)
        response = await client._transport.resolve_attachment(self._reference, budget)
        if response.status == 302 and client._is_login_redirect(response):
            raise LibrusError(ErrorKind.SESSION_EXPIRED)
        if response.status != 302:
            raise LibrusError(ErrorKind.PARSE)
        key = signed_attachment_key(
            response.headers.get("location", ""), client._service._connection
        )
        await client._transport.stream_download(
            key, budget, self._max_bytes, self._opened, self._pull, self._deliver
        )

    async def _run(self, budget: RequestBudget) -> None:
        client = self._client
        started = time.monotonic()
        outcome: ErrorKind | Literal["ok", "cancelled"] = "ok"
        try:
            async with asyncio.timeout(budget.remaining_seconds()):
                async with client._lock:
                    client._check_cooldown("authentication")
                    client._check_cooldown(self._operation)
                    await client._authenticated(self._fetch, budget, False)
            self._complete = True
        except LibrusError as error:
            self._error = outcome = error.kind
            if error.kind in (ErrorKind.ACCESS_DENIED, ErrorKind.SESSION_EXPIRED):
                client._cooldowns[self._operation] = (
                    time.monotonic()
                    + client._service._transport_limits.cooldown_seconds,
                    error.kind,
                )
        except TimeoutError:
            self._error = outcome = ErrorKind.TIMEOUT
        except asyncio.CancelledError:
            self._error = ErrorKind.CLOSED
            outcome = "cancelled"
        except Exception:
            # Never attach URL-bearing exceptions from a custom transport.
            self._error = outcome = ErrorKind.CONNECTION
        finally:
            if self._error is not None:
                self._chunk = None
            self._release()
            self._ready.set()
            self._delivery.set()
            client._emit(
                DiagnosticEvent(
                    self._operation,
                    outcome,
                    time.monotonic() - started,
                    budget.requests_dispatched,
                    budget.response_bytes,
                )
            )

    def _release(self) -> None:
        if self._admitted:
            self._admitted = False
            self._client._release_operation()

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._client._service._tasks.discard(task)
        # Cancellation can happen before the worker's first instruction.
        self._release()
        if task.cancelled():
            self._error = ErrorKind.CLOSED
        self._ready.set()
        self._delivery.set()

    async def aclose(self) -> None:
        self._closed = True
        self._chunk = None
        if self._task is not None:
            if not self._task.done() and not self._task.cancelling():
                self._task.cancel()
            if await join_owned(self._task):
                raise asyncio.CancelledError

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


class ModernAttachmentStream(AttachmentStream):
    """Explicit modern resolution with the shared credential-free download worker."""

    _operation: OperationName = "modern_attachment_download"

    @staticmethod
    def _validate_reference(
        reference: MessageAttachmentReference | ModernMessageAttachmentReference,
        account: str,
    ) -> None:
        if not isinstance(reference, ModernMessageAttachmentReference):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        validate_modern_attachment_reference(reference, account)

    async def _fetch(self, budget: RequestBudget, _: bool) -> None:
        client = self._client
        assert isinstance(self._reference, ModernMessageAttachmentReference)
        resolver = getattr(client._transport, "resolve_modern_attachment", None)
        if not callable(resolver):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        await client._modern_ready(budget)
        try:
            response = await resolver(self._reference, budget)
            client._validate_read_response(response, "application/json")
            key = await client._service._parsers.run(
                lambda body: modern_attachment_key(body, client._service._connection),
                response.body,
                budget,
            )
        except BaseException as error:
            client._invalidate_modern()
            if isinstance(error, SessionExpiredError):
                error._messages_origin = True
            raise
        await client._transport.stream_download(
            key,
            budget,
            self._max_bytes,
            self._opened,
            self._pull,
            self._deliver,
        )
