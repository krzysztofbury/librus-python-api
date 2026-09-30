"""Evaluate aiohttp on synthetic loopback HTTP only, never live Librus.

This is an executable transport-selection experiment, not the supported client.
The fixture paths and login response are not Librus routes or wire schemas.
"""

import asyncio
import json
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass

from aiohttp import ClientSession, ClientTimeout, CookieJar, TCPConnector, web
from yarl import URL

from librus_python_api.config import TransportLimits
from librus_python_api.errors import ErrorKind, LibrusError

ACCOUNTS = ("student_a", "parent_a", "student_b", "parent_b")


@dataclass(frozen=True, slots=True)
class SpikeReport:
    isolated_accounts: int
    scoped_duplicate_cookies: bool
    oversized_body_rejected: bool
    canceled_connection_released: bool
    deadline_enforced: bool


async def read_bounded(
    session: ClientSession, url: str, limits: TransportLimits
) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async with session.get(url, allow_redirects=False) as response:
        if response.status != 200:
            raise LibrusError(ErrorKind.ACCESS_DENIED)
        async for chunk in response.content.iter_chunked(
            min(16 * 1024, limits.response_max_bytes + 1)
        ):
            size += len(chunk)
            if size > limits.response_max_bytes:
                raise LibrusError(ErrorKind.LIMIT)
            chunks.append(chunk)
    return b"".join(chunks)


def fixture_application(
    slow_started: asyncio.Event, slow_release: asyncio.Event
) -> web.Application:
    async def login(request: web.Request) -> web.Response:
        account = request.match_info["account"]
        if account not in ACCOUNTS:
            raise web.HTTPForbidden()
        response = web.Response(text="synthetic login")
        response.set_cookie("access", account, path="/account", httponly=True)
        return response

    async def identity(request: web.Request) -> web.Response:
        account = request.cookies.get("access")
        if account not in ACCOUNTS:
            raise web.HTTPForbidden()
        return web.json_response({"account": account})

    async def scope(request: web.Request) -> web.Response:
        return web.json_response({"access": request.cookies.get("access")})

    async def oversized(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(b"x" * 65)
        await response.write_eof()
        return response

    async def slow(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        await response.prepare(request)
        slow_started.set()
        await slow_release.wait()
        return response

    app = web.Application()
    app.router.add_get("/fixture/login/{account}", login)
    app.router.add_get("/account/identity", identity)
    app.router.add_get("/scope", scope)
    app.router.add_get("/oversized", oversized)
    app.router.add_get("/slow", slow)
    return app


async def check_body_limits_and_cancellation(
    session: ClientSession,
    base_url: str,
    slow_started: asyncio.Event,
    slow_release: asyncio.Event,
) -> None:
    limits = TransportLimits(response_max_bytes=64)
    try:
        await read_bounded(session, f"{base_url}/oversized", limits)
    except LibrusError as error:
        assert error.kind == ErrorKind.LIMIT
    else:
        raise AssertionError("Oversized chunked response was accepted")

    task = asyncio.create_task(read_bounded(session, f"{base_url}/slow", limits))
    try:
        async with asyncio.timeout(2):
            await slow_started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Canceled read returned normally")
        # Connector limit=1: this cannot complete if cancellation leaked its slot.
        async with asyncio.timeout(2):
            await read_bounded(session, f"{base_url}/account/identity", limits)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        slow_release.set()


async def run_spike() -> SpikeReport:
    async with asyncio.timeout(15):
        return await _run_spike()


async def _run_spike() -> SpikeReport:
    slow_started, slow_release = asyncio.Event(), asyncio.Event()
    runner = web.AppRunner(fixture_application(slow_started, slow_release))
    async with AsyncExitStack() as stack:
        await runner.setup()
        stack.push_async_callback(runner.cleanup)
        stack.callback(slow_release.set)
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        # localhost is accepted by the normal strict cookie jar, unlike IP hosts.
        base_url = f"http://localhost:{port}"
        limits = TransportLimits(
            response_max_bytes=64,
            request_timeout_seconds=2,
            connect_timeout_seconds=1,
        )
        sessions = []
        for _ in ACCOUNTS:
            session = await stack.enter_async_context(
                ClientSession(
                    connector=TCPConnector(limit=1),
                    cookie_jar=CookieJar(),
                    timeout=ClientTimeout(
                        total=limits.request_timeout_seconds,
                        sock_connect=limits.connect_timeout_seconds,
                    ),
                    trust_env=False,
                )
            )
            sessions.append(session)
        for account, session in zip(ACCOUNTS, sessions, strict=True):
            await read_bounded(session, f"{base_url}/fixture/login/{account}", limits)
        identities = await asyncio.gather(
            *(read_bounded(s, f"{base_url}/account/identity", limits) for s in sessions)
        )
        assert [json.loads(body)["account"] for body in identities] == list(ACCOUNTS)
        session = sessions[0]
        session.cookie_jar.update_cookies(
            {"access": "root_scope"}, response_url=URL(f"{base_url}/")
        )
        # Add a same-name host/path-scoped cookie independently of the root one.
        await read_bounded(session, f"{base_url}/fixture/login/student_a", limits)
        cookies = list(session.cookie_jar)
        assert len(cookies) == 2
        assert {cookie["path"] for cookie in cookies} == {"/", "/account"}
        assert json.loads(await read_bounded(session, f"{base_url}/scope", limits)) == {
            "access": "root_scope"
        }
        identity = await read_bounded(session, f"{base_url}/account/identity", limits)
        assert json.loads(identity) == {"account": "student_a"}
        await check_body_limits_and_cancellation(
            sessions[1], base_url, slow_started, slow_release
        )
        slow_started.clear()
        slow_release.clear()
        try:
            async with asyncio.timeout(0.1):
                await read_bounded(sessions[1], f"{base_url}/slow", limits)
        except TimeoutError:
            pass
        else:
            raise AssertionError("Slow response escaped the operation deadline")
        slow_release.set()
    assert all(session.closed for session in sessions)
    return SpikeReport(len(ACCOUNTS), True, True, True, True)


if __name__ == "__main__":
    print(json.dumps(asdict(asyncio.run(run_spike())), sort_keys=True))
