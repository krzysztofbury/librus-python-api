"""Installed public API against independently captured private Chromium evidence."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from aiohttp import web

from librus_python_api import MessageFolder, MessageReference, RecipientGroupReference
from librus_python_api.config import ENDPOINTS
from librus_python_api.exceptions import LibrusError
from scripts.crosscheck_communication_coverage import load_capture, normalize, packet
from tests.http_support import SchoolFixture, serve


def load_inputs(directory: Path) -> list[tuple[dict[str, Any], bytes]]:
    path = directory / "browser.json"
    if path.is_symlink() or path.stat().st_size > 1048576:
        raise ValueError("Expectation path/size")
    expected = json.loads(path.read_bytes())
    records = load_capture(directory)
    assert len(records) == len(expected)
    return [(entry, body) for (_, body), entry in zip(records, expected, strict=True)]


async def replay(directory: Path) -> dict[str, object]:
    inputs = await asyncio.to_thread(load_inputs, directory)
    fixture = SchoolFixture()
    app = fixture.app()
    responses = {}
    for entry, body in inputs:
        route = ENDPOINTS[entry["endpoint"]].path
        if "{id}" in route:
            route = route.replace("{id}", entry["reference"])
        key = (route, tuple(sorted((entry["form"] or {}).items())))
        assert key not in responses
        responses[key] = body

    async def captured(request: web.Request) -> web.Response:
        fixture.record(request)
        data = {str(k): str(v) for k, v in (await request.post()).items()}
        key = (request.path, tuple(sorted(data.items())))
        assert key in responses, "No approved captured request"
        return web.Response(body=responses[key], content_type="text/html")

    for route in {key[0] for key in responses}:
        app.router.add_route("*", route, captured)
    async with serve(app) as origin:
        fixture.origin = origin
        async with fixture.service() as service:
            client = service.account("student")
            for entry, _ in inputs:
                operation = entry["endpoint"]
                try:
                    if operation == "recipient_groups":
                        value = packet(
                            operation, (await client.recipient_groups()).groups
                        )
                    elif operation == "recipients":
                        group = RecipientGroupReference(
                            entry["form"]["typAdresata"],
                            "student",
                            entry["form"]["idGrupy"],
                        )
                        if group.identifier == "grupa" and group.selection_id == "0":
                            value = packet(
                                "choices",
                                (await client.recipient_group_choices(group)).items,
                            )
                        else:
                            value = packet(
                                operation, (await client.recipients(group)).items
                            )
                    elif operation.startswith("messages_"):
                        result = await client.messages_page(
                            MessageFolder(operation.removeprefix("messages_")),
                            page=int(entry["form"]["numer_strony105"]),
                        )
                        value = packet(operation, (result.items, result.page_count))
                    else:
                        result_content = await client.message_content(
                            MessageReference(
                                MessageFolder.SENT, entry["reference"], "student"
                            )
                        )
                        value = packet(operation, result_content.content)
                except LibrusError as error:
                    value = {"kind": "unavailable", "error": error.kind.value}
                assert normalize(value) == entry["expected"], (
                    "Installed browser mismatch (values suppressed)"
                )
    return {"responses": len(inputs), "mismatches": 0, "loopback_only": True}


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
