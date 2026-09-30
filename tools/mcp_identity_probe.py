"""Installed-library E2E proof through the real consumer stdio adapter.

Run in an environment containing this built library and the consumer's locked
dependencies. Every credential/response here is synthetic. No live destination,
credential discovery, private session injection, or mocked retrieval is used.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    SchedulerLimits,
    __version__,
)
from tests.http_support import FIXTURE_SECRET, SchoolFixture, serve

ALIASES = ("student-a", "parent-a", "student-b", "parent-b")
RATE = 25.0
BURST = 2
SCRIPT = Path(__file__).resolve()


@dataclass(frozen=True, slots=True)
class ProbeReport:
    version: str
    tool_count: int
    independent_logins: int
    cold_requests: int
    warm_requests: int
    reused_connections: int
    total_elapsed_seconds: float
    rate_limit_requests_per_second: float
    live_verification: bool = False


async def child(consumer: Path, origin: str) -> None:
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "localhost":
        raise ValueError("Probe permits localhost fixture destinations only")
    sys.path.insert(0, str(consumer))
    from src.librus_client import LibrusManager
    from src.native_identity import NativeIdentityBackend
    from src.server import mcp, register_optional_tools

    async with LibrusService(
        {
            alias: AccountCredentials(login=alias, password=FIXTURE_SECRET)
            for alias in ALIASES
        },
        connection=ConnectionSettings(synergia_origin=origin, api_origin=origin),
        scheduler_limits=SchedulerLimits(requests_per_second=RATE, burst=BURST),
    ) as service:
        LibrusManager.set_identity_backend(NativeIdentityBackend(service))
        try:
            register_optional_tools()
            await mcp.run_stdio_async()
        finally:
            LibrusManager.set_identity_backend(None)


async def probe(consumer: Path) -> ProbeReport:
    fixture = SchoolFixture()
    fixture.profile_status[ALIASES[-1]] = 403
    started = time.monotonic()
    async with serve(fixture.app()) as origin:
        fixture.origin = origin
        # Do not inherit real operator configuration into this experiment.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("LIBRUS_")
        }
        environment.update(
            {
                "LIBRUS_ACCOUNTS": json.dumps(
                    [
                        {"alias": alias, "username": alias, "password": FIXTURE_SECRET}
                        for alias in ALIASES
                    ]
                ),
                "LIBRUS_FEATURES": "{}",
                "PYTHONPATH": str(SCRIPT.parents[1]),
            }
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(SCRIPT), str(consumer), "--serve", origin],
            cwd=consumer,
            env=environment,
        )
        async with asyncio.timeout(30), stdio_client(parameters) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 24
                results = await asyncio.gather(
                    *(
                        session.call_tool(
                            "get_student_information", {"student_alias": alias}
                        )
                        for alias in ALIASES
                        for _ in range(3)
                    )
                )
                for index, alias in enumerate(ALIASES):
                    for result in results[index * 3 : index * 3 + 3]:
                        if alias == ALIASES[-1]:
                            assert result.is_error is True
                            assert isinstance(result.content[0], TextContent)
                            assert "access_denied" in result.content[0].text
                            assert alias not in result.content[0].text
                            continue
                        expected = {
                            "name": "Fixture Student",
                            "class_name": "1 TEST",
                            "number": 12,
                            "tutor": "Fixture Tutor",
                            "school": f"Fixture School {alias}",
                            "lucky_number": 7,
                        }
                        assert result.is_error is not True
                        assert result.structured_content == expected
                        assert isinstance(result.content[0], TextContent)
                        assert json.loads(result.content[0].text) == expected
                cold = len(fixture.calls)
                assert cold == 28
                assert fixture.logins == dict.fromkeys(ALIASES, 1)
                await asyncio.gather(
                    *(
                        session.call_tool(
                            "get_student_information", {"student_alias": alias}
                        )
                        for alias in ALIASES
                    )
                )
                warm = len(fixture.calls) - cold
                assert warm == 3
                assert len(fixture.connections) == 4
                # Check the combined service token bound, not one per account.
                for index, instant in enumerate(fixture.dispatch_times):
                    assert (
                        index + 1
                        <= BURST + RATE * (instant - fixture.dispatch_times[0]) + 0.1
                    )
    return ProbeReport(
        __version__, 24, 4, cold, warm, 4, time.monotonic() - started, RATE
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consumer", type=Path, help="Consumer adapter checkout")
    parser.add_argument("--serve", metavar="LOCALHOST_ORIGIN", help=argparse.SUPPRESS)
    args = parser.parse_args()
    consumer = args.consumer.resolve()
    if args.serve:
        asyncio.run(child(consumer, args.serve))
    else:
        print(json.dumps(asdict(asyncio.run(probe(consumer))), indent=2))


if __name__ == "__main__":
    main()
