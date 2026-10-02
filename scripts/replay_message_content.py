"""Installed public content API replay of private captures, exclusively loopback.

The capture directory must also contain owner-only rendered-content.json,
mapping each content filename to independently recorded Chromium expectations:
correspondent, subject, timestamp, optional read_timestamp, normalized rendered
text and attachment [filename, file_id] pairs. Keep it private and delete it
with the raw captures. No native parser generates those expected values.
"""

import argparse
import asyncio
import json
from pathlib import Path

from aiohttp import web

from librus_python_api import MessageFolder, MessageReference, RequestBudget
from librus_python_api.config import ENDPOINTS
from tests.http_support import SchoolFixture, serve


async def replay(directory: Path) -> dict[str, object]:
    if (directory / "index.json").stat().st_size > 1048576:
        raise ValueError("Capture index limit")
    entries = json.loads((directory / "index.json").read_text())["captured"]
    expected_path = directory / "rendered-content.json"
    if expected_path.is_symlink() or expected_path.stat().st_size > 1048576:
        raise ValueError("Independent browser expectation limit")
    expected = json.loads(expected_path.read_text())
    if not 1 <= len(entries) <= 4:
        raise ValueError("Capture count limit")
    content_entries = [
        e for e in entries if e["endpoint"] == "message_content_received"
    ]
    if not content_entries:
        raise ValueError("No content captured")
    fixture = SchoolFixture()
    current = b""
    requests = 0

    async def content(request: web.Request) -> web.Response:
        nonlocal requests
        fixture.record(request)
        requests += 1
        return web.Response(body=current, content_type="text/html")

    app = fixture.app()
    app.router.add_get(ENDPOINTS["message_content_received"].path, content)
    async with serve(app) as origin:
        fixture.origin = origin
        async with fixture.service() as service:
            client = service.account("student")
            budget = RequestBudget(max_requests=8)
            for entry in content_entries:
                name = entry["file"]
                path = directory / name
                if (
                    Path(name).name != name
                    or path.is_symlink()
                    or path.stat().st_size > 262144
                ):
                    raise ValueError("Capture path/size rejected")
                current = path.read_bytes()
                ref = MessageReference(
                    MessageFolder.RECEIVED, entry["reference"], "student"
                )
                result = await client.message_content(
                    ref, allow_mark_read=True, budget=budget
                )
                data = result.content
                observed = {
                    "correspondent": data.correspondent,
                    "subject": data.subject,
                    "timestamp": data.timestamp.raw,
                    "read_timestamp": data.read_timestamp.raw
                    if data.read_timestamp
                    else None,
                    "text": data.text,
                    "attachments": [
                        (a.filename, a.reference.identifier) for a in data.attachments
                    ],
                }
                assert json.loads(json.dumps(observed)) == expected[name]
                assert data.reference == ref
                assert all(a.reference.message == ref for a in data.attachments)
                assert result.may_mark_read is True
                before = budget.requests_dispatched
                assert (
                    await client.message_content(
                        ref, allow_mark_read=True, budget=budget, max_age_seconds=60
                    )
                    is result
                )
                assert budget.requests_dispatched == before
    return {
        "responses": len(content_entries),
        "opens": requests,
        "loopback_only": True,
        "warm_cache_requests": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        report = asyncio.run(replay(args.directory))
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
