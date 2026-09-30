"""Maximum accepted body parser/loop responsiveness measurement, offline only."""

import asyncio
import json
import time
import tracemalloc
from dataclasses import asdict, dataclass

from librus_python_api import RequestBudget
from librus_python_api.parsers import parse_identity, parse_profile
from librus_python_api.parsing import ParserPool
from tests.http_support import profile_html

MAX_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class ParserReport:
    maximum_body_bytes: int
    jobs: int
    elapsed_seconds: float
    heartbeat_max_delay_seconds: float
    traced_peak_bytes: int


async def measure() -> ParserReport:
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
    pool = ParserPool(MAX_BYTES)
    delays: list[float] = []
    finished = asyncio.Event()

    async def heartbeat() -> None:
        while not finished.is_set():
            start = time.monotonic()
            await asyncio.sleep(0.001)
            delays.append(max(0.0, time.monotonic() - start - 0.001))

    tracemalloc.start()
    start = time.monotonic()
    pulse = asyncio.create_task(heartbeat())
    try:
        await asyncio.gather(
            *(
                pool.run(parse_identity, identity, RequestBudget())
                if index % 2 == 0
                else pool.run(parse_profile, profile, RequestBudget())
                for index in range(8)
            )
        )
    finally:
        finished.set()
        await pulse
        pool.close()
    elapsed = time.monotonic() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    delay = max(delays, default=0.0)
    # Coarse local regression thresholds, not a portable latency guarantee.
    assert elapsed < 10
    assert delay < 0.25
    assert peak < 32 * 1024 * 1024
    return ParserReport(MAX_BYTES, 8, elapsed, delay, peak)


if __name__ == "__main__":
    print(json.dumps(asdict(asyncio.run(measure())), indent=2))
