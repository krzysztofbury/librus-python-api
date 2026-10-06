"""Count-only live harness authorization, exclusively exercised on loopback."""

import asyncio
from pathlib import Path

import pytest
from aiohttp import web

from librus_python_api import AccountCredentials, ConnectionSettings
from librus_python_api.config import ENDPOINTS
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    UnsupportedCapabilityError,
)
from scripts.capture_notification_counts import CountScope, capture
from tests.http_support import FIXTURE_SECRET, serve
from tests.notifications_support import NotificationsFixture, counts_html


@pytest.mark.parametrize("student_landing", [False, True])
def test_count_capture_one_login_scope_and_warm_cache_never_consume_events(
    tmp_path: Path,
    student_landing: bool,
) -> None:
    class LandingFixture(NotificationsFixture):
        def app(self) -> web.Application:
            app = super().app()
            app.router.add_get("/uczen/index", self.landing)
            return app

        async def landing(self, request: web.Request) -> web.Response:
            self.record(request)
            return web.Response(text=counts_html(), content_type="text/html")

        async def callback(self, request: web.Request) -> web.Response:
            response = await super().callback(request)
            if student_landing:
                response.set_status(302)
                response.headers["Location"] = "/uczen/index"
            return response

    async def scenario() -> None:
        fixture = LandingFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            report = await capture(
                AccountCredentials(login="student", password=FIXTURE_SECRET),
                tmp_path,
                ConnectionSettings(synergia_origin=origin, api_origin=origin),
            )
        # A student landing in the login chain is followed, never read for counts.
        assert report["status"] == "completed"
        assert report["categories"] == 6 and report["warm_cache_requests"] == 0
        assert report["logins"] == 1
        assert report["requests"] == (7 if student_landing else 6)
        operations = report["operations"]
        assert isinstance(operations, dict) and operations["student_information"] == 1
        assert sum(path == "/informacja" for path, _ in fixture.calls) == 1
        assert report["read_once_requests"] == 0 and fixture.calls_by_account == []
        assert (tmp_path / "notification-counts.html").stat().st_mode & 0o777 == 0o600

    asyncio.run(scenario())


def test_capture_admission_never_widens_to_read_once_or_another_login() -> None:
    scope = CountScope()
    scope.admit(ENDPOINTS["student_information"], None)
    with pytest.raises(InvalidInputError):
        scope.admit(ENDPOINTS["student_information"], None)
    for name in (
        "consume_schedule_events",
        "message_content_received",
        "messages_received",
        "attachment_resolve",
    ):
        with pytest.raises(UnsupportedCapabilityError):
            scope.admit(ENDPOINTS[name], None)
    scope.admit(ENDPOINTS["login_submit"], None)
    with pytest.raises(LimitError):
        scope.admit(ENDPOINTS["login_submit"], None)
    cap = CountScope()
    for _ in range(24):
        cap.admit(ENDPOINTS["login_portal"], None)
    with pytest.raises(LimitError):
        cap.admit(ENDPOINTS["login_portal"], None)
    scope.failed = True
    with pytest.raises(LimitError):
        scope.admit(ENDPOINTS["identity"], None)
