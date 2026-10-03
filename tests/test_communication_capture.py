"""0.4.5 capture authorization scope and public wire path, offline only."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import AccountCredentials, ConnectionSettings, MessageFolder
from librus_python_api.config import ENDPOINTS, message_page_form, recipient_form
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    UnsupportedCapabilityError,
)
from scripts.capture_communication_coverage import CoverageScope, capture
from tests.http_support import FIXTURE_SECRET, serve
from tests.reads_support import ReadsFixture
from tests.recipients_support import choice_html


def test_coverage_capture_loopback_discovers_every_group_and_exact_sent_content_once(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            report = await capture(
                AccountCredentials(login="student", password=FIXTURE_SECRET),
                tmp_path,
                ConnectionSettings(synergia_origin=origin, api_origin=origin),
            )
        assert report["status"] == "completed"
        assert report["logins"] == 1 and report["requests"] == 16
        assert report["group_types"] == 3
        assert report["received_pages"] == report["sent_pages"] == 3
        assert (
            report["received_opens"]
            == report["downloads"]
            == report["read_once_requests"]
            == 0
        )
        operations = [r[0] for r in fixture.reads]
        assert operations.count("recipients") == 3
        assert operations.count("message_content_sent") == 1
        assert "message_content_received" not in operations

    asyncio.run(scenario())
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.iterdir())


def test_coverage_scope_requires_observed_page_selector_and_sent_reference() -> None:
    scope = CoverageScope()

    def admit(name: str, form: dict[str, str] | None = None, suffix: str = "") -> None:
        endpoint = ENDPOINTS[name]
        scope.admit(
            endpoint,
            form,
            "https://synergia.librus.pl" + endpoint.path.replace("{id}", suffix),
        )

    for name in (
        "message_content_received",
        "attachment_resolve",
        "consume_schedule_events",
        "student_information",
    ):
        with pytest.raises(UnsupportedCapabilityError):
            admit(name)
    with pytest.raises(InvalidInputError):
        admit("messages_received", message_page_form(MessageFolder.RECEIVED, 1))
    with pytest.raises(InvalidInputError):
        admit("recipients", recipient_form("nauczyciel"))
    scope.recipient_forms.append(recipient_form("nauczyciel"))
    admit("recipients", recipient_form("nauczyciel"))
    with pytest.raises(InvalidInputError):
        admit("recipients", recipient_form("nauczyciel"))
    with pytest.raises(InvalidInputError):
        admit("message_content_sent", suffix="101")
    scope.sent_reference = "101"
    with pytest.raises(InvalidInputError):
        admit("message_content_sent", suffix="102")
    with pytest.raises(InvalidInputError):
        admit("message_content_sent", suffix="101?extra=1")
    admit("message_content_sent", suffix="101")
    with pytest.raises(InvalidInputError):
        admit("message_content_sent", suffix="101")
    admit("login_submit")
    with pytest.raises(LimitError):
        admit("login_submit")
    scope.failed = True
    with pytest.raises(LimitError):
        admit("identity")


def test_coverage_scope_dispatch_ceiling_does_not_reset_for_other_operations() -> None:
    scope = CoverageScope()
    for _ in range(32):
        scope.admit(
            ENDPOINTS["login_portal"],
            None,
            "https://synergia.librus.pl/loguj/portalRodzina",
        )
    with pytest.raises(LimitError):
        scope.admit(
            ENDPOINTS["identity"], None, "https://synergia.librus.pl/gateway/api/2.0/Me"
        )


def test_installed_smoke_public_batch_and_warm_caches_stay_in_single_dispatch_scope(
    tmp_path: Path,
) -> None:
    class SmokeFixture(ReadsFixture):
        def handler(self, operation: str) -> Any:
            normal = super().handler(operation)
            if operation != "recipients":
                return normal

            async def recipient(request: web.Request) -> web.Response:
                form = await request.post()
                if form["typAdresata"] == "grupa":
                    login = self.record(request)
                    self.reads.append((operation, login))
                    return web.Response(text=choice_html(), content_type="text/html")
                response = await normal(request)
                assert isinstance(response, web.Response)
                return response

            return recipient

    async def scenario() -> None:
        fixture = SmokeFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            report = await capture(
                AccountCredentials(login="student", password=FIXTURE_SECRET),
                tmp_path,
                ConnectionSettings(synergia_origin=origin, api_origin=origin),
                mode="smoke",
            )
        assert (
            report["status"] == "completed"
            and report["requests"] == 16
            and report["logins"] == 1
        )
        assert report["warm_cache_requests"] == 0 and report["group_choices"] == 0
        assert report["received_pages_fetched"] == report["sent_pages_fetched"] == 3
        assert (
            report["received_opens"]
            == report["downloads"]
            == report["read_once_requests"]
            == 0
        )
        assert [r[0] for r in fixture.reads].count("message_content_sent") == 1

    asyncio.run(scenario())
