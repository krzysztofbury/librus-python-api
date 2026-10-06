"""The pre-publication live check stays read-only, exercised on loopback only."""

import asyncio
from typing import Any

import pytest

from librus_python_api import AccountCredentials, ConnectionSettings, RequestBudget
from librus_python_api.exceptions import ErrorKind, LibrusError
from scripts.live_release_check import ReleaseCheckTransport, check
from tests.http_support import FIXTURE_SECRET, serve
from tests.test_modern_communication import CommunicationFixture


def run_check(fixture: CommunicationFixture) -> dict[str, Any]:
    aliases = ("student", "parent")

    async def scenario() -> dict[str, Any]:
        fixture.aliases = aliases
        async with (
            serve(fixture.app()) as native,
            serve(fixture.modern_app()) as modern,
        ):
            fixture.origin, fixture.modern_origin = native, modern
            return await check(
                {
                    a: AccountCredentials(login=a, password=FIXTURE_SECRET)
                    for a in aliases
                },
                ConnectionSettings(
                    synergia_origin=native,
                    api_origin=native,
                    messages_origin=modern,
                    download_origin=fixture.download_origin,
                ),
            )

    return asyncio.run(scenario())


def test_full_check_passes_without_opening_sending_or_consuming() -> None:
    fixture = CommunicationFixture()
    report = run_check(fixture)
    assert report["passed"] is True
    for account in report["accounts"]:
        assert {s["status"] for s in account["steps"]} == {"ok"}
        assert account["steps"][-1]["step"] == "session_alive"
    paths = {path for path, _, _ in fixture.modern_calls}
    assert not any(path.rstrip("/").split("/")[-1].isdigit() for path in paths)
    assert not fixture.sends
    assert all(path != "/uczen/index" for path, _ in fixture.calls)
    # The report carries counts and statuses only, never fixture text.
    assert "Fixture" not in repr(report)


def test_a_failed_check_is_reported_and_fails_the_run() -> None:
    fixture = CommunicationFixture()
    fixture.message_count = 0  # A sender filter can then never narrow.
    report = run_check(fixture)
    assert report["passed"] is False
    failed = [
        s for a in report["accounts"] for s in a["steps"] if s["status"] == "failed"
    ]
    assert failed and all(s["step"].startswith("filtered_page") for s in failed)


@pytest.mark.parametrize(
    "endpoint,reference",
    [
        ("modern_content_received", "19001"),
        ("message_content_received", "19001"),
        ("consume_schedule_events", None),
        ("modern_send_message", None),
        ("modern_messages_received", "19001"),
    ],
)
def test_transport_refuses_anything_outside_the_read_allowlist(
    endpoint: str, reference: str | None
) -> None:
    transport = ReleaseCheckTransport.__new__(ReleaseCheckTransport)
    with pytest.raises(LibrusError) as error:
        asyncio.run(
            transport.request(endpoint, RequestBudget(), reference_id=reference)
        )
    assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
