"""Execute the user-facing examples against the real library and loopback server."""

import ast
import asyncio
import inspect
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import ConnectionSettings, LibrusService
from tests.http_support import FIXTURE_SECRET, serve
from tests.reads_support import ReadsFixture


def test_readme_examples_use_supported_api_without_live_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    examples = re.findall(r"```python\n(.*?)```", readme.read_text(), re.S)
    # Strip only the standalone entry point; execute its real main in our loop.
    first = ast.parse(examples[0])
    first.body.pop()
    monkeypatch.setenv("LIBRUS_LOGIN", "fixture")
    monkeypatch.setenv("LIBRUS_PASSWORD", FIXTURE_SECRET)
    monkeypatch.setenv("LIBRUS_CONTEXT_KEY", bytes(range(32)).hex())

    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin

            def local_service(*args: Any, **kwargs: Any) -> LibrusService:
                return LibrusService(
                    *args,
                    **kwargs,
                    connection=ConnectionSettings(
                        synergia_origin=origin, api_origin=origin
                    ),
                )

            monkeypatch.setattr("librus_python_api.LibrusService", local_service)
            namespace: dict[str, Any] = {}
            exec(compile(first, "README.md", "exec"), namespace)
            await namespace["main"]()
            async with fixture.service(("fixture",)) as service:
                namespace.update(client=service.account("fixture"), date=date)
                for example in examples[1:]:
                    result = eval(
                        compile(
                            example,
                            "README.md",
                            "exec",
                            flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                        ),
                        namespace,
                    )
                    if inspect.isawaitable(result):
                        await result
            assert {operation for operation, _ in fixture.reads} >= {
                "student_information",
                "homework",
                "final_grades",
                "timetable",
                "attendance",
                "announcements",
                "messages_received",
            }

    asyncio.run(scenario())
