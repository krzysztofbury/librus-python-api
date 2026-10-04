"""Public login-scoped account service under one shared traffic boundary."""

import asyncio
import hashlib
import json
import math
import re
import time
from collections.abc import Awaitable, Callable, Hashable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import TracebackType
from typing import Any, Literal, Self, cast
from urllib.parse import urljoin, urlsplit

from librus_python_api.announcements import parse_announcements
from librus_python_api.attachments import AttachmentStream
from librus_python_api.attendance import parse_attendance, parse_attendance_detail
from librus_python_api.attendance_frequency import (
    parse_gateway_attendance,
    parse_lesson_subject,
    parse_subject_name,
    summarize_frequency,
)
from librus_python_api.budget import RequestBudget
from librus_python_api.checkpoint import CHECKPOINT_SERVICE, validate_checkpoint
from librus_python_api.completed_lessons import (
    parse_completed_lessons,
    validate_selection,
)
from librus_python_api.config import (
    ATTACHMENT_MAX_BYTES,
    ATTENDANCE_MAX_WINDOW_DAYS,
    ATTENDANCE_METADATA_CACHE_SIZE,
    ATTENDANCE_METADATA_TTL_SECONDS,
    ATTENDANCE_RESULT_CACHE_SIZE,
    CHECKPOINT_TIMEOUT_SECONDS,
    ENDPOINTS,
    GRADE_MAX_WINDOW_DAYS,
    MESSAGE_MAX_CURSOR_IDS,
    SCHEDULE_RESPONSE_VERSION,
    SESSION_COOKIE,
    AccountCredentials,
    ConnectionSettings,
    OperationLimits,
    SchedulerLimits,
    TransportLimits,
    agenda_form,
    attendance_view_form,
    completed_lessons_form,
    encode_modern_send,
    encode_send_form,
    grade_view_form,
    homework_form,
    message_page_form,
    recipient_form,
    timetable_form,
)
from librus_python_api.diagnostics import DiagnosticSink
from librus_python_api.exceptions import ErrorKind, LibrusError, SessionExpiredError
from librus_python_api.grade_parsers import parse_final_grades
from librus_python_api.grade_records import parse_grade_records
from librus_python_api.lifecycle import join_owned
from librus_python_api.message_content import parse_message_content, validate_reference
from librus_python_api.messages import parse_messages
from librus_python_api.messages import validate_selection as validate_message_selection
from librus_python_api.models import (
    AccountContext,
    Agenda,
    Announcements,
    Attendance,
    AttendanceDetail,
    AttendanceFrequency,
    AttendanceView,
    AttendanceWindow,
    CompletedLesson,
    CompletedLessons,
    CompletedLessonsCursor,
    CompletedLessonsPage,
    DiagnosticEvent,
    FinalGrades,
    GatewayAttendance,
    GatewayAttendanceRecord,
    Grades,
    GradeView,
    GradeWindow,
    Homework,
    Identity,
    LoginSubmission,
    MessageAttachmentReference,
    MessageContent,
    MessageFolder,
    MessageReference,
    Messages,
    MessagesCursor,
    MessagesPage,
    MessageSummary,
    ModernAccountData,
    ModernIdentity,
    ModernRecipientReference,
    ModernRecipients,
    ModernRecipientTypeReference,
    ModernRecipientTypes,
    ModernSendSubmission,
    NotificationCounts,
    Observation,
    OperationName,
    RecipientGroupChoices,
    RecipientGroupReference,
    RecipientGroups,
    RecipientReference,
    Recipients,
    RequestForm,
    ScheduleEventResponse,
    ScheduleEvents,
    ScheduleEventWire,
    SchedulerSnapshot,
    SchoolDetail,
    SchoolReference,
    SendResult,
    SendSubmission,
    StudentInformation,
    SubjectFrequencies,
    SubjectFrequency,
    Timetable,
    TransportResponse,
)
from librus_python_api.modern_messages import (
    parse_modern_identity,
    parse_modern_recipients,
    parse_modern_send_response,
    parse_modern_types,
    validate_modern_type,
)
from librus_python_api.notifications import (
    decode_payload,
    parse_notification_counts,
    parse_schedule_events,
    validate_response,
)
from librus_python_api.parsers import parse_identity, parse_login, parse_profile
from librus_python_api.parsing import ParserPool
from librus_python_api.recipients import (
    parse_recipient_group_choices,
    parse_recipient_groups,
    parse_recipients,
    validate_group,
)
from librus_python_api.scheduler import RequestScheduler
from librus_python_api.school_reads import (
    parse_agenda,
    parse_homework,
    parse_school_detail,
)
from librus_python_api.sending import SendAttempt, parse_send_acknowledgement
from librus_python_api.timetable import parse_timetable
from librus_python_api.transport import (
    AccountTransport,
    AiohttpTransport,
    TransportFactory,
)

HTML = "text/html"
JSON = "application/json"
MAX_AGE_LIMIT_SECONDS = 3600
NUMERIC_ID = re.compile(r"[0-9]{1,64}")

# A read receives its budget and whether this attempt has just logged in.
type Fetch[T] = Callable[[RequestBudget, bool], Awaitable[T]]


@dataclass(slots=True)
class _Flight:
    task: asyncio.Task[Any]
    waiters: int = 0


