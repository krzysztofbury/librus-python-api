import asyncio
import gzip
import socket
import time
from contextlib import AsyncExitStack
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from pydantic import SecretStr

from librus_python_api.budget import RequestBudget
from librus_python_api.config import (
    ConnectionSettings,
    SchedulerLimits,
    TransportLimits,
    recipient_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import LoginSubmission
from librus_python_api.scheduler import RequestScheduler
from librus_python_api.transport import AiohttpTransport
from tests.http_support import serve


def test_read_effect_get_is_not_replayed_after_stale_keepalive_disconnect() -> None:
    async def scenario() -> None:
        calls = 0

        async def warm(request: web.Request) -> web.Response:
            return web.Response(text="warm")

        async def open_message(request: web.Request) -> web.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                assert request.transport is not None
                request.transport.close()
            return web.Response(text="content")

        app = web.Application()
        app.router.add_get("/gateway/api/2.0/Me", warm)
        app.router.add_get("/wiadomosci/1/5/{id}", open_message)
        async with serve(app) as origin, RequestScheduler(("a",)) as scheduler:
            transport = AiohttpTransport(
                "a",
                scheduler,
                ConnectionSettings(synergia_origin=origin, api_origin=origin),
                TransportLimits(),
            )
            try:
                await transport.request("identity", RequestBudget())
                budget = RequestBudget(max_requests=1)
                with pytest.raises(LibrusError, match="^connection$"):
                    await transport.request(
                        "message_content_received", budget, reference_id="101"
                    )
                assert calls == budget.requests_dispatched == 1
            finally:
                await transport.aclose()

    asyncio.run(scenario())


def test_missing_aiohttp_replay_switch_stops_traffic_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        calls = 0

        async def me(request: web.Request) -> web.Response:
            nonlocal calls
            calls += 1
            return web.Response(text="{}")

        app = web.Application()
        app.router.add_get("/gateway/api/2.0/Me", me)
        async with serve(app) as origin, RequestScheduler(("a",)) as scheduler:
            transport = AiohttpTransport(
                "a",
                scheduler,
                ConnectionSettings(synergia_origin=origin, api_origin=origin),
                TransportLimits(),
            )
            # Simulates an aiohttp release that renamed the private attribute.
            monkeypatch.setattr(
                aiohttp.ClientSession,
                "ATTRS",
                aiohttp.ClientSession.ATTRS - {"_retry_connection"},
            )
            try:
                with pytest.raises(LibrusError, match="^unsupported_capability$"):
                    await transport.request("identity", RequestBudget())
                assert calls == 0
            finally:
                await transport.aclose()

    asyncio.run(scenario())


def test_native_transport_preserves_account_cookies_and_isolates_sessions() -> None:
    async def scenario() -> None:
        async def submit(request: web.Request) -> web.Response:
            data = await request.post()
            login = str(data["login"])
            response = web.Response(text="{}")
            response.set_cookie("oauth_token", login, path="/")
            response.headers.add("Set-Cookie", f"oauth_token=api-{login}; Path=/OAuth")
            response.set_cookie("DeviceCookie", "synthetic-device", path="/OAuth")
            return response

        async def profile(request: web.Request) -> web.Response:
            assert "DeviceCookie" not in request.cookies
            return web.Response(text=request.cookies["oauth_token"])

        async def authorization(request: web.Request) -> web.Response:
            return web.Response(text=request.cookies["oauth_token"])

        app = web.Application()
        app.router.add_post("/OAuth/Authorization", submit)
        app.router.add_get("/OAuth/Authorization", authorization)
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
            scoped = await asyncio.gather(
                *(
                    item.request("login_authorization", RequestBudget())
                    for item in transports
                )
            )
            assert [item.body for item in scoped] == [b"api-a", b"api-b"]
            assert "synthetic-device" not in repr(results)
            assert transports[0].has_cookie("DeviceCookie", "login_authorization")
            assert not transports[0].has_cookie("DeviceCookie", "identity")
            transports[0].clear_auth()
            assert not transports[0].has_cookie("oauth_token", "identity")
            assert not transports[0].has_cookie("oauth_token", "login_authorization")
            assert transports[0].has_cookie("DeviceCookie", "login_authorization")
            assert transports[1].has_cookie("oauth_token", "identity")
            assert transports[1].has_cookie("oauth_token", "login_authorization")

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
        "/OAuth/Authorization/Unrecognized",
        "/OAuth/Authorization/PerformLogin/extra",
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


@pytest.mark.parametrize("startup_delay_seconds", [0, 0.1])
def test_slow_body_timeout_releases_connector_before_next_request(
    monkeypatch: pytest.MonkeyPatch, startup_delay_seconds: float
) -> None:
    resolve = socket.getaddrinfo

    def delayed_resolve(*args: Any, **kwargs: Any) -> Any:
        time.sleep(startup_delay_seconds)
        return resolve(*args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", delayed_resolve)

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
            await response.write(b"x")
            await release.wait()
            return response

        async def warm(request: web.Request) -> web.Response:
            return web.Response(body=b"ready")

        app = web.Application()
        app.router.add_get("/gateway/api/2.0/Me", handler)
        app.router.add_get("/OAuth/Authorization", warm)
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
                # Initialization/DNS may outlast a tiny deadline. Warm the same
                # connector, then prove timeout happened during an actual body.
                assert (
                    await transport.request("login_authorization", RequestBudget())
                ).body == b"ready"
                budget = RequestBudget(timeout_seconds=1)
                with pytest.raises(LibrusError, match="^timeout$"):
                    await transport.request("identity", budget)
                assert count == 1, "The timeout must occur after the body starts"
                assert budget.response_bytes == 1
                assert scheduler.snapshot().active == 0
                assert (
                    await transport.request(
                        "identity", RequestBudget(timeout_seconds=5)
                    )
                ).body == b"ok"
                assert count == 2 and not release.is_set()
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


CREDENTIALS = LoginSubmission(SecretStr("fixture"), SecretStr("fixture-secret"))


@pytest.mark.parametrize(
    "endpoint,form",
    [
        ("attendance", CREDENTIALS),  # credentials only go to the login submission
        ("grades", CREDENTIALS),
        ("login_submit", {"login": "fixture", "pass": "fixture-secret"}),
        ("timetable", None),  # a view-changing POST always carries its form
        ("agenda", {"rok": 2026}),
        ("identity", {"fixture": "value"}),  # a GET never carries a form body
        ("agenda", {"rok": "2026", "miesiac": "10", "extra": "1"}),  # unknown field
        ("timetable", {"rok": "2026"}),  # another endpoint's field
        ("agenda", {"rok": "2026", "miesiac": "1" * 65}),  # oversized value
        ("grades", {}),  # empty form
        ("recipients", {"typAdresata": "nauczyciel"}),
        ("recipients", recipient_form("nauczyciel") | {"idGrupy": "301"}),
        ("recipients", recipient_form("grupa") | {"idGrupy": "0301"}),
        ("recipients", recipient_form("grupa") | {"czyWirtualneKlasy": "true"}),
        ("recipients", recipient_form("grupa") | {"wyslij": "1"}),
        (
            "recipients",
            {
                "typAdresata": "nauczyciel",
                "poprzednia": "5",
                "tabZaznaczonych": "1",
                "czyWirtualneKlasy": "false",
                "idGrupy": "0",
            },
        ),
        (
            "messages_sent",
            {
                "numer_strony105": "0",
                "porcjowanie_pojemnik105": "105",
                "wyslij": "Fixture",
            },
        ),
        ("messages_sent", {"numer_strony105": "0"}),
        (
            "messages_received",
            {"numer_strony105": "0", "porcjowanie_pojemnik105": "106"},
        ),
        (
            "messages_received",
            {"numer_strony105": "1000", "porcjowanie_pojemnik105": "105"},
        ),
        (
            "messages_received",
            {"numer_strony105": "-1", "porcjowanie_pojemnik105": "105"},
        ),
    ],
)
def test_mismatched_forms_are_rejected_before_dispatch(
    endpoint: str, form: object
) -> None:
    async def scenario() -> None:
        async with RequestScheduler(("a",), limits=SchedulerLimits()) as scheduler:
            transport = AiohttpTransport(
                "a", scheduler, ConnectionSettings(), TransportLimits()
            )
            try:
                with pytest.raises(LibrusError) as failure:
                    await transport.request(endpoint, RequestBudget(), form=form)  # type: ignore[arg-type]
                assert failure.value.kind == ErrorKind.INVALID_INPUT
                assert scheduler.snapshot().requests_dispatched == 0
            finally:
                await transport.aclose()

    asyncio.run(scenario())
