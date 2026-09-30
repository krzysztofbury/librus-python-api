"""Public login-scoped account service under one shared traffic boundary."""

import asyncio
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Literal, Self, cast
from urllib.parse import urljoin, urlsplit

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_none,
)

from librus_python_api.budget import RequestBudget
from librus_python_api.config import (
    ENDPOINTS,
    SESSION_COOKIE,
    AccountCredentials,
    ConnectionSettings,
    OperationLimits,
    SchedulerLimits,
    TransportLimits,
)
from librus_python_api.diagnostics import DiagnosticSink
from librus_python_api.exceptions import ErrorKind, LibrusError, SessionExpiredError
from librus_python_api.grade_parsers import parse_final_grades
from librus_python_api.lifecycle import join_owned
from librus_python_api.models import (
    DiagnosticEvent,
    FinalGrades,
    Identity,
    LoginSubmission,
    Observation,
    OperationName,
    SchedulerSnapshot,
    StudentInformation,
    TransportResponse,
)
from librus_python_api.parsers import parse_identity, parse_login, parse_profile
from librus_python_api.parsing import ParserPool
from librus_python_api.scheduler import RequestScheduler
from librus_python_api.transport import (
    AccountTransport,
    AiohttpTransport,
    TransportFactory,
)

type _ReadResult = Identity | StudentInformation | FinalGrades


