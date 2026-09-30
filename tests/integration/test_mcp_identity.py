"""Real consumer field mapping and MCP stdio over synthetic HTTP retrieval."""

import asyncio
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

from tests.http_support import FIXTURE_SECRET, SchoolFixture, serve
from tests.integration.mcp_server import ALIASES, BURST, RATE

pytestmark = pytest.mark.integration


def assert_profile(result: CallToolResult, alias: str) -> None:
    assert isinstance(result.content[0], TextContent)
    if alias == ALIASES[-1]:
        assert result.is_error is True
        assert "access_denied" in result.content[0].text
        assert alias not in result.content[0].text
    else:
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
        assert json.loads(result.content[0].text) == expected


async def exercise_identity_tools(
    session: ClientSession,
    fixture: SchoolFixture,
) -> tuple[int, int]:
    await session.initialize()
    tools = await session.list_tools()
    assert len(tools.tools) == 24
    results = await asyncio.gather(
        *(
            session.call_tool("get_student_information", {"student_alias": alias})
            for alias in ALIASES
            for _ in range(3)
        )
    )
    for index, alias in enumerate(ALIASES):
        for result in results[index * 3 : index * 3 + 3]:
            assert_profile(result, alias)
    cold = len(fixture.calls)
    assert cold == 28
    assert fixture.logins == dict.fromkeys(ALIASES, 1)
    warm_results = await asyncio.gather(
        *(
            session.call_tool("get_student_information", {"student_alias": alias})
            for alias in ALIASES
        )
    )
    for alias, result in zip(ALIASES, warm_results, strict=True):
        assert_profile(result, alias)
    warm = len(fixture.calls) - cold
    assert warm == 3
    assert len(fixture.connections) == 4
    for index, instant in enumerate(fixture.dispatch_times):
        assert index + 1 <= BURST + RATE * (instant - fixture.dispatch_times[0]) + 0.1
    return cold, warm


def test_native_identity_through_real_consumer_stdio(
    mcp_checkout: Path,
    pytestconfig: pytest.Config,
    tmp_path: Path,
    record_property: Callable[[str, object], None],
) -> None:
    root = str(pytestconfig.rootpath)
    # Replace operator credentials and state paths; no production state is used.
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("LIBRUS_")
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
            "PYTHONPATH": root,
            "LIBRUS_STATE_DIR": str(tmp_path / "state"),
            "LIBRUS_DOWNLOAD_DIR": str(tmp_path / "downloads"),
        }
    )

    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.profile_status[ALIASES[-1]] = 403
        started = time.monotonic()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "tests.integration.mcp_server", str(mcp_checkout), origin],
                # The consumer has its own tests package. Resolve this launcher
                # from the library root, then add the consumer inside the child.
                cwd=pytestconfig.rootpath,
                env=environment,
            )
            async with asyncio.timeout(30), stdio_client(parameters) as streams:
                async with ClientSession(*streams) as session:
                    cold, warm = await exercise_identity_tools(session, fixture)
        for name, value in (
            ("tool_count", 24),
            ("independent_logins", 4),
            ("cold_requests", cold),
            ("warm_requests", warm),
            ("reused_connections", len(fixture.connections)),
            ("total_elapsed_seconds", time.monotonic() - started),
            ("rate_limit_requests_per_second", RATE),
        ):
            record_property(name, value)

    asyncio.run(scenario())
