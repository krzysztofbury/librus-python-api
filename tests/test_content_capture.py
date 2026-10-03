"""Owning live-authorization caps and selection logic, exercised offline only."""

import asyncio
from pathlib import Path

import pytest

from librus_python_api import AccountCredentials, LibrusService
from librus_python_api.config import ENDPOINTS, ConnectionSettings
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    UnsupportedCapabilityError,
)
from scripts.capture_message_content import ContentAudit, capture
from tests.http_support import FIXTURE_SECRET, serve
from tests.messages_support import message_row, messages_html
from tests.reads_support import ReadsFixture


def test_audit_only_allows_selected_received_message_and_one_login() -> None:
    audit = ContentAudit()
    content = ENDPOINTS["message_content_received"]
    url = "https://synergia.librus.pl/wiadomosci/1/5/101"
    with pytest.raises(InvalidInputError):
        audit.admit(content, None, url)
    audit.selected = "101"
    with pytest.raises(InvalidInputError):
        audit.admit(content, None, url.replace("101", "102"))
    for excluded in ("message_content_sent", "recipients", "announcements"):
        with pytest.raises(UnsupportedCapabilityError):
            audit.admit(ENDPOINTS[excluded], None, url)
    audit.admit(content, None, url)
    audit.admit(content, None, url)
    with pytest.raises(InvalidInputError):
        audit.admit(content, None, url)
    audit.admit(ENDPOINTS["login_submit"], None, url)
    with pytest.raises(LimitError):
        audit.admit(ENDPOINTS["login_submit"], None, url)
    audit.failed = True
    with pytest.raises(LimitError):
        audit.admit(ENDPOINTS["login_portal"], None, url)
    capped = ContentAudit()
    for _ in range(24):
        capped.admit(ENDPOINTS["login_portal"], None, url)
    with pytest.raises(LimitError):
        capped.admit(ENDPOINTS["login_portal"], None, url)


@pytest.mark.parametrize("mode,opens", [("discovery", 1), ("smoke", 2)])
@pytest.mark.parametrize("already_read", [False, True])
def test_capture_opens_only_already_read_received_content(
    mode: str,
    opens: int,
    already_read: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        fixture.bodies["messages_received"] = (
            messages_html(rows=message_row(unread=not already_read)).encode(),
            "text/html",
        )
        async with serve(fixture.app()) as origin:
            monkeypatch.setattr(
                "scripts.capture_message_content.LibrusService",
                lambda accounts, **kw: LibrusService(
                    accounts,
                    connection=ConnectionSettings(
                        synergia_origin=origin, api_origin=origin
                    ),
                    **kw,
                ),
            )
            report = await capture(
                AccountCredentials(login="student", password=FIXTURE_SECRET),
                tmp_path,
                mode=mode,
            )
            assert report["status"] == ("completed" if already_read else "stopped")
            assert report["requests"] == 7 + (opens if already_read else 0)
            assert fixture.count("message_content_received") == (
                opens if already_read else 0
            )
            assert report["logins"] == 1
            assert fixture.count("message_content_sent") == 0

    asyncio.run(scenario())
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.iterdir())