@dataclass(slots=True)
class _Flight:
    task: asyncio.Task[_ReadResult]
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
        self._tasks: set[asyncio.Task[_ReadResult]] = set()
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
        self._transport_instance: AccountTransport | None = None
        self._lock = asyncio.Lock()
        self._flights: dict[
            tuple[OperationName, float, RequestBudget | None], _Flight
        ] = {}
        self._operations = 0
        self._generation = 0
        self._identity: Identity | None = None
        self._cache: dict[str, tuple[float, _ReadResult]] = {}
        self._cooldowns: dict[str, tuple[float, ErrorKind]] = {}

    @property
    def _transport(self) -> AccountTransport:
        if self._transport_instance is None:
            self._transport_instance = self._service._transport(self._alias)
        return self._transport_instance

    async def identity(
        self,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> Identity:
        return cast(Identity, await self._read("identity", budget, max_age_seconds))

    async def student_information(
        self,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> StudentInformation:
        return cast(
            StudentInformation,
            await self._read("student_information", budget, max_age_seconds),
        )

    async def final_grades(
        self,
        *,
        budget: RequestBudget | None = None,
        max_age_seconds: float = 0.0,
    ) -> FinalGrades:
        return cast(
            FinalGrades, await self._read("final_grades", budget, max_age_seconds)
        )

    async def _read(
        self,
        operation: OperationName,
        budget: RequestBudget | None,
        max_age: float,
    ) -> _ReadResult:
        service = self._service
        service._bind()
        if (
            type(max_age) not in (int, float)
            or not math.isfinite(max_age)
            or not 0 <= max_age <= 3600
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if budget is not None:
            budget._bind_loop()
            budget.remaining_seconds()
        if (
            service._operations >= service._limits.operations
            or self._operations >= service._limits.operations_per_account
        ):
            raise LibrusError(ErrorKind.LIMIT)
        service._operations += 1
        self._operations += 1
        key = (operation, max_age, budget)
        flight = self._flights.get(key)
        if flight is None:
            task = asyncio.create_task(
                self._execute(operation, budget or service._budget(), max_age)
            )
            flight = _Flight(task)
            self._flights[key] = flight
            service._tasks.add(task)
            task.add_done_callback(service._tasks.discard)
        flight.waiters += 1
        try:
            return await asyncio.shield(flight.task)
        except asyncio.CancelledError:
            if service._closed:
                raise LibrusError(ErrorKind.CLOSED) from None
            raise
        finally:
            flight.waiters -= 1
            if flight.waiters == 0:
                # Remove before joining so new callers never inherit cancellation.
                if self._flights.get(key) is flight:
                    del self._flights[key]
                if not flight.task.done() and not flight.task.cancelling():
                    flight.task.cancel()
                await join_owned(flight.task)
            service._operations -= 1
            self._operations -= 1

    async def _execute(
        self,
        operation: OperationName,
        budget: RequestBudget,
        max_age: float,
    ) -> _ReadResult:
        started = time.monotonic()
        outcome: ErrorKind | Literal["ok", "cancelled"] = "ok"
        try:
            return await self._perform(operation, budget, max_age)
        except LibrusError as error:
            outcome = error.kind
            raise
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            sink = self._service._diagnostic_sink
            if sink is not None:
                event = DiagnosticEvent(
                    operation,
                    outcome,
                    time.monotonic() - started,
                    budget.requests_dispatched,
                    budget.response_bytes,
                )
                # Diagnostics must never replace an operation result or expose
                # errors from caller-supplied sinks.
                try:
                    sink(event)
                except Exception:
                    pass

    async def _perform(
        self,
        operation: OperationName,
        budget: RequestBudget,
        max_age: float,
    ) -> _ReadResult:
        timed_out = False
        try:
            async with asyncio.timeout(budget.remaining_seconds()):
                async with self._lock:
                    self._check_cooldown("authentication")
                    self._check_cooldown(operation)
                    cached = self._cache.get(operation)
                    if (
                        max_age > 0
                        and cached
                        and time.monotonic() - cached[0] <= max_age
                    ):
                        return cached[1]
                    try:
                        result = await self._retrieve(operation, budget)
                    except LibrusError as error:
                        if error.kind in (
                            ErrorKind.ACCESS_DENIED,
                            ErrorKind.SESSION_EXPIRED,
                        ):
                            self._cooldowns[operation] = (
                                time.monotonic()
                                + self._service._transport_limits.cooldown_seconds,
                                error.kind,
                            )
                        raise
                    self._cache[operation] = (time.monotonic(), result)
                    return result
        except TimeoutError:
            timed_out = True
        assert timed_out
        raise LibrusError(ErrorKind.TIMEOUT)

    def _check_cooldown(self, key: str) -> None:
        cooldown = self._cooldowns.get(key)
        if cooldown and time.monotonic() < cooldown[0]:
            raise LibrusError(cooldown[1])

    def _invalidate(self) -> None:
        self._identity = None
        self._cache.clear()
        self._transport.clear_auth()

    async def _retrieve(
        self,
        operation: OperationName,
        budget: RequestBudget,
    ) -> _ReadResult:
        authenticated_now = self._identity is None
        # Initial login is outside retries: a failed credential submission must
        # never be replayed by a generic retry policy.
        if authenticated_now:
            await self._authenticate(budget)
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(SessionExpiredError),
            stop=stop_after_attempt(2),
            wait=wait_none(),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                if self._identity is None:
                    await self._authenticate(budget)
                    authenticated_now = True
                try:
                    return await self._read_authenticated(
                        operation, budget, authenticated_now
                    )
                except SessionExpiredError:
                    self._invalidate()
                    raise
        raise AssertionError("Bounded recovery exhausted")

    async def _read_authenticated(
        self,
        operation: OperationName,
        budget: RequestBudget,
        authenticated_now: bool,
    ) -> _ReadResult:
        assert self._identity is not None
        if operation == "identity":
            if authenticated_now:
                return self._identity
            self._identity = await self._fetch_identity(budget)
            return self._identity
        response = await self._transport.request(operation, budget)
        self._validate_read_response(response)
        if (
            response.headers.get("content-type", "").partition(";")[0].strip().lower()
            != "text/html"
        ):
            raise LibrusError(ErrorKind.PARSE)
        if operation == "final_grades":
            items = await self._service._parsers.run(
                parse_final_grades, response.body, budget
            )
            return FinalGrades(self._identity, items, self._observation(operation))
        assert operation == "student_information"
        fields = await self._service._parsers.run(parse_profile, response.body, budget)
        return StudentInformation(
            self._identity,
            fields.name,
            fields.class_name,
            fields.register_number,
            fields.tutor,
            fields.school,
            fields.lucky_number,
            self._observation("student_information"),
        )

    def _observation(self, source: str) -> Observation:
        return Observation(self._alias, datetime.now(UTC), self._generation, source)

    def _validate_read_response(self, response: TransportResponse) -> None:
        # A redirect is expiry evidence only for a configured login destination.
        # Other redirects must not trigger a new credential submission.
        if 300 <= response.status < 400:
            location = response.headers.get("location", "")
            failed = False
            try:
                target = urlsplit(urljoin(response.url, location))
                if (
                    not location
                    or target.username
                    or target.password
                    or target.fragment
                ):
                    raise ValueError
                endpoint = ENDPOINTS["login_callback"]
                expected = urlsplit(self._service._connection.origin(endpoint))
                if (target.scheme, target.netloc) != (expected.scheme, expected.netloc):
                    raise ValueError
                if target.path not in (
                    ENDPOINTS["login_callback"].path,
                    ENDPOINTS["login_portal"].path,
                ):
                    raise ValueError
            except ValueError:
                failed = True
            if failed:
                raise LibrusError(ErrorKind.ACCESS_DENIED)
            raise LibrusError(ErrorKind.SESSION_EXPIRED)
        if response.status != 200:
            raise LibrusError(ErrorKind.PARSE)

    async def _fetch_identity(self, budget: RequestBudget) -> Identity:
        response = await self._transport.request("identity", budget)
        self._validate_read_response(response)
        if (
            response.headers.get("content-type", "").partition(";")[0].strip().lower()
            != "application/json"
        ):
            raise LibrusError(ErrorKind.PARSE)
        owner, student = await self._service._parsers.run(
            parse_identity, response.body, budget
        )
        credentials = self._credentials
        previous = self._identity
        if previous is not None and (owner.id, student.id) != (
            previous.owner.id,
            previous.student.id,
        ):
            self._invalidate()
            raise LibrusError(ErrorKind.ACCESS_DENIED)
        if (
            credentials.expected_owner_id is not None
            and owner.id != credentials.expected_owner_id
        ) or (
            credentials.expected_student_id is not None
            and student.id != credentials.expected_student_id
        ):
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
            if (
                response.headers.get("content-type", "")
                .partition(";")[0]
                .strip()
                .lower()
                != "application/json"
            ):
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
