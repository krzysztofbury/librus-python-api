"""Owning safety checks for explicitly bounded list discovery, with no live I/O."""

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import web

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    SchedulerLimits,
)
from librus_python_api.config import ENDPOINTS, message_page_form
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    UnsupportedCapabilityError,
)
from librus_python_api.models import MessageFolder
from scripts.capture_messages import CaptureAudit, capture
from tests.http_support import FIXTURE_SECRET, SchoolFixture, serve
from tests.messages_support import message_row, messages_html


def test_capture_scope_excludes_content_writes_unknown_pages_and_second_login() -> None:
    audit = CaptureAudit()
    with pytest.raises(UnsupportedCapabilityError):
        audit.admit(ENDPOINTS["announcements"], None)
    with pytest.raises(InvalidInputError):
        audit.admit(ENDPOINTS["messages_sent"], {"wyslij": "Fixture"})
    with pytest.raises(InvalidInputError):
        audit.admit(
            ENDPOINTS["messages_received"], message_page_form(MessageFolder.RECEIVED, 3)
        )
    audit.admit(ENDPOINTS["login_submit"], None)
    with pytest.raises(LimitError):
        audit.admit(ENDPOINTS["login_submit"], None)
    assert audit.requests == audit.logins == 1


def test_capture_request_and_list_ceiling_close_after_failure() -> None:
    audit = CaptureAudit()
    for _ in range(10):
        audit.admit(
            ENDPOINTS["messages_received"], message_page_form(MessageFolder.RECEIVED, 0)
        )
    with pytest.raises(InvalidInputError):
        audit.admit(
            ENDPOINTS["messages_received"], message_page_form(MessageFolder.RECEIVED, 0)
        )
    audit.failed = True
    with pytest.raises(LimitError):
        audit.admit(ENDPOINTS["login_portal"], None)
    other = CaptureAudit()
    for _ in range(24):
        other.admit(ENDPOINTS["login_portal"], None)
    with pytest.raises(LimitError):
        other.admit(ENDPOINTS["login_portal"], None)


@pytest.mark.parametrize("mode,requests,lists", [("discovery", 7, 2), ("smoke", 10, 5)])
def test_real_loopback_capture_uses_only_fixed_pagination_forms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    requests: int,
    lists: int,
) -> None:
    fixture = SchoolFixture()
    forms: list[dict[str, str]] = []

    async def list_page(request: web.Request) -> web.Response:
        fixture.record(request)
        fields = {key: str(value) for key, value in (await request.post()).items()}
        forms.append(fields)
        assert not request.query
        folder = (
            MessageFolder.RECEIVED if request.path.endswith("5") else MessageFolder.SENT
        )
        body = messages_html(
            folder,
            rows=message_row("101") + message_row("102")
            if folder is MessageFolder.RECEIVED
            else "",
            footer=True,
            legacy_notice=True,
        )
        return web.Response(text=body, content_type="text/html")

    async def scenario() -> None:
        app = fixture.app()
        app.router.add_post("/wiadomosci/1/5", list_page)
        app.router.add_post("/wiadomosci/1/6", list_page)
        async with serve(app) as origin:
            fixture.origin = origin
            monkeypatch.setattr(
                "scripts.capture_messages.LibrusService",
                lambda accounts, **kw: LibrusService(
                    accounts,
                    connection=ConnectionSettings(
                        synergia_origin=origin, api_origin=origin
                    ),
                    scheduler_limits=SchedulerLimits(
                        requests_per_second=1000, burst=16
                    ),
                    **kw,
                ),
            )
            report = await capture(
                AccountCredentials(login="student", password=FIXTURE_SECRET),
                tmp_path,
                mode=mode,
            )
            assert report["status"] == "completed" and report["logins"] == 1
            assert report["requests"] == requests

    asyncio.run(scenario())
    assert forms == [{"numer_strony105": "0", "porcjowanie_pojemnik105": "105"}] * lists
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["captured"]) == lists
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.iterdir())
