"""Installed public count API replay against independent private browser data."""

import argparse
import asyncio
import json
from pathlib import Path

from aiohttp import web

from tests.http_support import SchoolFixture, serve


def load_inputs(file: Path, expected: Path) -> tuple[bytes, object]:
    if any(p.is_symlink() or p.stat().st_size > 262144 for p in (file, expected)):
        raise ValueError("Capture/expectation limit")
    return file.read_bytes(), json.loads(expected.read_text())


async def replay(file: Path, expected: Path) -> dict[str, object]:
    body, rendered = await asyncio.to_thread(load_inputs, file, expected)
    fixture = SchoolFixture()

    async def counts(request: web.Request) -> web.Response:
        fixture.record(request)
        return web.Response(body=body, content_type="text/html")

    app = fixture.app()
    app.router.add_get("/uczen/index", counts)
    async with serve(app) as origin:
        fixture.origin = origin
        async with fixture.service() as service:
            result = await service.account("student").notification_counts()
            actual = [
                {"category": r.category.value, "label": r.label, "count": r.count}
                for r in result.items
            ]
            assert actual == rendered, "Browser replay mismatch"
    return {"categories": len(actual), "loopback_only": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--expectations", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(replay(args.file, args.expectations))
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
