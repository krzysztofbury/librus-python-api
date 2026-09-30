"""Real consumer identity/summary mapping over synthetic HTTP and MCP stdio."""

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

from tests.grade_support import GradeFixture, summary_html
from tests.http_support import FIXTURE_SECRET, serve
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


async def exercise_native_tools(
    session: ClientSession,
    fixture: GradeFixture,
    operation: str,
) -> tuple[int, int]:
    await session.initialize()
    tools = await session.list_tools()
    assert len(tools.tools) == 24
    tool_name = (
        "get_student_information" if operation == "identity" else "get_final_grades"
    )
    assert_result = assert_profile if operation == "identity" else assert_summary
    results = await asyncio.gather(
        *(
            session.call_tool(tool_name, {"student_alias": alias})
            for alias in ALIASES
            for _ in range(3)
        )
    )
    for index, alias in enumerate(ALIASES):
        for result in results[index * 3 : index * 3 + 3]:
            assert_result(result, alias)
    cold = len(fixture.calls)
    assert cold == 24
    assert fixture.logins == dict.fromkeys(ALIASES, 1)
    warm_results = await asyncio.gather(
        *(session.call_tool(tool_name, {"student_alias": alias}) for alias in ALIASES)
    )
    for alias, result in zip(ALIASES, warm_results, strict=True):
        assert_result(result, alias)
    warm = len(fixture.calls) - cold
    assert warm == 3
    assert len(fixture.connections) == 4
    for index, instant in enumerate(fixture.dispatch_times):
        assert index + 1 <= BURST + RATE * (instant - fixture.dispatch_times[0]) + 0.1
    return cold, warm


def assert_summary(result: CallToolResult, alias: str) -> None:
    assert isinstance(result.content[0], TextContent)
    if alias == ALIASES[-1]:
        assert result.is_error is True
        assert "access_denied" in result.content[0].text
        assert alias not in result.content[0].text
        return
    expected = [
        {
            "subject": f"Fixture {alias}",
            "midterm": "-" if alias == ALIASES[1] else "progressing",
            "predicted_final": "-",
            "final": "4+",
        },
        {
            "subject": f"Fixture Extra {alias}",
            "midterm": "-",
            "predicted_final": "-",
            "final": "-",
        },
    ]
    assert result.is_error is not True
    assert result.structured_content == {"result": expected}
    assert all(isinstance(content, TextContent) for content in result.content)
    assert [
        json.loads(content.text)
        for content in result.content
        if isinstance(content, TextContent)
    ] == expected


@pytest.mark.parametrize("operation", ["identity", "final_grades"])
def test_native_reads_through_real_consumer_stdio(
    mcp_checkout: Path,
    pytestconfig: pytest.Config,
    tmp_path: Path,
    record_property: Callable[[str, object], None],
    operation: str,
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
        fixture = GradeFixture()
        fixture.profile_status[ALIASES[-1]] = 403
        fixture.grade_status[ALIASES[-1]] = 403
        for alias in ALIASES[:-1]:
            first = summary_html(
                subject=f"Fixture {alias}",
                include_midterm=alias != ALIASES[1],
                include_predicted=alias != ALIASES[1],
            )
            extra = (
                summary_html(
                    subject=f"Fixture Extra {alias}",
                    annual="-",
                    midterm="-",
                    include_midterm=alias != ALIASES[1],
                    include_predicted=alias != ALIASES[1],
                )
                .split("<tbody>")[1]
                .split("</tbody>")[0]
            )
            fixture.grade_bodies[alias] = first.replace("</tbody>", extra + "</tbody>")
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
                    cold, warm = await exercise_native_tools(
                        session, fixture, operation
                    )
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