class LibrusService:
    """Own all independent login clients, transports, parsers, and worker tasks.

    Construction performs no I/O and does not discover environment settings.
    One service is event-loop local. Always close it or use an async context.
    """

    def __init__(
        self,
        accounts: Mapping[str, AccountCredentials],
        *,
        scheduler_limits: SchedulerLimits | None = None,
        transport_limits: TransportLimits | None = None,
        operation_limits: OperationLimits | None = None,
        connection: ConnectionSettings | None = None,
        transport_factory: TransportFactory = AiohttpTransport,
        diagnostic_sink: DiagnosticSink | None = None,
    ) -> None:
        self._limits = scheduler_limits or SchedulerLimits()
        self._transport_limits = transport_limits or TransportLimits()
        self._operation_limits = operation_limits or OperationLimits()
        self._connection = connection or ConnectionSettings()
        self._scheduler = RequestScheduler(tuple(accounts), limits=self._limits)
        if any(
            not isinstance(value, AccountCredentials) for value in accounts.values()
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._factory = transport_factory
        self._diagnostic_sink = diagnostic_sink
        self._clients = {
            alias: AccountClient(self, alias, credentials)
            for alias, credentials in accounts.items()
        }
        self._parsers = ParserPool(self._transport_limits.parse_max_bytes)
        self._transports: list[AccountTransport] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._operations = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None

    def account(self, alias: str) -> "AccountClient":
        if self._closed:
            raise LibrusError(ErrorKind.CLOSED)
        client = self._clients.get(alias)
        if client is None:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        return client

    def snapshot(self) -> SchedulerSnapshot:
        return self._scheduler.snapshot()

    def _bind(self) -> None:
        if CHECKPOINT_SERVICE.get() is self:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._loop = loop
        if self._closed:
            raise LibrusError(ErrorKind.CLOSED)

    def _transport(self, alias: str) -> AccountTransport:
        transport = self._factory(
            alias,
            self._scheduler,
            self._connection,
            self._transport_limits,
        )
        if any(transport is item for item in self._transports):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._transports.append(transport)
        return transport

    def _budget(self) -> RequestBudget:
        limits = self._operation_limits
        return RequestBudget(
            max_requests=limits.max_requests,
            timeout_seconds=limits.timeout_seconds,
            max_response_bytes=limits.max_response_bytes,
        )

    async def aclose(self) -> None:
        if CHECKPOINT_SERVICE.get() is self:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._loop = loop
        if asyncio.current_task() in self._tasks:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._finish_close())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            await join_owned(self._close_task)
            raise

    async def _finish_close(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._scheduler.aclose()
        try:
            outcomes = await asyncio.gather(
                *(transport.aclose() for transport in self._transports),
                return_exceptions=True,
            )
            if any(isinstance(outcome, BaseException) for outcome in outcomes):
                raise LibrusError(ErrorKind.CONNECTION)
        finally:
            self._parsers.close()

    async def __aenter__(self) -> Self:
        self._bind()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


def _require_dates(*days: date | None, max_days: int | None = None) -> None:
    if any(day is not None and type(day) is not date for day in days):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    start, end = days[0], days[-1]
    if max_days is not None and start is not None and end is not None:
        if not 0 <= (end - start).days < max_days:
            raise LibrusError(ErrorKind.INVALID_INPUT)


class AccountClient:
    """Service-owned account context. Fresh reads are the default.

    max_age_seconds permits bounded account/session-scoped reuse. No persistent
    cookies, child switching, or automatic cross-login identity merging exists.
    Default-budget identical reads coalesce. Explicit budgets coalesce only by
    budget object identity. Canceling the last waiter cancels and joins its work.
    """

    def __init__(
        self,
        service: LibrusService,
        alias: str,
        credentials: AccountCredentials,
    ) -> None:
        self._service, self._alias, self._credentials = service, alias, credentials
        self._context = AccountContext(
            alias,
            hashlib.sha256(
                json.dumps(
                    [
                        1,
                        alias,
                        credentials.login.get_secret_value(),
                        service._connection.synergia_origin,
                        service._connection.api_origin,
                        service._connection.messages_origin,
                    ],
                    ensure_ascii=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )
        self._transport_instance: AccountTransport | None = None
        self._lock = asyncio.Lock()
        self._flights: dict[Hashable, _Flight] = {}
        self._operations = 0
        self._generation = 0
        self._identity: Identity | None = None
        self._cache: dict[Hashable, tuple[float, Any]] = {}
        self._metadata: dict[tuple[str, str], tuple[float, str]] = {}
        self._cooldowns: dict[str, tuple[float, ErrorKind]] = {}
        self._consuming_schedule = False
        self._modern_account: ModernAccountData | None = None

    @property
    def _transport(self) -> AccountTransport:
        if self._transport_instance is None:
            self._transport_instance = self._service._transport(self._alias)
        return self._transport_instance

    def prepare_send(
        self, *, recipients: tuple[RecipientReference, ...], subject: str, body: str
    ) -> SendAttempt:
        if self._service._closed:
            raise LibrusError(ErrorKind.CLOSED)
        submission = SendSubmission(recipients, subject, body)
        encode_send_form(submission, self._alias)
        return SendAttempt(self, submission)

    async def _execute_send(
        self, attempt: SendAttempt, budget: RequestBudget | None
    ) -> SendResult:
        if isinstance(attempt.submission, ModernSendSubmission):
            return await self._execute_modern_send(attempt, attempt.submission, budget)
        submission = attempt.submission
        encode_send_form(submission, self._alias)
        deadline = asyncio.timeout(None)

        async def fetch(budget: RequestBudget, _: bool) -> SendResult:
            send = getattr(self._transport, "send_message", None)
            if not callable(send):
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

            def dispatched() -> None:
                attempt._dispatch(
                    self._session_identity(), self._observation("send_message")
                )
                for key in tuple(self._cache):
                    if isinstance(key, tuple) and key[0] == "messages_sent":
                        del self._cache[key]

            response = await send(submission, budget, dispatched)
            receipt_budget = self._receipt_budget(deadline)
            self._validate_read_response(response, HTML)
            status = await self._service._parsers.run(
                parse_send_acknowledgement, response.body, receipt_budget
            )
            return attempt._acknowledge(status)

        return await self._uncached(
            "send_message",
            fetch,
            budget,
            authenticate=True,
            preserve_cancellation=True,
            deadline=deadline,
        )

    def _receipt_budget(self, deadline: asyncio.Timeout) -> RequestBudget:
        """No further I/O: retain a complete receipt with bounded local parsing."""
        seconds = self._service._transport_limits.request_timeout_seconds
        deadline.reschedule(asyncio.get_running_loop().time() + seconds)
        return RequestBudget(max_requests=1, timeout_seconds=seconds)

    def prepare_modern_send(
        self,
        *,
        recipients: tuple[ModernRecipientReference, ...],
        subject: str,
        body: str,
    ) -> SendAttempt:
        if self._service._closed:
            raise LibrusError(ErrorKind.CLOSED)
        submission = ModernSendSubmission(recipients, subject, body)
        encode_modern_send(submission, self._alias)
        return SendAttempt(self, submission)

    @property
    def context(self) -> AccountContext:
        """Configured login/origin provenance without authentication or storage I/O."""
        return self._context

    async def _modern_ready(
        self, budget: RequestBudget, *, refresh: bool = False
    ) -> ModernAccountData:
        if self._modern_account is not None and not refresh:
            return self._modern_account
        authenticate = getattr(self._transport, "authenticate_modern", None)
        if not callable(authenticate):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        try:
            if self._modern_account is None:
                await authenticate(self._credentials.login.get_secret_value(), budget)
            account = await self._page(
                "modern_identity", budget, parse_modern_identity, content_type=JSON
            )
            identity = self._session_identity()
            if (
                account.account_id != identity.owner.id
                or (
                    identity.owner.first_name is not None
                    and account.first_name != identity.owner.first_name
                )
                or (
                    identity.owner.last_name is not None
                    and account.last_name != identity.owner.last_name
                )
            ):
                raise LibrusError(ErrorKind.ACCESS_DENIED)
            self._modern_account = account
            return account
        except BaseException:
            self._invalidate_modern()
            raise

    async def modern_identity(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> ModernIdentity:
        async def fetch(budget: RequestBudget, _: bool) -> ModernIdentity:
            # Identity reads are fresh even if a modern session is already bound.
            account = await self._modern_ready(budget, refresh=True)
            return ModernIdentity(
                self._session_identity(), account, self._observation("modern_identity")
            )

        return await self._read(("modern_identity",), fetch, budget, max_age_seconds)

    async def modern_recipient_types(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> ModernRecipientTypes:
        async def fetch(budget: RequestBudget, _: bool) -> ModernRecipientTypes:
            await self._modern_ready(budget)
            items = await self._page(
                "modern_recipient_types",
                budget,
                lambda body: parse_modern_types(body, self._alias),
                content_type=JSON,
            )
            return ModernRecipientTypes(
                self._session_identity(),
                items,
                self._observation("modern_recipient_types"),
            )

        return await self._read(
            ("modern_recipient_types",),
            fetch,
            budget,
            max_age_seconds,
        )

    async def modern_recipients(
        self,
        recipient_type: ModernRecipientTypeReference,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> ModernRecipients:
        validate_modern_type(recipient_type, self._alias)

        async def fetch(budget: RequestBudget, _: bool) -> ModernRecipients:
            await self._modern_ready(budget)
            items = await self._page(
                "modern_recipients",
                budget,
                lambda body: parse_modern_recipients(body, recipient_type),
                content_type=JSON,
            )
            return ModernRecipients(
                self._session_identity(),
                recipient_type,
                items,
                self._observation("modern_recipients"),
            )

        return await self._read(
            ("modern_recipients", recipient_type.identifier),
            fetch,
            budget,
            max_age_seconds,
        )

    async def _execute_modern_send(
        self,
        attempt: SendAttempt,
        submission: ModernSendSubmission,
        budget: RequestBudget | None,
    ) -> SendResult:
        encode_modern_send(submission, self._alias)
        deadline = asyncio.timeout(None)

        async def fetch(budget: RequestBudget, _: bool) -> SendResult:
            send = getattr(self._transport, "send_modern_message", None)
            if not callable(send):
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            # A bound cookie/account is not proof it is still valid. One fresh
            # side-effect-free identity GET prevents avoidable UNKNOWN sends.
            await self._modern_ready(budget, refresh=True)

            def dispatched() -> None:
                attempt._dispatch(
                    self._session_identity(), self._observation("modern_send_message")
                )
                for key in tuple(self._cache):
                    if isinstance(key, tuple) and key[0] == "messages_sent":
                        del self._cache[key]

            try:
                response = await send(submission, budget, dispatched)
                receipt_budget = self._receipt_budget(deadline)
                if response.status in (201, 400, 422):
                    if _media_type(response) != JSON:
                        self._invalidate_modern()
                        raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
                else:
                    self._validate_read_response(response, JSON)
                status = await self._service._parsers.run(
                    lambda body: parse_modern_send_response(body, response.status),
                    response.body,
                    receipt_budget,
                )
            except BaseException as error:
                # UNKNOWN_DELIVERY is an unqualified receipt, not session expiry.
                # A malformed body/transport/permission failure still clears it.
                if (
                    not isinstance(error, LibrusError)
                    or error.kind is not ErrorKind.UNKNOWN_DELIVERY
                ):
                    self._invalidate_modern()
                if isinstance(error, SessionExpiredError):
                    error._messages_origin = True
                raise
            return attempt._acknowledge(status)

        return await self._uncached(
            "modern_send_message",
            fetch,
            budget,
            authenticate=True,
            preserve_cancellation=True,
            deadline=deadline,
        )

    # Public reads: validate input, then describe one fetch for _read.

    async def notification_counts(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> NotificationCounts:
        """Read token-scoped menu counters, not a fresh notification poll."""

        async def fetch(budget: RequestBudget, _: bool) -> NotificationCounts:
            items = await self._page(
                "notification_counts", budget, parse_notification_counts
            )
            return NotificationCounts(
                self._session_identity(),
                items,
                self._observation("notification_counts"),
            )

        return await self._read(
            ("notification_counts",), fetch, budget, max_age_seconds
        )

    async def consume_schedule_events(
        self,
        *,
        checkpoint: Callable[[ScheduleEventResponse], Awaitable[None]],
        allow_consume_events: bool = False,
        checkpoint_timeout_seconds: float = CHECKPOINT_TIMEOUT_SECONDS,
        budget: RequestBudget | None = None,
    ) -> ScheduleEvents:
        """Consume once, checkpoint complete encoded payload before parsing.

        Callback success acknowledges consumer-owned durable storage. Callback
        failure/timeout means acknowledgement unknown, never automatic replay.
        """
        if (
            type(allow_consume_events) is not bool
            or not allow_consume_events
            or self._consuming_schedule
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        validate_checkpoint(checkpoint, checkpoint_timeout_seconds)
        self._consuming_schedule = True

        async def fetch(budget: RequestBudget, _: bool) -> ScheduleEvents:
            accepted: ScheduleEventResponse | None = None

            async def persist(wire: ScheduleEventWire) -> None:
                nonlocal accepted
                accepted = ScheduleEventResponse(
                    SCHEDULE_RESPONSE_VERSION,
                    self._session_identity(),
                    wire,
                    self._observation("consume_schedule_events"),
                )
                token = CHECKPOINT_SERVICE.set(self._service)
                try:
                    await checkpoint(accepted)
                finally:
                    CHECKPOINT_SERVICE.reset(token)

            response = await self._transport.consume_schedule_events(
                budget, persist, checkpoint_timeout_seconds
            )
            self._validate_read_response(response, HTML)
            assert accepted is not None
            return await self._decode_schedule(accepted, budget)

        try:
            return await self._uncached(
                "consume_schedule_events", fetch, budget, authenticate=True
            )
        finally:
            self._consuming_schedule = False

    async def decode_schedule_events(
        self, response: ScheduleEventResponse, *, budget: RequestBudget | None = None
    ) -> ScheduleEvents:
        """Replay a persisted envelope locally, without authentication or HTTP."""
        validate_response(
            response, self._alias, self._service._transport_limits.response_max_bytes
        )

        async def fetch(budget: RequestBudget, _: bool) -> ScheduleEvents:
            budget._receive(len(response.wire.body))
            return await self._decode_schedule(response, budget)

        return await self._uncached(
            "decode_schedule_events", fetch, budget, authenticate=False
        )

    async def _decode_schedule(
        self, response: ScheduleEventResponse, budget: RequestBudget
    ) -> ScheduleEvents:
        limits, wire = self._service._transport_limits, response.wire
        compressed = (
            bool(wire.content_codings)
            and wire.content_codings[0].strip().casefold() == "gzip"
        )
        bound = (
            min(limits.parse_max_bytes, budget.remaining_response_bytes)
            if compressed
            else limits.parse_max_bytes
        )
        body = await self._service._parsers.run(
            lambda raw: decode_payload(raw, wire, bound), wire.body, budget
        )
        if compressed:
            budget._receive(len(body))
        items = await self._service._parsers.run(parse_schedule_events, body, budget)
        return ScheduleEvents(response.identity, items, response.observation)

    async def _uncached[T](
        self,
        operation: OperationName,
        fetch: Fetch[T],
        budget: RequestBudget | None,
        *,
        authenticate: bool,
        preserve_cancellation: bool = False,
        deadline: asyncio.Timeout | None = None,
    ) -> T:
        """Own one independent operation, without caching or coalescing."""
        service = self._service
        service._bind()
        if budget is not None and not isinstance(budget, RequestBudget):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        actual = budget or service._budget()
        actual._bind_loop()
        actual.remaining_seconds()
        self._admit_operation()
        task = asyncio.create_task(
            self._execute_uncached(operation, fetch, actual, authenticate, deadline)
        )
        service._tasks.add(task)
        task.add_done_callback(service._tasks.discard)
        cancelled = False
        try:
            await asyncio.wait((task,))
            return task.result()
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if cancelled and not task.done() and not task.cancelling():
                task.cancel()
            interrupted = await join_owned(task)
            self._release_operation()
            if (
                not preserve_cancellation
                and not task.cancelled()
                and (error := task.exception()) is not None
                and isinstance(error, LibrusError)
                and error.kind is ErrorKind.CHECKPOINT
            ):
                raise LibrusError(ErrorKind.CHECKPOINT) from None
            if cancelled or interrupted:
                if service._closed and not preserve_cancellation:
                    raise LibrusError(ErrorKind.CLOSED) from None
                raise asyncio.CancelledError

    async def _execute_uncached[T](
        self,
        operation: OperationName,
        fetch: Fetch[T],
        budget: RequestBudget,
        authenticate: bool,
        deadline: asyncio.Timeout | None = None,
    ) -> T:
        started = time.monotonic()
        outcome: ErrorKind | Literal["ok", "cancelled"] = "ok"
        try:
            if deadline is None:
                deadline = asyncio.timeout(None)
            async with deadline:
                deadline.reschedule(
                    asyncio.get_running_loop().time() + budget.remaining_seconds()
                )
                async with self._lock:
                    if authenticate:
                        self._check_cooldown("authentication")
                        self._check_cooldown(operation)
                        return await self._authenticated(fetch, budget, False)
                    return await fetch(budget, False)
        except LibrusError as error:
            outcome = error.kind
            if authenticate and error.kind in (
                ErrorKind.ACCESS_DENIED,
                ErrorKind.SESSION_EXPIRED,
            ):
                self._cooldowns[operation] = (
                    time.monotonic() + self._service._transport_limits.cooldown_seconds,
                    error.kind,
                )
            raise
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except TimeoutError:
            outcome = ErrorKind.TIMEOUT
            raise LibrusError(ErrorKind.TIMEOUT) from None
        except Exception:
            # A custom transport must not leak private exception text or
            # produce a misleading success diagnostic at this owner boundary.
            outcome = ErrorKind.CONNECTION
        finally:
            self._emit(
                DiagnosticEvent(
                    operation,
                    outcome,
                    time.monotonic() - started,
                    budget.requests_dispatched,
                    budget.response_bytes,
                )
            )

        raise LibrusError(ErrorKind.CONNECTION)

    async def identity(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> Identity:
        async def fetch(budget: RequestBudget, fresh_login: bool) -> Identity:
            # A login already read the identity; reading it again is wasted.
            if not fresh_login:
                self._identity = await self._fetch_identity(budget)
            return self._session_identity()

        return await self._read(("identity",), fetch, budget, max_age_seconds)

    async def student_information(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> StudentInformation:
        async def fetch(budget: RequestBudget, _: bool) -> StudentInformation:
            fields = await self._page("student_information", budget, parse_profile)
            return StudentInformation(
                self._session_identity(),
                fields.name,
                fields.class_name,
                fields.register_number,
                fields.tutor,
                fields.school,
                fields.lucky_number,
                self._observation("student_information"),
            )

        return await self._read(
            ("student_information",), fetch, budget, max_age_seconds
        )

    async def final_grades(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> FinalGrades:
        async def fetch(budget: RequestBudget, _: bool) -> FinalGrades:
            items = await self._page("final_grades", budget, parse_final_grades)
            return FinalGrades(
                self._session_identity(), items, self._observation("final_grades")
            )

        return await self._read(("final_grades",), fetch, budget, max_age_seconds)

    async def grades(
        self,
        *,
        view: GradeView = GradeView.ALL,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Grades:
        """Select a grade view with one non-replayed view-changing POST.

        Changes the selected grade filter, not school records. A cache hit makes
        no POST. Missing inline weight/count data remains unknown.
        """
        form = grade_view_form(view)

        async def fetch(budget: RequestBudget, _: bool) -> Grades:
            records = await self._page("grades", budget, parse_grade_records, form=form)
            return Grades(
                self._session_identity(), records, self._observation("grades"), view
            )

        return await self._read(("grades", view), fetch, budget, max_age_seconds)

    async def grades_window(
        self,
        start: date,
        end: date,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> GradeWindow:
        """Inclusive civil dates, at most 366 days; averages are not dated rows.

        Filters the full grade collection, sharing its cache and coalescing.
        """
        _require_dates(start, end, max_days=GRADE_MAX_WINDOW_DAYS)
        result = await self.grades(budget=budget, max_age_seconds=max_age_seconds)
        return GradeWindow(
            result.identity,
            start,
            end,
            tuple(g for g in result.records.numeric if start <= g.day <= end),
            tuple(g for g in result.records.descriptive if start <= g.day <= end),
            result.observation,
        )

    async def attendance(
        self,
        *,
        view: AttendanceView = AttendanceView.ALL,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Attendance:
        """Read a fixed upstream attendance view without replaying its POST."""
        form = attendance_view_form(view)

        async def fetch(budget: RequestBudget, _: bool) -> Attendance:
            records = await self._page(
                "attendance", budget, parse_attendance, form=form
            )
            return Attendance(
                self._session_identity(),
                records.items,
                records.semesters,
                self._observation("attendance"),
                view,
            )

        return await self._read(("attendance", view), fetch, budget, max_age_seconds)

    async def attendance_window(
        self,
        start: date,
        end: date,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> AttendanceWindow:
        """Inclusive civil-date selection over the cached all-view collection."""
        _require_dates(start, end, max_days=ATTENDANCE_MAX_WINDOW_DAYS)
        result = await self.attendance(budget=budget, max_age_seconds=max_age_seconds)
        return AttendanceWindow(
            result.identity,
            start,
            end,
            tuple(row for row in result.items if start <= row.day <= end),
            result.observation,
        )

    async def attendance_detail(
        self,
        detail_id: str,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> AttendanceDetail:
        if type(detail_id) is not str or not NUMERIC_ID.fullmatch(detail_id):
            raise LibrusError(ErrorKind.INVALID_INPUT)

        async def fetch(budget: RequestBudget, _: bool) -> AttendanceDetail:
            content = await self._page(
                "attendance_detail",
                budget,
                parse_attendance_detail,
                reference=detail_id,
            )
            return AttendanceDetail(
                self._session_identity(),
                detail_id,
                content.fields,
                content.notes,
                self._observation("attendance_detail"),
            )

        return await self._read(
            ("attendance_detail", detail_id), fetch, budget, max_age_seconds
        )

    async def gateway_attendance(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> GatewayAttendance:
        async def fetch(budget: RequestBudget, _: bool) -> GatewayAttendance:
            items = await self._page(
                "gateway_attendance",
                budget,
                parse_gateway_attendance,
                content_type=JSON,
            )
            return GatewayAttendance(
                self._session_identity(),
                items,
                self._observation("gateway_attendance"),
            )

        return await self._read(("gateway_attendance",), fetch, budget, max_age_seconds)

    async def attendance_frequency(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> AttendanceFrequency:
        rows = await self.gateway_attendance(
            budget=budget, max_age_seconds=max_age_seconds
        )

        def semester(number: int) -> tuple[GatewayAttendanceRecord, ...]:
            return tuple(r for r in rows.items if r.semester == number)

        return AttendanceFrequency(
            rows.identity,
            summarize_frequency(semester(1), subject_policy=False),
            summarize_frequency(semester(2), subject_policy=False),
            summarize_frequency(rows.items, subject_policy=False),
            rows.observation,
        )

    async def subject_frequency(
        self,
        start: date | None = None,
        end: date | None = None,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> SubjectFrequencies:
        _require_dates(start, end, max_days=ATTENDANCE_MAX_WINDOW_DAYS)

        async def fetch(budget: RequestBudget, _: bool) -> SubjectFrequencies:
            return await self._subject_frequencies(budget, start, end)

        return await self._read(
            ("subject_frequency", start, end),
            fetch,
            budget,
            max_age_seconds,
            endpoint="gateway_attendance",
        )

    async def timetable(
        self,
        monday: date,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Timetable:
        """Select an explicit school civil week; never replay its selection POST."""
        form = timetable_form(monday)

        async def fetch(budget: RequestBudget, _: bool) -> Timetable:
            days = await self._page(
                "timetable",
                budget,
                lambda body: parse_timetable(body, monday),
                form=form,
            )
            return Timetable(
                self._session_identity(), monday, days, self._observation("timetable")
            )

        return await self._read(("timetable", monday), fetch, budget, max_age_seconds)

    async def announcements(
        self, *, budget: RequestBudget | None = None, max_age_seconds: float = 0.0
    ) -> Announcements:
        """Read ordinary announcements, with full bounded text and inert references."""

        async def fetch(budget: RequestBudget, _: bool) -> Announcements:
            items = await self._page(
                "announcements",
                budget,
                lambda body: parse_announcements(body, self._alias),
            )
            return Announcements(
                self._session_identity(), items, self._observation("announcements")
            )

        return await self._read(("announcements",), fetch, budget, max_age_seconds)

    async def agenda(
        self,
        year: int,
        month: int,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Agenda:
        form = agenda_form(year, month)

        async def fetch(budget: RequestBudget, _: bool) -> Agenda:
            days = await self._page(
                "agenda",
                budget,
                lambda body: parse_agenda(body, year, month, self._alias),
                form=form,
            )
            return Agenda(
                self._session_identity(),
                year,
                month,
                days,
                self._observation("agenda"),
            )

        return await self._read(("agenda", year, month), fetch, budget, max_age_seconds)

    async def agenda_detail(
        self,
        reference: SchoolReference,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> SchoolDetail:
        return await self._school_detail(
            "agenda_detail", reference, budget, max_age_seconds
        )

    async def homework(
        self,
        start: date,
        end: date,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Homework:
        """Assignments in an inclusive window of at most one calendar month."""
        form = homework_form(start, end)

        async def fetch(budget: RequestBudget, _: bool) -> Homework:
            items = await self._page(
                "homework",
                budget,
                lambda body: parse_homework(body, self._alias),
                form=form,
            )
            return Homework(
                self._session_identity(),
                start,
                end,
                items,
                self._observation("homework"),
            )

        return await self._read(
            ("homework", start, end), fetch, budget, max_age_seconds
        )

    async def homework_detail(
        self,
        reference: SchoolReference,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> SchoolDetail:
        return await self._school_detail(
            "homework_detail", reference, budget, max_age_seconds
        )

    async def completed_lessons_page(
        self,
        start: date,
        end: date,
        *,
        page: int = 0,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> CompletedLessonsPage:
        completed_lessons_form(start, end, page)

        async def fetch(budget: RequestBudget, _: bool) -> CompletedLessonsPage:
            return await self._lesson_page(start, end, page, budget)

        return await self._read(
            ("completed_lessons", "page", start, end, page),
            fetch,
            budget,
            max_age_seconds,
        )

    async def completed_lessons(
        self,
        start: date,
        end: date,
        *,
        cursor: CompletedLessonsCursor | None = None,
        max_pages: int = 4,
        limit: int = 128,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> CompletedLessons:
        validate_selection(start, end, cursor, max_pages, limit, self._alias)

        async def fetch(budget: RequestBudget, _: bool) -> CompletedLessons:
            return await self._lesson_batch(
                start, end, cursor, max_pages, limit, budget
            )

        return await self._read(
            ("completed_lessons", "batch", start, end, cursor, max_pages, limit),
            fetch,
            budget,
            max_age_seconds,
        )

    def stream_attachment(
        self,
        reference: MessageAttachmentReference,
        *,
        max_bytes: int = ATTACHMENT_MAX_BYTES,
        budget: RequestBudget | None = None,
    ) -> AttachmentStream:
        """Construct an uncached stream context; no content open or file writes."""
        return AttachmentStream(self, reference, max_bytes=max_bytes, budget=budget)

    async def message_content(
        self,
        reference: MessageReference,
        *,
        allow_mark_read: bool = False,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> MessageContent:
        """Open one message; received opens require explicit read-effect consent."""
        validate_reference(reference, self._alias)
        if type(allow_mark_read) is not bool or (
            reference.folder is MessageFolder.RECEIVED and not allow_mark_read
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        operation: Literal["message_content_received", "message_content_sent"] = (
            "message_content_received"
            if reference.folder is MessageFolder.RECEIVED
            else "message_content_sent"
        )

        async def fetch(budget: RequestBudget, _: bool) -> MessageContent:
            # An upstream read effect can occur even if dispatch, parsing or
            # cancellation later fails. Never retain pre-open mailbox summaries.
            if reference.folder is MessageFolder.RECEIVED:
                for key in tuple(self._cache):
                    if isinstance(key, tuple) and key[0] == "messages_received":
                        del self._cache[key]
            content = await self._page(
                operation,
                budget,
                lambda body: parse_message_content(body, reference),
                reference=reference.identifier,
            )
            return MessageContent(
                self._session_identity(),
                content,
                reference.folder is MessageFolder.RECEIVED,
                self._observation(operation),
            )

        return await self._read((operation, reference), fetch, budget, max_age_seconds)

    async def messages_page(
        self,
        folder: MessageFolder = MessageFolder.RECEIVED,
        *,
        page: int = 0,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> MessagesPage:
        """One explicit mailbox page; no body open, mark-read or send."""
        message_page_form(folder, page)
        operation: Literal["messages_received", "messages_sent"] = (
            "messages_received" if folder is MessageFolder.RECEIVED else "messages_sent"
        )

        async def fetch(budget: RequestBudget, _: bool) -> MessagesPage:
            return await self._message_page(folder, page, budget)

        return await self._read(
            (operation, "page", page), fetch, budget, max_age_seconds
        )

    async def messages(
        self,
        folder: MessageFolder = MessageFolder.RECEIVED,
        *,
        cursor: MessagesCursor | None = None,
        max_pages: int = 4,
        limit: int = 128,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Messages:
        """Bounded, deduplicated continuation under one account operation/budget."""
        validate_message_selection(folder, cursor, max_pages, limit, self._alias)
        operation: Literal["messages_received", "messages_sent"] = (
            "messages_received" if folder is MessageFolder.RECEIVED else "messages_sent"
        )

        async def fetch(budget: RequestBudget, _: bool) -> Messages:
            return await self._message_batch(folder, cursor, max_pages, limit, budget)

        return await self._read(
            (operation, "batch", cursor, max_pages, limit),
            fetch,
            budget,
            max_age_seconds,
        )

    async def recipient_groups(
        self,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> RecipientGroups:
        """Discover named group types; never send or open existing messages."""

        async def fetch(budget: RequestBudget, _: bool) -> RecipientGroups:
            groups = await self._page(
                "recipient_groups",
                budget,
                lambda body: parse_recipient_groups(body, self._alias),
            )
            return RecipientGroups(
                self._session_identity(), groups, self._observation("recipient_groups")
            )

        return await self._read(("recipient_groups",), fetch, budget, max_age_seconds)

    async def recipients(
        self,
        group: RecipientGroupReference,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Recipients:
        """One typed group lookup; duplicate labels never overwrite distinct IDs."""
        validate_group(group, self._alias)

        async def fetch(budget: RequestBudget, _: bool) -> Recipients:
            items = await self._page(
                "recipients",
                budget,
                lambda body: parse_recipients(body, group),
                form=recipient_form(group.identifier, selection_id=group.selection_id),
            )
            return Recipients(
                self._session_identity(), group, items, self._observation("recipients")
            )

        return await self._read(
            ("recipients", group.identifier, group.selection_id),
            fetch,
            budget,
            max_age_seconds,
        )

    async def recipient_group_choices(
        self,
        group: RecipientGroupReference,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> RecipientGroupChoices:
        """Discover bounded nonzero group options, never guess virtual classes."""
        validate_group(group, self._alias, choices=True)

        async def fetch(budget: RequestBudget, _: bool) -> RecipientGroupChoices:
            items = await self._page(
                "recipients",
                budget,
                lambda body: parse_recipient_group_choices(body, group),
                form=recipient_form(group.identifier),
            )
            return RecipientGroupChoices(
                self._session_identity(), group, items, self._observation("recipients")
            )

        return await self._read(
            ("recipients", "choices", group.identifier), fetch, budget, max_age_seconds
        )

    # Shared read machinery.

    async def _school_detail(
        self,
        operation: Literal["agenda_detail", "homework_detail"],
        reference: SchoolReference,
        budget: RequestBudget | None,
        max_age_seconds: float,
    ) -> SchoolDetail:
        kind = operation.removesuffix("_detail")
        if (
            not isinstance(reference, SchoolReference)
            or reference.kind != kind
            or reference.account != self._alias
            or type(reference.identifier) is not str
            or not NUMERIC_ID.fullmatch(reference.identifier)
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)

        async def fetch(budget: RequestBudget, _: bool) -> SchoolDetail:
            title, fields, notes = await self._page(
                operation,
                budget,
                parse_school_detail,
                reference=reference.identifier,
            )
            return SchoolDetail(
                self._session_identity(),
                reference,
                title,
                fields,
                notes,
                self._observation(operation),
            )

        return await self._read(
            (operation, reference.identifier), fetch, budget, max_age_seconds
        )

    async def _read[T](
        self,
        key: tuple[OperationName, *tuple[Hashable, ...]],
        fetch: Fetch[T],
        budget: RequestBudget | None,
        max_age: float,
        *,
        endpoint: str | None = None,
    ) -> T:
        """Admit, coalesce, and cache one read; the work runs as an owned task.

        The key starts with the operation name and identifies the selection.
        """
        operation = key[0]
        service = self._service
        service._bind()
        if (
            type(max_age) not in (int, float)
            or not math.isfinite(max_age)
            or not 0 <= max_age <= MAX_AGE_LIMIT_SECONDS
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if budget is not None:
            budget._bind_loop()
            budget.remaining_seconds()
        # Resolve policy before admission so a lookup failure cannot leak a slot.
        retry_safe = ENDPOINTS[endpoint or operation].retry_safe
        self._admit_operation()
        flight_key = (key, max_age, budget)
        flight = self._flights.get(flight_key)
        if flight is None:
            task = asyncio.create_task(
                self._execute(
                    operation,
                    key,
                    fetch,
                    budget or service._budget(),
                    max_age,
                    retry_safe,
                )
            )
            flight = _Flight(task)
            self._flights[flight_key] = flight
            service._tasks.add(task)
            task.add_done_callback(service._tasks.discard)
        flight.waiters += 1
        try:
            return cast(T, await asyncio.shield(flight.task))
        except asyncio.CancelledError:
            if service._closed:
                raise LibrusError(ErrorKind.CLOSED) from None
            raise
        finally:
            flight.waiters -= 1
            if flight.waiters == 0:
                # Remove before joining so new callers never inherit cancellation.
                if self._flights.get(flight_key) is flight:
                    del self._flights[flight_key]
                if not flight.task.done() and not flight.task.cancelling():
                    flight.task.cancel()
                await join_owned(flight.task)
            self._release_operation()

    def _admit_operation(self) -> None:
        service = self._service
        if (
            service._operations >= service._limits.operations
            or self._operations >= service._limits.operations_per_account
        ):
            raise LibrusError(ErrorKind.LIMIT)
        service._operations += 1
        self._operations += 1

    def _release_operation(self) -> None:
        self._service._operations -= 1
        self._operations -= 1
        assert self._operations >= 0
        assert self._service._operations >= 0

    async def _execute[T](
        self,
        operation: OperationName,
        key: Hashable,
        fetch: Fetch[T],
        budget: RequestBudget,
        max_age: float,
        retry_safe: bool,
    ) -> T:
        started = time.monotonic()
        outcome: ErrorKind | Literal["ok", "cancelled"] = "ok"
        try:
            async with asyncio.timeout(budget.remaining_seconds()):
                async with self._lock:
                    return await self._cached(
                        operation, key, fetch, budget, max_age, retry_safe
                    )
        except LibrusError as error:
            outcome = error.kind
            raise
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except TimeoutError:
            outcome = ErrorKind.TIMEOUT
            raise LibrusError(ErrorKind.TIMEOUT) from None
        finally:
            self._emit(
                DiagnosticEvent(
                    operation,
                    outcome,
                    time.monotonic() - started,
                    budget.requests_dispatched,
                    budget.response_bytes,
                )
            )

    def _emit(self, event: DiagnosticEvent) -> None:
        sink = self._service._diagnostic_sink
        if sink is None:
            return
        # Diagnostics must never replace an operation result or expose errors
        # from caller-supplied sinks.
        try:
            sink(event)
        except Exception:
            pass

    async def _cached[T](
        self,
        operation: OperationName,
        key: Hashable,
        fetch: Fetch[T],
        budget: RequestBudget,
        max_age: float,
        retry_safe: bool,
    ) -> T:
        self._check_cooldown("authentication")
        self._check_cooldown(operation)
        cached = self._cache.get(key)
        if max_age > 0 and cached and time.monotonic() - cached[0] <= max_age:
            return cast(T, cached[1])
        try:
            result = await self._authenticated(fetch, budget, retry_safe)
        except LibrusError as error:
            if error.kind in (ErrorKind.ACCESS_DENIED, ErrorKind.SESSION_EXPIRED):
                self._cooldowns[operation] = (
                    time.monotonic() + self._service._transport_limits.cooldown_seconds,
                    error.kind,
                )
            raise
        self._cache[key] = (time.monotonic(), result)
        if len(self._cache) > ATTENDANCE_RESULT_CACHE_SIZE:
            del self._cache[next(iter(self._cache))]
        return result

    async def _authenticated[T](
        self, fetch: Fetch[T], budget: RequestBudget, retry_safe: bool
    ) -> T:
        """Run a read in a session; recover proven expiry once for safe reads.

        Initial login is never retried: a failed credential submission must not
        be replayed. A view-changing POST is never replayed either; expiry only
        clears the session so a later explicit call can log in again.
        """
        fresh_login = self._identity is None
        if fresh_login:
            await self._authenticate(budget)
        try:
            return await fetch(budget, fresh_login)
        except SessionExpiredError as error:
            modern_expired = error._messages_origin
            if modern_expired:
                self._invalidate_modern()
            else:
                self._invalidate()
            if not retry_safe:
                raise
        if not modern_expired:
            await self._authenticate(budget)
        try:
            return await fetch(budget, not modern_expired)
        except SessionExpiredError as error:
            if error._messages_origin:
                self._invalidate_modern()
            else:
                self._invalidate()
            raise

    async def _page[T](
        self,
        endpoint: str,
        budget: RequestBudget,
        parse: Callable[[bytes], T],
        *,
        form: RequestForm = None,
        reference: str | None = None,
        content_type: str = HTML,
    ) -> T:
        """One authenticated request whose body a pure parser turns into data."""
        try:
            response = await self._transport.request(
                endpoint, budget, form=form, reference_id=reference
            )
            self._validate_read_response(response, content_type)
            return await self._service._parsers.run(parse, response.body, budget)
        except BaseException as error:
            if ENDPOINTS[endpoint].origin == "messages":
                self._invalidate_modern()
                if isinstance(error, SessionExpiredError):
                    error._messages_origin = True
            raise

    def _check_cooldown(self, key: str) -> None:
        cooldown = self._cooldowns.get(key)
        if cooldown and time.monotonic() < cooldown[0]:
            raise LibrusError(cooldown[1])

    def _invalidate(self) -> None:
        self._identity = None
        self._modern_account = None
        self._cache.clear()
        self._metadata.clear()
        self._transport.clear_auth()

    def _invalidate_modern(self) -> None:
        self._modern_account = None
        for key in tuple(self._cache):
            if isinstance(key, tuple) and str(key[0]).startswith("modern_"):
                del self._cache[key]
        if self._transport_instance is not None:
            clear = getattr(self._transport_instance, "clear_modern_auth", None)
            if callable(clear):
                clear()

    def _session_identity(self) -> Identity:
        assert self._identity is not None
        return self._identity

    def _observation(self, source: str) -> Observation:
        return Observation(self._alias, datetime.now(UTC), self._generation, source)

    # Multi-request reads.

    async def _message_page(
        self, folder: MessageFolder, page: int, budget: RequestBudget
    ) -> MessagesPage:
        operation = "messages_" + folder.value
        items, count, fingerprint = await self._page(
            operation,
            budget,
            lambda body: parse_messages(body, folder, page, self._alias),
            form=message_page_form(folder, page),
        )
        return MessagesPage(
            self._session_identity(),
            folder,
            page,
            count,
            items,
            fingerprint,
            self._observation(operation),
        )

    async def _message_batch(
        self,
        folder: MessageFolder,
        cursor: MessagesCursor | None,
        max_pages: int,
        limit: int,
        budget: RequestBudget,
    ) -> Messages:
        page, offset = (cursor.page, cursor.offset) if cursor else (0, 0)
        count = cursor.page_count if cursor else None
        history = list(cursor.seen_ids) if cursor else []
        seen = set(history)
        fingerprints = {cursor.fingerprint} if cursor and not offset else set()
        items: list[MessageSummary] = []
        duplicates = 0
        next_cursor = None
        for fetched in range(1, max_pages + 1):
            result = await self._message_page(folder, page, budget)
            drifted = (
                cursor is not None
                and fetched == 1
                and offset > 0
                and cursor.fingerprint != result.fingerprint
            )
            if (
                (count is not None and count != result.page_count)
                or drifted
                or result.fingerprint in fingerprints
                or (offset and offset >= len(result.items))
                or (
                    result.items
                    and offset == 0
                    and all(r.reference.identifier in seen for r in result.items)
                )
            ):
                raise LibrusError(ErrorKind.STALE_CURSOR)
            count = result.page_count
            fingerprints.add(result.fingerprint)
            while offset < len(result.items) and len(items) < limit:
                item = result.items[offset]
                offset += 1
                if item.reference.identifier in seen:
                    duplicates += 1
                    continue
                if len(seen) >= MESSAGE_MAX_CURSOR_IDS:
                    raise LibrusError(ErrorKind.LIMIT)
                seen.add(item.reference.identifier)
                history.append(item.reference.identifier)
                items.append(item)
            if offset == len(result.items):
                if page + 1 == count:
                    break
                page, offset = page + 1, 0
            if offset or len(items) == limit or fetched == max_pages:
                next_cursor = MessagesCursor(
                    self._alias,
                    folder,
                    page,
                    offset,
                    count,
                    result.fingerprint,
                    tuple(history),
                )
                break
        return Messages(
            self._session_identity(),
            folder,
            tuple(items),
            fetched,
            duplicates,
            next_cursor,
            ("item_limit" if len(items) == limit else "page_limit")
            if next_cursor
            else None,
            self._observation("messages_" + folder.value),
        )

    async def _lesson_page(
        self, start: date, end: date, page: int, budget: RequestBudget
    ) -> CompletedLessonsPage:
        items, count, fingerprint = await self._page(
            "completed_lessons",
            budget,
            lambda body: parse_completed_lessons(body, start, end, page),
            form=completed_lessons_form(start, end, page),
        )
        return CompletedLessonsPage(
            self._session_identity(),
            start,
            end,
            page,
            count,
            items,
            fingerprint,
            self._observation("completed_lessons"),
        )

    async def _lesson_batch(
        self,
        start: date,
        end: date,
        cursor: CompletedLessonsCursor | None,
        max_pages: int,
        limit: int,
        budget: RequestBudget,
    ) -> CompletedLessons:
        """Read pages until the limit, the last page, or max_pages.

        Pages are not a snapshot: a resumed page must still match the cursor's
        fingerprint, and a repeated page or changed page count fails the batch.
        """
        page, offset = (cursor.page, cursor.offset) if cursor else (0, 0)
        count = cursor.page_count if cursor else None
        seen = {cursor.fingerprint} if cursor and not cursor.offset else set()
        items: list[CompletedLesson] = []
        next_cursor = None
        fetched = 0
        while fetched < max_pages:
            fetched += 1
            result = await self._lesson_page(start, end, page, budget)
            drifted = (
                cursor is not None
                and fetched == 1
                and offset > 0
                and cursor.fingerprint != result.fingerprint
            )
            if (
                (count is not None and count != result.page_count)
                or drifted
                or result.fingerprint in seen
                or (offset and offset >= len(result.items))
            ):
                raise LibrusError(ErrorKind.STALE_CURSOR)
            count = result.page_count
            seen.add(result.fingerprint)
            take = min(len(result.items) - offset, limit - len(items))
            items.extend(result.items[offset : offset + take])
            offset += take
            if offset == len(result.items):
                if page + 1 == count:
                    break
                page, offset = page + 1, 0
            if offset or len(items) == limit or fetched == max_pages:
                next_cursor = CompletedLessonsCursor(
                    self._alias, start, end, page, offset, count, result.fingerprint
                )
                break
        return CompletedLessons(
            self._session_identity(),
            start,
            end,
            tuple(items),
            fetched,
            next_cursor,
            self._observation("completed_lessons"),
        )

    async def _metadata_value(
        self, endpoint: str, identifier: str, budget: RequestBudget
    ) -> str:
        key = endpoint, identifier
        cached = self._metadata.get(key)
        if cached and time.monotonic() - cached[0] <= ATTENDANCE_METADATA_TTL_SECONDS:
            return cached[1]
        parser = (
            parse_lesson_subject
            if endpoint == "attendance_lesson"
            else parse_subject_name
        )
        value = await self._page(
            endpoint,
            budget,
            lambda body: parser(body, identifier),
            reference=identifier,
            content_type=JSON,
        )
        self._metadata[key] = time.monotonic(), value
        if len(self._metadata) > ATTENDANCE_METADATA_CACHE_SIZE:
            del self._metadata[next(iter(self._metadata))]
        return value

    async def _subject_frequencies(
        self, budget: RequestBudget, start: date | None, end: date | None
    ) -> SubjectFrequencies:
        collection = await self._page(
            "gateway_attendance", budget, parse_gateway_attendance, content_type=JSON
        )
        observed = self._observation("gateway_attendance")
        rows = tuple(
            r
            for r in collection
            if (start is None or r.day >= start) and (end is None or r.day <= end)
        )
        lessons = dict.fromkeys(row.lesson_id for row in rows)
        if len(lessons) > ATTENDANCE_METADATA_CACHE_SIZE:
            raise LibrusError(ErrorKind.LIMIT)
        lesson_subjects = {
            lesson: await self._metadata_value("attendance_lesson", lesson, budget)
            for lesson in lessons
        }
        subjects: dict[str, list[GatewayAttendanceRecord]] = {}
        for row in rows:
            subjects.setdefault(lesson_subjects[row.lesson_id], []).append(row)
        if len(subjects) > ATTENDANCE_METADATA_CACHE_SIZE:
            raise LibrusError(ErrorKind.LIMIT)
        items = [
            SubjectFrequency(
                subject,
                await self._metadata_value("attendance_subject", subject, budget),
                summarize_frequency(tuple(records), subject_policy=True),
            )
            for subject, records in subjects.items()
        ]
        return SubjectFrequencies(
            self._session_identity(), tuple(items), start, end, observed
        )

    # Authentication and response validation.

    def _validate_read_response(
        self, response: TransportResponse, content_type: str
    ) -> None:
        if 300 <= response.status < 400:
            # A redirect proves expiry only when it targets a login route.
            # Other redirects must not trigger a new credential submission.
            if self._is_login_redirect(response):
                raise LibrusError(ErrorKind.SESSION_EXPIRED)
            raise LibrusError(ErrorKind.ACCESS_DENIED)
        if response.status != 200 or _media_type(response) != content_type:
            raise LibrusError(ErrorKind.PARSE)

    def _is_login_redirect(self, response: TransportResponse) -> bool:
        location = response.headers.get("location", "")
        try:
            target = urlsplit(urljoin(response.url, location))
        except ValueError:
            return False
        callback = ENDPOINTS["login_callback"]
        expected = urlsplit(self._service._connection.origin(callback))
        return (
            bool(location)
            and not (target.username or target.password or target.fragment)
            and (target.scheme, target.netloc) == (expected.scheme, expected.netloc)
            and target.path in (callback.path, ENDPOINTS["login_portal"].path)
        )

    async def _fetch_identity(self, budget: RequestBudget) -> Identity:
        owner, student = await self._page(
            "identity", budget, parse_identity, content_type=JSON
        )
        credentials, previous = self._credentials, self._identity
        changed = previous is not None and (owner.id, student.id) != (
            previous.owner.id,
            previous.student.id,
        )
        unexpected = (
            credentials.expected_owner_id is not None
            and owner.id != credentials.expected_owner_id
        ) or (
            credentials.expected_student_id is not None
            and student.id != credentials.expected_student_id
        )
        if changed or unexpected:
            self._invalidate()
            raise LibrusError(ErrorKind.ACCESS_DENIED)
        return Identity(owner, student, self._observation("identity"))

    async def _authenticate(self, budget: RequestBudget) -> None:
        self._invalidate()
        try:
            response = await self._transport.request("login_portal", budget)
            response = await self._redirects(response, budget)
            authorization = ENDPOINTS["login_authorization"]
            form_url = (
                self._service._connection.origin(authorization) + authorization.path
            )
            current_url = (
                urlsplit(response.url)._replace(query="", fragment="").geturl()
            )
            # A portal redirect already established API-side cookies. Fetch the
            # form only when that hop did not land on its exact approved route.
            if current_url != form_url:
                response = await self._transport.request("login_authorization", budget)
                await self._redirects(response, budget)
            response = await self._transport.request(
                "login_submit",
                budget,
                form=LoginSubmission(
                    self._credentials.login, self._credentials.password
                ),
            )
            if _media_type(response) != JSON:
                raise LibrusError(ErrorKind.ACCOUNT_ACTION_REQUIRED)
            location = await self._service._parsers.run(
                parse_login, response.body, budget
            )
            response = await self._transport.follow(response.url, location, budget)
            await self._redirects(response, budget)
            if not self._transport.has_cookie(SESSION_COOKIE, "identity"):
                raise LibrusError(ErrorKind.ACCOUNT_ACTION_REQUIRED)
            self._generation += 1
            self._identity = await self._fetch_identity(budget)
        except BaseException as error:
            self._invalidate()
            if isinstance(error, LibrusError):
                self._cooldowns["authentication"] = (
                    time.monotonic() + self._service._transport_limits.cooldown_seconds,
                    error.kind,
                )
            raise

    async def _redirects(
        self,
        response: TransportResponse,
        budget: RequestBudget,
    ) -> TransportResponse:
        for _ in range(self._service._transport_limits.max_redirects):
            if not 300 <= response.status < 400:
                if response.status != 200:
                    raise LibrusError(ErrorKind.PARSE)
                return response
            if response.status not in (301, 302, 303, 307, 308):
                raise LibrusError(ErrorKind.PARSE)
            location = response.headers.get("location", "")
            response = await self._transport.follow(response.url, location, budget)
        if 300 <= response.status < 400:
            raise LibrusError(ErrorKind.LIMIT)
        return response


def _media_type(response: TransportResponse) -> str:
    return response.headers.get("content-type", "").partition(";")[0].strip().lower()
