"""Owning bounded credentialed qualification scope, tested only on loopback."""

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import web

from librus_python_api import AccountCredentials, ConnectionSettings, LibrusService
from librus_python_api.config import ENDPOINTS, message_page_form
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    UnsupportedCapabilityError,
)
from librus_python_api.models import MessageFolder
from scripts.capture_attachment_streams import StreamAudit, capture
from tests.http_support import FIXTURE_SECRET, SchoolFixture, serve
from tests.message_content_support import attachment_html, content_html
from tests.messages_support import message_row, messages_html


def test_capture_scope_exact_selection_one_login_and_one_bounded_download() -> None:
    audit = StreamAudit("smoke")
    url = "https://synergia.librus.pl/wiadomosci/1/5/101"
    with pytest.raises(InvalidInputError):
        audit.admit(ENDPOINTS["message_content_received"], None, url)
    audit.message_id = "101"
    audit.file_id = "301"
    audit.admit(ENDPOINTS["message_content_received"], None, url)
    with pytest.raises(InvalidInputError):
        audit.admit(ENDPOINTS["message_content_received"], None, url)
    with pytest.raises(InvalidInputError):
        audit.admit(
            ENDPOINTS["attachment_resolve"],
            None,
            "https://synergia.librus.pl/wiadomosci/pobierz_zalacznik/101/302",
        )
    audit.admit(
        ENDPOINTS["attachment_resolve"],
        None,
        "https://synergia.librus.pl/wiadomosci/pobierz_zalacznik/101/301",
    )
    with pytest.raises(UnsupportedCapabilityError):
        audit.admit_download(10 * 1024 * 1024 + 1)
    audit.admit_download(10 * 1024 * 1024)
    with pytest.raises(UnsupportedCapabilityError):
        audit.admit_download(1)
    audit.admit(ENDPOINTS["login_submit"], None, url)
    with pytest.raises(LimitError):
        audit.admit(ENDPOINTS["login_submit"], None, url)
    with pytest.raises(UnsupportedCapabilityError):
        audit.admit(ENDPOINTS["message_content_sent"], None, url)
    with pytest.raises(InvalidInputError):
        audit.admit(
            ENDPOINTS["messages_received"],
            message_page_form(MessageFolder.RECEIVED, 1),
            url,
        )
    capped = StreamAudit("discovery")
    for _ in range(24):
        capped.admit(ENDPOINTS["login_portal"], None, url)
    with pytest.raises(LimitError):
        capped.admit(ENDPOINTS["login_portal"], None, url)
    blocked = StreamAudit("discovery")
    blocked.message_id, blocked.file_id = "101", "301"
    with pytest.raises(UnsupportedCapabilityError):
        blocked.admit(
            ENDPOINTS["attachment_resolve"],
            None,
            "https://synergia.librus.pl/wiadomosci/pobierz_zalacznik/101/301",
        )
    blocked.failed = True
    with pytest.raises(LimitError):
        blocked.admit(ENDPOINTS["login_portal"], None, url)


@pytest.mark.parametrize("mode", ["discovery", "smoke"])
@pytest.mark.parametrize("eligible", [False, True])
def test_discovery_and_smoke_use_original_wire_without_retaining_file_bytes(
    mode: str, eligible: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        app = fixture.app()

        async def lists(request: web.Request) -> web.Response:
            fixture.record(request)
            assert dict(await request.post()) == {
                "numer_strony105": "0",
                "porcjowanie_pojemnik105": "105",
            }
            folder = (
                MessageFolder.RECEIVED
                if request.path.endswith("5")
                else MessageFolder.SENT
            )
            items = (
                message_row(attachment=True, unread=not eligible)
                if folder is MessageFolder.RECEIVED
                else ""
            )
            return web.Response(
                text=messages_html(folder, rows=items), content_type="text/html"
            )

        async def content(request: web.Request) -> web.Response:
            fixture.record(request)
            return web.Response(
                text=content_html(attachments=attachment_html(), read_receipt=True),
                content_type="text/html",
            )

        async def resolve(request: web.Request) -> web.Response:
            fixture.record(request)
            return web.Response(
                status=302,
                headers={"Location": fixture.origin + "/GetFile/Fixture-Key"},
            )

        async def download(request: web.Request) -> web.Response:
            assert not request.cookies
            return web.Response(body=b"unique-fixture-file-bytes-not-to-save")

        app.router.add_post("/wiadomosci/1/5", lists)
        app.router.add_post("/wiadomosci/1/6", lists)
        app.router.add_get("/wiadomosci/1/5/101", content)
        app.router.add_get("/wiadomosci/pobierz_zalacznik/101/301", resolve)
        app.router.add_get("/GetFile/Fixture-Key/get", download)
        async with serve(app) as origin:
            fixture.origin = origin
            monkeypatch.setattr(
                "scripts.capture_attachment_streams.LibrusService",
                lambda accounts, **kw: LibrusService(
                    accounts,
                    connection=ConnectionSettings(
                        synergia_origin=origin,
                        api_origin=origin,
                        download_origin=origin,
                    ),
                    **kw,
                ),
            )
            report = await capture(
                AccountCredentials(login="student", password=FIXTURE_SECRET),
                tmp_path,
                mode=mode,
                selection=("101", "301") if mode == "smoke" else None,
            )
            assert report["status"] == (
                "completed" if eligible else "no_eligible_attachment"
            )
            assert report["requests"] == 7 + (1 if eligible else 0) + (
                2 if eligible and mode == "smoke" else 0
            )
            assert report["logins"] == 1
            if eligible and mode == "smoke":
                assert report["download"] == {
                    "bytes": 37,
                    "complete": True,
                    "declared_length_present": True,
                    "declared_length_matches": True,
                }

    asyncio.run(scenario())
    for path in tmp_path.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
        assert b"unique-fixture-file-bytes-not-to-save" not in path.read_bytes()
    captured = json.loads((tmp_path / "index.json").read_text())["captured"]
    assert len(captured) == (3 if eligible else 2)
