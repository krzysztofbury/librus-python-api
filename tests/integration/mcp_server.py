"""Minimal consumer subprocess launcher for native read integration tests."""

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlsplit

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    SchedulerLimits,
)
from tests.http_support import FIXTURE_SECRET

ALIASES = ("student-a", "parent-a", "student-b", "parent-b")
RATE = 25.0
BURST = 2


async def serve(consumer: Path, origin: str) -> None:
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "localhost":
        raise ValueError("Integration tests permit localhost fixture destinations only")
    sys.path.insert(0, str(consumer))
    from src.librus_client import LibrusManager
    from src.native_grades import NativeFinalGradesBackend
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
        LibrusManager.set_final_grades_backend(NativeFinalGradesBackend(service))
        try:
            register_optional_tools()
            await mcp.run_stdio_async()
        finally:
            LibrusManager.set_identity_backend(None)
            LibrusManager.set_final_grades_backend(None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consumer", type=Path)
    parser.add_argument("origin")
    args = parser.parse_args()
    asyncio.run(serve(args.consumer.resolve(), args.origin))
