"""Recipient discovery is separately allowlisted, one-login and type-bound."""

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
from librus_python_api.config import ENDPOINTS, recipient_form
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    UnsupportedCapabilityError,
)
from scripts.capture_recipients import RecipientCaptureAudit, capture
from tests.http_support import FIXTURE_SECRET, SchoolFixture, serve
from tests.recipients_support import groups_html, recipient_html


def test_recipient_scope_requires_discovered_group_and_excludes_message_routes() -> (
    None
):
    audit = RecipientCaptureAudit()
    with pytest.raises(InvalidInputError):
        audit.admit(ENDPOINTS["recipients"], recipient_form("nauczyciel"))
    with pytest.raises(UnsupportedCapabilityError):
        audit.admit(ENDPOINTS["messages_sent"], None)
    audit.groups = ("wychowawca", "nauczyciel", "sekretariat")
    with pytest.raises(InvalidInputError):
        audit.admit(ENDPOINTS["recipients"], recipient_form("admin"))
    for _ in range(6):
        audit.admit(ENDPOINTS["recipients"], recipient_form("nauczyciel"))
    with pytest.raises(InvalidInputError):
        audit.admit(ENDPOINTS["recipients"], recipient_form("nauczyciel"))
    audit.admit(ENDPOINTS["login_submit"], None)
    with pytest.raises(LimitError):
        audit.admit(ENDPOINTS["login_submit"], None)
    assert audit.requests == 7 and audit.logins == 1


@pytest.mark.parametrize("mode,count", [("discovery", 9), ("smoke", 12)])
def test_loopback_discovery_captures_get_and_only_discovered_fixed_post_forms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    count: int,
) -> None:
    fixture = SchoolFixture()
    forms: list[dict[str, str]] = []

    async def groups(request: web.Request) -> web.Response:
        fixture.record(request)
        return web.Response(
            text=groups_html(("wychowawca", "nauczyciel", "sekretariat")),
            content_type="text/html",
        )

    async def recipients(request: web.Request) -> web.Response:
        fixture.record(request)
        forms.append({key: str(value) for key, value in (await request.post()).items()})
        return web.Response(text=recipient_html(), content_type="text/html")

    async def scenario() -> None:
        app = fixture.app()
        app.router.add_get(ENDPOINTS["recipient_groups"].path, groups)
        app.router.add_post(ENDPOINTS["recipients"].path, recipients)
        async with serve(app) as origin:
            fixture.origin = origin
            monkeypatch.setattr(
                "scripts.capture_recipients.LibrusService",
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
            assert (
                report["status"] == "completed"
                and report["requests"] == count
                and report["logins"] == 1
            ), report

    asyncio.run(scenario())
    assert set(f["typAdresata"] for f in forms) == {
        "wychowawca",
        "nauczyciel",
        "sekretariat",
    }
    assert all(
        set(f)
        == {
            "typAdresata",
            "poprzednia",
            "tabZaznaczonych",
            "czyWirtualneKlasy",
            "idGrupy",
        }
        for f in forms
    )
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["captured"]) == count - 5 and index["captured"][0]["form"] is None
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.iterdir())
