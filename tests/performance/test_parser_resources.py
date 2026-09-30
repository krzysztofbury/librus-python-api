"""Maximum accepted parser workload, separate from portable functional tests."""

import asyncio
import json
import time
import tracemalloc
from collections.abc import Callable

import pytest

from librus_python_api import RequestBudget
from librus_python_api.models import ProfileFields
from librus_python_api.parsers import parse_identity, parse_profile
from librus_python_api.parsing import ParserPool
from tests.http_support import profile_html

pytestmark = pytest.mark.performance
MAX_BYTES = 256 * 1024


def maximum_body_payloads() -> tuple[bytes, bytes]:
    identity = json.dumps(
        {"Me": {"Account": {"Id": "owner"}, "User": {"Id": "student"}}}
    ).encode()
    identity += b" " * (MAX_BYTES - len(identity))
    profile = (
        profile_html()
        .replace("</body>", "<span>fixture</span>" * 4000 + "</body>")
        .encode()
    )
    profile += b" " * (MAX_BYTES - len(profile))
    assert len(identity) == len(profile) == MAX_BYTES
    return identity, profile


def test_maximum_body_parser_resources(
    record_property: Callable[[str, object], None],
) -> None:
    async def scenario() -> None:
        identity, profile = maximum_body_payloads()
        pool = ParserPool(MAX_BYTES)
        delays: list[float] = []
        finished = asyncio.Event()

        async def heartbeat() -> None:
            while not finished.is_set():
                start = time.monotonic()
                await asyncio.sleep(0.001)
                delays.append(max(0.0, time.monotonic() - start - 0.001))

        tracing_already_started = tracemalloc.is_tracing()
        if tracing_already_started:
            pytest.fail(
                "Run resource measurements without an existing tracemalloc session"
            )
        tracemalloc.start()
        start = time.monotonic()
        pulse = asyncio.create_task(heartbeat())
        try:
            results = await asyncio.gather(
                *(
                    pool.run(parse_identity, identity, RequestBudget())
                    if index % 2 == 0
                    else pool.run(parse_profile, profile, RequestBudget())
                    for index in range(8)
                )
            )
            for result in results[::2]:
                assert isinstance(result, tuple)
                assert (result[0].id, result[1].id) == ("owner", "student")
            for result in results[1::2]:
                assert isinstance(result, ProfileFields)
                assert result.register_number == 12
                assert result.school == "Synthetic School"
            elapsed = time.monotonic() - start
            _, peak = tracemalloc.get_traced_memory()
        finally:
            finished.set()
            await pulse
            pool.close()
            tracemalloc.stop()
        delay = max(delays, default=0.0)
        for name, value in (
            ("maximum_body_bytes", MAX_BYTES),
            ("jobs", 8),
            ("elapsed_seconds", elapsed),
            ("heartbeat_max_delay_seconds", delay),
            ("traced_peak_bytes", peak),
        ):
            record_property(name, value)
        # Coarse local regression thresholds, not portable latency guarantees.
        assert elapsed < 10
        assert delay < 0.25
        assert peak < 32 * 1024 * 1024

    asyncio.run(scenario())
