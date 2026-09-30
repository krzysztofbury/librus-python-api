"""Original synthetic loopback fixtures; not captured Librus responses."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiohttp import web


@asynccontextmanager
async def serve(app: web.Application) -> AsyncIterator[str]:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        yield f"http://localhost:{runner.addresses[0][1]}"
    finally:
        await runner.cleanup()
