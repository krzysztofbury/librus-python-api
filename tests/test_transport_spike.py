import asyncio

from tools.transport_spike import run_spike


def test_aiohttp_loopback_selection_evidence() -> None:
    report = asyncio.run(run_spike())
    assert report.isolated_accounts == 4
    assert report.scoped_duplicate_cookies
    assert report.oversized_body_rejected
    assert report.canceled_connection_released
    assert report.deadline_enforced
