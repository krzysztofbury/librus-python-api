"""Original synthetic loopback fixtures; not captured Librus responses."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiohttp import web

from librus_python_api.config import (
    AccountCredentials,
    ConnectionSettings,
    OperationLimits,
    SchedulerLimits,
    TransportLimits,
)
from librus_python_api.diagnostics import DiagnosticSink
from librus_python_api.service import LibrusService

# Only sent to the loopback server, which does not authenticate this value.
FIXTURE_SECRET = "fixture-only-never-valid"


@asynccontextmanager
async def serve(app: web.Application) -> AsyncIterator[str]:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        yield f"http://localhost:{runner.addresses[0][1]}"
    finally:
        await runner.cleanup()


class SchoolFixture:
    """Minimal original wire contract, not an emulation claim for live Librus."""

    def __init__(self) -> None:
        self.origin = ""
        self.calls: list[tuple[str, str]] = []
        self.dispatch_times: list[float] = []
        self.logins: dict[str, int] = {}
        self.profile_status: dict[str, int] = {}
        self.expire_profile: dict[str, int] = {}
        self.challenge = False
        self.malformed_identity = False
        self.identity_mode = "json"
        self.cookie_missing = False
        self.redirect_loop = False
        self.connections: set[int] = set()
        self.wait_profile: asyncio.Event | None = None
        self.profile_started = asyncio.Event()

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/loguj/portalRodzina", self.portal)
        app.router.add_get("/OAuth/Authorization", self.authorization)
        app.router.add_post("/OAuth/Authorization", self.submit)
        app.router.add_get("/loguj", self.callback)
        app.router.add_get("/gateway/api/2.0/Me", self.identity)
        app.router.add_get("/informacja", self.profile)
        return app

    def record(self, request: web.Request) -> str:
        login = request.cookies.get("oauth_token", "")
        self.calls.append((request.path, login))
        self.dispatch_times.append(time.monotonic())
        self.connections.add(id(request.transport))
        return login

    async def portal(self, request: web.Request) -> web.Response:
        self.record(request)
        return web.Response(
            status=302, headers={"Location": "/OAuth/Authorization?client_id=46"}
        )

    async def authorization(self, request: web.Request) -> web.Response:
        self.record(request)
        assert request.query["client_id"] == "46"
        response = web.Response(
            text="<html><form></form></html>", content_type="text/html"
        )
        response.set_cookie("DeviceCookie", "fixture-device", path="/OAuth")
        return response

    async def submit(self, request: web.Request) -> web.Response:
        self.record(request)
        assert request.cookies["DeviceCookie"] == "fixture-device"
        assert request.query["client_id"] == "46"
        assert request.headers["X-Requested-With"] == "XMLHttpRequest"
        form = await request.post()
        assert set(form) == {"action", "login", "pass"}
        assert form["action"] == "login"
        login = str(form["login"])
        self.logins[login] = self.logins.get(login, 0) + 1
        if login == "rejected":
            return web.json_response({"status": "error"})
        if self.challenge:
            return web.json_response({"status": "ok", "twoFactorRequired": True})
        response = web.json_response({"status": "ok", "goTo": self.origin + "/loguj"})
        response.set_cookie("pending", login, path="/loguj")
        return response

    async def callback(self, request: web.Request) -> web.Response:
        self.record(request)
        if self.redirect_loop:
            return web.Response(status=302, headers={"Location": "/loguj"})
        response = web.Response(text="<html>landing</html>", content_type="text/html")
        if not self.cookie_missing:
            response.set_cookie("oauth_token", request.cookies["pending"], path="/")
        return response

    async def identity(self, request: web.Request) -> web.Response:
        login = self.record(request)
        if not login:
            return web.Response(status=401)
        if self.identity_mode == "html":
            return web.Response(
                text="<html>unexpected page</html>", content_type="text/html"
            )
        if self.identity_mode in ("login_redirect", "foreign_redirect"):
            location = (
                "/loguj"
                if self.identity_mode == "login_redirect"
                else "https://example.invalid/steal"
            )
            self.identity_mode = "json"
            return web.Response(status=302, headers={"Location": location})
        if self.malformed_identity:
            return web.json_response({"Me": {"Account": {"Id": login}}})
        payload = {
            "Me": {
                "Account": {
                    "Id": login,
                    "FirstName": "Synthetic",
                    "LastName": "Owner",
                },
                "User": {
                    "Id": "student-shared",
                    "FirstName": "Fixture",
                    "LastName": "Student",
                },
            }
        }
        if self.identity_mode == "account_reference":
            payload["Me"]["Account"]["UserId"] = payload["Me"]["User"].pop("Id")
        return web.json_response(payload)

    async def profile(self, request: web.Request) -> web.Response:
        login = self.record(request)
        self.profile_started.set()
        if self.wait_profile is not None:
            await self.wait_profile.wait()
        if self.expire_profile.get(login, 0):
            self.expire_profile[login] -= 1
            return web.Response(status=401)
        if login in self.profile_status:
            return web.Response(status=self.profile_status[login])
        return web.Response(
            text=profile_html(school=f"Fixture School {login}"),
            content_type="text/html",
        )

    def service(
        self,
        aliases: tuple[str, ...] = ("student",),
        *,
        operation_limits: OperationLimits | None = None,
        transport_limits: TransportLimits | None = None,
        diagnostic_sink: DiagnosticSink | None = None,
        scheduler_limits: SchedulerLimits | None = None,
    ) -> LibrusService:
        return LibrusService(
            {
                alias: AccountCredentials(login=alias, password=FIXTURE_SECRET)
                for alias in aliases
            },
            connection=ConnectionSettings(
                synergia_origin=self.origin, api_origin=self.origin
            ),
            scheduler_limits=scheduler_limits
            or SchedulerLimits(requests_per_second=1000, burst=16),
            operation_limits=operation_limits,
            transport_limits=transport_limits,
            diagnostic_sink=diagnostic_sink,
        )


def profile_html(
    school: str = "Synthetic School", lucky: str = '<span id="luckyNumber">7</span>'
) -> str:
    return f"""<!doctype html><html><body>
    <table><tr><th>Uczeń:</th><td>Fixture Student</td></tr>
    <tr><th>Klasa</th><td>1 TEST</td></tr>
    <tr><th>Numer w dzienniku</th><td>12</td></tr>
    <tr><th>Wychowawca</th><td>Fixture Tutor</td></tr>
    <tr><th>Szkoła</th><td>{school}</td></tr></table>{lucky}</body></html>"""
