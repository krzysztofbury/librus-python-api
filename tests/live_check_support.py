"""One loopback fixture serving every read the weekly profile makes."""

import asyncio
from datetime import date

from aiohttp import web

from librus_python_api import AccountCredentials, ConnectionSettings
from scripts.live_check.report import Report
from scripts.live_check.runner import Profile, run_profile
from tests.http_support import FIXTURE_SECRET, serve
from tests.test_modern_communication import CommunicationFixture

TODAY = date(2026, 10, 7)


class WeeklyFixture(CommunicationFixture):
    """Adds the gateway lesson and subject routes used by subject frequency."""

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get("/gateway/api/2.0/Lessons", self.gateway_lessons)
        app.router.add_get("/gateway/api/2.0/Subjects", self.gateway_subjects)
        app.router.add_get("/gateway/api/2.0/Lessons/{id}", self.gateway_lesson)
        app.router.add_get("/gateway/api/2.0/Subjects/{id}", self.gateway_subject)
        return app

    async def gateway_lessons(self, request: web.Request) -> web.Response:
        self.record(request)
        return web.json_response(
            {"Lessons": [{"Id": 41, "Teacher": {"Id": 7}, "Subject": {"Id": 51}}]}
        )

    async def gateway_subjects(self, request: web.Request) -> web.Response:
        self.record(request)
        return web.json_response(
            {"Subjects": [{"Id": 51, "Name": "Fixture subject", "No": 1, "Short": "F"}]}
        )

    async def gateway_lesson(self, request: web.Request) -> web.Response:
        self.record(request)
        return web.json_response(
            {"Lesson": {"Id": int(request.match_info["id"]), "Subject": {"Id": 51}}}
        )

    async def gateway_subject(self, request: web.Request) -> web.Response:
        self.record(request)
        return web.json_response(
            {
                "Subject": {
                    "Id": int(request.match_info["id"]),
                    "Name": "Fixture subject",
                }
            }
        )


def run_fixture(
    profile: Profile,
    fixture: CommunicationFixture,
    logins: tuple[str, ...] = ("student", "parent"),
    identities: dict[str, str] | None = None,
) -> Report:
    async def scenario() -> Report:
        fixture.aliases = logins
        async with (
            serve(fixture.app()) as native,
            serve(fixture.modern_app()) as modern,
        ):
            fixture.origin, fixture.modern_origin = native, modern
            return await run_profile(
                profile,
                {
                    f"slot-{index}": AccountCredentials(
                        login=login, password=FIXTURE_SECRET
                    )
                    for index, login in enumerate(logins)
                },
                today=TODAY,
                identities=identities,
                connection=ConnectionSettings(
                    synergia_origin=native,
                    api_origin=native,
                    messages_origin=modern,
                    download_origin=fixture.download_origin,
                ),
            )

    return asyncio.run(scenario())
