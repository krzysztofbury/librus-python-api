import asyncio
import gzip
from contextlib import AsyncExitStack

import pytest
from aiohttp import web
from pydantic import SecretStr

from librus_python_api.budget import RequestBudget
from librus_python_api.config import (
    ConnectionSettings,
    SchedulerLimits,
    TransportLimits,
)
from librus_python_api.errors import ErrorKind, LibrusError
from librus_python_api.models import LoginSubmission
from librus_python_api.scheduler import RequestScheduler
from librus_python_api.transport import AiohttpTransport
from tests.http_support import serve


def test_native_transport_preserves_account_cookies_and_isolates_sessions() -> None:
    async def scenario() -> None:
        async def submit(request: web.Request) -> web.Response:
            data = await request.post()
            response = web.Response(text="{}")
            response.set_cookie("oauth_token", str(data["login"]), path="/")
            response.set_cookie("DeviceCookie", "synthetic-device", path="/OAuth")
            return response

        async def profile(request: web.Request) -> web.Response:
            assert "DeviceCookie" not in request.cookies
            return web.Response(text=request.cookies["oauth_token"])

        app = web.Application()
        app.router.add_post("/OAuth/Authorization", submit)
        app.router.add_get("/gateway/api/2.0/Me", profile)
        async with serve(app) as url, AsyncExitStack() as stack:
            scheduler = await stack.enter_async_context(
                RequestScheduler(
                    ("a", "b"),
                    limits=SchedulerLimits(requests_per_second=1000, burst=8),
                )
            )
            transports = []
            for key in ("a", "b"):
                transport = AiohttpTransport(
                    key,
                    scheduler,
                    ConnectionSettings(synergia_origin=url, api_origin=url),
                    TransportLimits(),
                )
                stack.push_async_callback(transport.aclose)
                transports.append(transport)
                await transport.request(
                    "login_submit",
                    RequestBudget(),
                    form=LoginSubmission(
                        SecretStr(key), SecretStr(f"fixture-only-{key}")
                    ),
                )
            results = await asyncio.gather(
                *(item.request("identity", RequestBudget()) for item in transports)
            )
            assert [item.body for item in results] == [b"a", b"b"]
            assert "synthetic-device" not in repr(results)
            assert transports[0].has_cookie("DeviceCookie", "login_authorization")
            assert not transports[0].has_cookie("DeviceCookie", "identity")
            transports[0].clear_auth()
            assert not transports[0].has_cookie("oauth_token", "identity")
            assert transports[0].has_cookie("DeviceCookie", "login_authorization")
            assert transports[1].has_cookie("oauth_token", "identity")

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["declared", "chunked", "compressed"])
def test_body_limits_apply_before_decoding_or_parsing(kind: str) -> None:
    async def scenario() -> None:
        async def handler(request: web.Request) -> web.StreamResponse:
            if kind == "chunked":
                response = web.StreamResponse()
                await response.prepare(request)
                await response.write(b"x" * 65)
                await response.write_eof()
                return response
            if kind == "compressed":
                return web.Response(
                    body=gzip.compress(b"x" * 4096),
                    headers={
                        "Content-Encoding": "gzip",
                    },
                )
            return web.Response(body=b"x" * 65)

        app = web.Application()
        app.router.add_get("/gateway/api/2.0/Me", handler)
        async with serve(app) as url, RequestScheduler(("a",)) as scheduler:
            transport = AiohttpTransport(
                "a",
                scheduler,
                ConnectionSettings(synergia_origin=url, api_origin=url),
                TransportLimits(response_max_bytes=64),
            )
            try:
                with pytest.raises(LibrusError, match="^limit$"):
                    await transport.request("identity", RequestBudget())
                assert scheduler.snapshot().active == 0
            finally:
                await transport.aclose()

    asyncio.run(scenario())


