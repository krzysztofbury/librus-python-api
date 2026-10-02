"""Account-isolated aiohttp transport and explicit injection contract."""

import math
import re
import zlib
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import partial
from types import MappingProxyType
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import aiohttp
from yarl import URL

from librus_python_api.budget import RequestBudget
from librus_python_api.config import (
    AUTH_COOKIES,
    ENDPOINTS,
    OAUTH_QUERY,
    USER_AGENT,
    ConnectionSettings,
    Endpoint,
    SideEffect,
    TransportLimits,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import LoginSubmission, RequestForm, TransportResponse
from librus_python_api.scheduler import RequestScheduler


class AccountTransport(Protocol):
    """A factory-created, exclusively owned transport for one login context.

    Custom implementations must preserve the scheduler, isolation, byte limits,
    destination validation, and joined cancellation guarantees. The service
    owns and closes factory results; shared transport instances are rejected.
    """

    async def request(
        self,
        endpoint_id: str,
        budget: RequestBudget,
        *,
        form: RequestForm = None,
        reference_id: str | None = None,
    ) -> TransportResponse: ...

    async def follow(
        self,
        previous_url: str,
        location: str,
        budget: RequestBudget,
    ) -> TransportResponse: ...

    def has_cookie(self, name: str, endpoint_id: str) -> bool: ...
    def clear_auth(self) -> None: ...
    async def aclose(self) -> None: ...


class TransportFactory(Protocol):
    def __call__(
        self,
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
    ) -> AccountTransport: ...


def _check_form(endpoint: Endpoint, form: RequestForm) -> None:
    """Credentials go only to the login submission; other POSTs need a form."""
    if endpoint.operation_id == "login_submit":
        valid = isinstance(form, LoginSubmission) and (
            1 <= len(form.login.get_secret_value()) <= 256
            and 1 <= len(form.password.get_secret_value()) <= 1024
        )
    elif endpoint.method == "POST":
        valid = isinstance(form, Mapping) and all(
            type(key) is str and type(value) is str for key, value in form.items()
        )
    else:
        valid = form is None
    if not valid:
        raise LibrusError(ErrorKind.INVALID_INPUT)


class AiohttpTransport:
    def __init__(
        self,
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
    ) -> None:
        self._account, self._scheduler = account, scheduler
        self._connection, self._limits = connection, limits
        self._session: aiohttp.ClientSession | None = None
        self._closed = False

    def _get_session(self) -> aiohttp.ClientSession:
        if self._closed:
            raise LibrusError(ErrorKind.CLOSED)
        if self._session is None:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(
                    limit=1,
                    ssl=self._connection.ssl_context or True,
                ),
                cookie_jar=aiohttp.CookieJar(),
                trust_env=False,
                auto_decompress=False,
                read_bufsize=16 * 1024,
                timeout=aiohttp.ClientTimeout(
                    total=self._limits.request_timeout_seconds,
                    connect=self._limits.connect_timeout_seconds,
                ),
                headers={"Accept-Encoding": "identity", "User-Agent": USER_AGENT},
            )
        return self._session

    def _url(self, endpoint: Endpoint) -> str:
        return self._connection.origin(endpoint) + endpoint.path

    async def request(
        self,
        endpoint_id: str,
        budget: RequestBudget,
        *,
        form: RequestForm = None,
        reference_id: str | None = None,
    ) -> TransportResponse:
        endpoint = ENDPOINTS.get(endpoint_id)
        if endpoint is None:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        url = self._url(endpoint)
        if "{id}" in endpoint.path:
            if type(reference_id) is not str or not re.fullmatch(
                r"[0-9]{1,64}", reference_id
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
            url = url.replace("{id}", reference_id)
        elif reference_id is not None:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if endpoint.origin == "api":
            url = str(URL(url).with_query(OAUTH_QUERY))
        return await self._request(endpoint, url, budget, form)

    async def follow(
        self,
        previous_url: str,
        location: str,
        budget: RequestBudget,
    ) -> TransportResponse:
        failed = False
        try:
            if not location or len(location) > 4096:
                raise ValueError
            url = urljoin(previous_url, location)
            parsed = urlsplit(url)
            if (
                parsed.username
                or parsed.password
                or parsed.fragment
                or "%" in parsed.path
            ):
                raise ValueError
            endpoint = next(
                (
                    item
                    for item in ENDPOINTS.values()
                    if item.method == "GET"
                    and item.side_effect == SideEffect.AUTHENTICATION
                    and parsed.path == item.path
                    and URL(url).origin() == URL(self._connection.origin(item))
                ),
                None,
            )
            if endpoint is None:
                raise ValueError
        except ValueError:
            failed = True
        if failed:
            raise LibrusError(ErrorKind.ACCESS_DENIED)
        assert endpoint is not None
        return await self._request(endpoint, url, budget, None)

    async def _request(
        self,
        endpoint: Endpoint,
        url: str,
        budget: RequestBudget,
        form: RequestForm,
    ) -> TransportResponse:
        if self._closed:
            raise LibrusError(ErrorKind.CLOSED)
        _check_form(endpoint, form)
        kind: ErrorKind | None = None
        try:
            return await self._scheduler.run(
                self._account,
                budget,
                partial(self._exchange, endpoint, url, budget, form),
            )
        except aiohttp.ClientError:
            kind = ErrorKind.CONNECTION
        except TimeoutError:
            kind = ErrorKind.TIMEOUT
        except zlib.error:
            kind = ErrorKind.PARSE
        except (ValueError, OverflowError):
            kind = ErrorKind.PARSE
        assert kind is not None
        raise LibrusError(kind)

    async def _exchange(
        self,
        endpoint: Endpoint,
        url: str,
        budget: RequestBudget,
        form: RequestForm,
    ) -> TransportResponse:
        session = self._get_session()
        proxy = self._connection.proxy_url
        headers = None
        if isinstance(form, LoginSubmission):
            headers = {
                "Origin": self._connection.api_origin,
                "Referer": str(URL(self._url(endpoint)).with_query(OAUTH_QUERY)),
                "X-Requested-With": "XMLHttpRequest",
            }
        payload: dict[str, str] | None = None
        if isinstance(form, LoginSubmission):
            payload = {
                "action": "login",
                "login": form.login.get_secret_value(),
                "pass": form.password.get_secret_value(),
            }
        elif form is not None:
            payload = dict(form)
        async with session.request(
            endpoint.method,
            url,
            data=payload,
            headers=headers,
            allow_redirects=False,
            proxy=proxy.get_secret_value() if proxy is not None else None,
        ) as response:
            if (
                len(response.headers) > 128
                or sum(len(k) + len(v) for k, v in response.headers.items()) > 32 * 1024
                or len(response.headers.getall("Location", [])) > 1
            ):
                raise LibrusError(ErrorKind.LIMIT)
            if len(session.cookie_jar) > self._limits.max_cookies:
                session.cookie_jar.clear()
                raise LibrusError(ErrorKind.LIMIT)
            self._check_status(response)
            body = await self._read_body(response, budget)
            return TransportResponse(
                response.status,
                body,
                str(response.url),
                MappingProxyType({k.lower(): v for k, v in response.headers.items()}),
            )

    def _check_status(self, response: aiohttp.ClientResponse) -> None:
        if response.status in (429, 503):
            pause = self._limits.cooldown_seconds
            value = response.headers.get("Retry-After", "")
            try:
                if value and len(value) <= 64:
                    try:
                        seconds = float(value)
                    except ValueError:
                        instant = parsedate_to_datetime(value)
                        seconds = (instant - datetime.now(UTC)).total_seconds()
                    if math.isfinite(seconds) and seconds >= 0:
                        # Avoid platform timer overflow from untrusted headers.
                        pause = max(pause, min(seconds, 24 * 60 * 60))
            except (ValueError, TypeError, OverflowError):
                pass
            self._scheduler.pause_for(pause)
        kinds = {
            401: ErrorKind.SESSION_EXPIRED,
            403: ErrorKind.ACCESS_DENIED,
            429: ErrorKind.THROTTLED,
            503: ErrorKind.MAINTENANCE,
        }
        if response.status in kinds:
            raise LibrusError(kinds[response.status])
        if response.status >= 400:
            raise LibrusError(ErrorKind.CONNECTION)

    async def _read_body(
        self,
        response: aiohttp.ClientResponse,
        budget: RequestBudget,
    ) -> bytes:
        if response.content_length is not None and (
            response.content_length > self._limits.response_max_bytes
            or response.content_length > budget.remaining_response_bytes
        ):
            raise LibrusError(ErrorKind.LIMIT)
        encoding = response.headers.get("Content-Encoding", "identity").lower()
        if encoding not in ("identity", "gzip"):
            raise LibrusError(ErrorKind.PARSE)
        inflater = (
            zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
        )
        body = bytearray()
        wire_bytes = 0
        async for chunk in response.content.iter_chunked(16 * 1024):
            wire_bytes += len(chunk)
            budget._receive(len(chunk))
            if wire_bytes > self._limits.response_max_bytes:
                raise LibrusError(ErrorKind.LIMIT)
            if inflater is not None:
                available = min(
                    self._limits.response_max_bytes - len(body),
                    budget.remaining_response_bytes,
                )
                chunk = inflater.decompress(chunk, available + 1)
                budget._receive(len(chunk))
            if len(body) + len(chunk) > self._limits.response_max_bytes:
                raise LibrusError(ErrorKind.LIMIT)
            body.extend(chunk)
        if inflater is not None and (not inflater.eof or inflater.unused_data):
            raise LibrusError(ErrorKind.PARSE)
        return bytes(body)

    def has_cookie(self, name: str, endpoint_id: str) -> bool:
        if self._session is None:
            return False
        url = URL(self._url(ENDPOINTS[endpoint_id]))
        return name in self._session.cookie_jar.filter_cookies(url)

    def clear_auth(self) -> None:
        if self._session is not None:
            self._session.cookie_jar.clear(lambda cookie: cookie.key in AUTH_COOKIES)

    async def aclose(self) -> None:
        self._closed = True
        if self._session is not None:
            await self._session.close()
