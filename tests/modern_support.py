"""Original two-origin modern messaging fixtures with invented IDs and people."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiohttp import web

from librus_python_api import AccountCredentials, ConnectionSettings, LibrusService
from librus_python_api.config import SchedulerLimits
from tests.http_support import FIXTURE_SECRET, serve
from tests.reads_support import ReadsFixture


def directory(records: int = 2) -> dict[str, Any]:
    return {
        "classes": [
            {
                "label": "Fixture class",
                "receivers": [
                    [
                        {
                            "accountId": str(701 + i),
                            "userId": str(901 + i),
                            "name": f"Fixture recipient {i}",
                        }
                        for i in range(records)
                    ]
                ],
            }
        ]
    }


class ModernFixture(ReadsFixture):
    def __init__(self) -> None:
        super().__init__()
        self.aliases: tuple[str, ...] = ("student",)
        self.modern_origin = ""
        self.modern_calls: list[tuple[str, str, dict[str, str]]] = []
        self.sends: list[tuple[str, bytes, str]] = []
        self.started = asyncio.Event()
        self.block_stage: str | None = None
        self.release = asyncio.Event()
        self.responses: dict[str, tuple[int, bytes, str, dict[str, str]]] = {}
        self.launch_location: str | None = None
        self.handoff_location = "/nowy"
        self.identity_override: dict[str, Any] = {}
        self.disconnect = False
        self.partial = False
        self.types_data = {
            "data": {
                "defaultGroup": "parentsCouncil",
                "list": [
                    {"id": "parentsCouncil", "name": "Fixture council"},
                    {"id": "teachers", "name": "Fixture teachers"},
                ],
            }
        }
        self.directory_data = directory()

    def account_id(self, login: str) -> str:
        return str(301 + self.aliases.index(login))

    async def identity(self, request: web.Request) -> web.Response:
        response = await super().identity(request)
        assert response.text is not None
        data = json.loads(response.text)
        login = request.cookies["oauth_token"]
        data["Me"]["Account"]["Id"] = self.account_id(login)
        return web.json_response(data)

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get("/wiadomosci3", self.launch)
        return app

    async def held_stage(self, stage: str) -> None:
        if self.block_stage == stage:
            self.started.set()
            await self.release.wait()

    async def launch(self, request: web.Request) -> web.Response:
        login = self.record(request)
        assert "modern_session" not in request.cookies
        await self.held_stage("launch")
        encoded = base64.b64encode(login.encode()).decode().rstrip("=")
        location = self.launch_location or (
            f"{self.modern_origin}/pobierz28/MultiDomainLogon/token/{'Z' * 32}"
            f"/login/{encoded}/target/L25vd3k/from/c3luZXJnaWE"
        )
        return web.Response(status=302, headers={"Location": location})

    def modern_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get(
            "/pobierz28/MultiDomainLogon/token/{token}/login/{login}/target/{target}/from/{source}",
            self.handoff,
        )
        app.router.add_get("/api/me", self.modern_identity)
        app.router.add_get("/api/receivers/types", self.types)
        app.router.add_get(
            "/api/receivers/groups/students-and-attendants", self.recipients
        )
        app.router.add_post("/api/messages", self.send)
        return app

    def record_modern(self, request: web.Request, stage: str) -> str:
        login = request.cookies.get("modern_session", "")
        assert "oauth_token" not in request.cookies
        assert "DeviceCookie" not in request.cookies
        self.modern_calls.append((stage, login, dict(request.query)))
        return login

    def response(self, stage: str, default: dict[str, Any]) -> web.Response:
        if stage in self.responses:
            status, body, kind, headers = self.responses[stage]
            return web.Response(
                status=status, body=body, content_type=kind, headers=headers
            )
        return web.json_response(default)

    async def handoff(self, request: web.Request) -> web.Response:
        self.record_modern(request, "handoff")
        await self.held_stage("handoff")
        login = base64.b64decode(
            request.match_info["login"] + "=" * (-len(request.match_info["login"]) % 4)
        ).decode()
        response = web.Response(status=302, headers={"Location": self.handoff_location})
        response.set_cookie("modern_session", login, path="/")
        return response

    async def modern_identity(self, request: web.Request) -> web.Response:
        login = self.record_modern(request, "identity")
        await self.held_stage("identity")
        return self.response(
            "identity",
            {
                "accountId": self.account_id(login),
                "groupId": "5",
                "firstName": "Synthetic",
                "lastName": "Owner",
                "originSystem": "synergia",
                **self.identity_override,
            },
        )

    async def types(self, request: web.Request) -> web.Response:
        self.record_modern(request, "types")
        assert dict(request.query) == {"includeClass": "true"}
        await self.held_stage("types")
        return self.response("types", self.types_data)

    async def recipients(self, request: web.Request) -> web.Response:
        self.record_modern(request, "directory")
        assert dict(request.query) == {"receiverType": "parentsCouncil"}
        await self.held_stage("directory")
        return self.response("directory", self.directory_data)

    async def send(self, request: web.Request) -> web.StreamResponse:
        login = self.record_modern(request, "send")
        self.sends.append(
            (login, await request.read(), request.headers["Content-Type"])
        )
        self.started.set()
        await self.held_stage("send")
        if self.disconnect:
            assert request.transport is not None
            request.transport.close()
        if self.partial:
            response = web.StreamResponse(
                headers={"Content-Type": "application/json", "Content-Length": "100"}
            )
            await response.prepare(request)
            await response.write(b'{"data":')
            assert request.transport is not None
            request.transport.close()
            return response
        return self.response("send", {"data": {"fixtureUnknownReceipt": True}})

    @asynccontextmanager
    async def running(
        self, aliases: tuple[str, ...] = ("student",), **kwargs: Any
    ) -> AsyncIterator[LibrusService]:
        self.aliases = aliases
        async with serve(self.app()) as native, serve(self.modern_app()) as modern:
            self.origin, self.modern_origin = native, modern
            settings = ConnectionSettings(
                synergia_origin=native, api_origin=native, messages_origin=modern
            )
            limits = kwargs.pop(
                "scheduler_limits", SchedulerLimits(requests_per_second=1000, burst=32)
            )
            async with LibrusService(
                {
                    alias: AccountCredentials(login=alias, password=FIXTURE_SECRET)
                    for alias in aliases
                },
                connection=settings,
                scheduler_limits=limits,
                **kwargs,
            ) as service:
                yield service