def test_cumulative_body_budget_stops_dispatch_after_exhaustion() -> None:
    async def scenario() -> None:
        calls = 0

        async def handler(request: web.Request) -> web.Response:
            nonlocal calls
            calls += 1
            return web.Response(body=b"body")

        app = web.Application()
        app.router.add_get("/gateway/api/2.0/Me", handler)
        async with serve(app) as url, RequestScheduler(("a",)) as scheduler:
            transport = AiohttpTransport(
                "a",
                scheduler,
                ConnectionSettings(synergia_origin=url, api_origin=url),
                TransportLimits(),
            )
            try:
                budget = RequestBudget(max_response_bytes=4)
                assert (await transport.request("identity", budget)).body == b"body"
                with pytest.raises(LibrusError, match="^limit$"):
                    await transport.request("identity", budget)
                assert calls == budget.requests_dispatched == 1
                assert budget.response_bytes == 4
            finally:
                await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "location",
    [
        "https://example.invalid/steal",
        "/terminarz/dodane_od_ostatniego_logowania",
        "/informacja",
        "http://user:secret@localhost/loguj",
        "/loguj#fragment",
    ],
)
def test_redirects_cannot_dispatch_foreign_or_non_authentication_requests(
    location: str,
) -> None:
    async def scenario() -> None:
        async with RequestScheduler(("a",)) as scheduler:
            transport = AiohttpTransport(
                "a",
                scheduler,
                ConnectionSettings(
                    synergia_origin="http://localhost:8080",
                    api_origin="http://localhost:8080",
                ),
                TransportLimits(),
            )
            budget = RequestBudget()
            with pytest.raises(LibrusError, match="^access_denied$") as caught:
                await transport.follow("http://localhost:8080/loguj", location, budget)
            assert caught.value.__context__ is None
            assert budget.requests_dispatched == 0
            await transport.aclose()

    asyncio.run(scenario())


def test_slow_body_timeout_releases_connector_before_next_request() -> None:
    async def scenario() -> None:
        release = asyncio.Event()
        count = 0

        async def handler(request: web.Request) -> web.StreamResponse:
            nonlocal count
            count += 1
            if count > 1:
                return web.Response(body=b"ok")
            response = web.StreamResponse()
            await response.prepare(request)
            await release.wait()
            return response

        app = web.Application()
        app.router.add_get("/gateway/api/2.0/Me", handler)
        async with (
            serve(app) as url,
            RequestScheduler(
                ("a",),
                limits=SchedulerLimits(
                    requests_per_second=1000,
                    burst=3,
                ),
            ) as scheduler,
        ):
            transport = AiohttpTransport(
                "a",
                scheduler,
                ConnectionSettings(synergia_origin=url, api_origin=url),
                TransportLimits(),
            )
            try:
                with pytest.raises(LibrusError, match="^timeout$"):
                    await transport.request(
                        "identity", RequestBudget(timeout_seconds=0.03)
                    )
                assert (
                    await transport.request("identity", RequestBudget())
                ).body == b"ok"
            finally:
                release.set()
                await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, ErrorKind.SESSION_EXPIRED),
        (403, ErrorKind.ACCESS_DENIED),
        (429, ErrorKind.THROTTLED),
        (503, ErrorKind.MAINTENANCE),
    ],
)
def test_status_classification_does_not_attach_private_body(
    status: int, kind: ErrorKind
) -> None:
    async def scenario() -> None:
        async def handler(request: web.Request) -> web.Response:
            return web.Response(status=status, text="fixture private content")

        app = web.Application()
        app.router.add_get("/gateway/api/2.0/Me", handler)
        async with serve(app) as url, RequestScheduler(("a",)) as scheduler:
            transport = AiohttpTransport(
                "a",
                scheduler,
                ConnectionSettings(synergia_origin=url, api_origin=url),
                TransportLimits(),
            )
            try:
                with pytest.raises(LibrusError) as caught:
                    await transport.request("identity", RequestBudget())
                assert caught.value.kind == kind
                assert "private" not in repr(caught.value)
            finally:
                await transport.aclose()

    asyncio.run(scenario())
