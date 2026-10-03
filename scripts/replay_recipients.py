"""Exercise the installed public recipient API with private captures on loopback.

Authentication is synthetic and every HTTP destination is local. Captured HTML
is data only; it is never rendered with scripts or fetched embedded resources.
Keep the capture directory outside Git and delete it after qualification.
"""

import argparse
import asyncio
import json
from pathlib import Path

from aiohttp import web

from librus_python_api import RequestBudget
from librus_python_api.config import ENDPOINTS
from tests.http_support import SchoolFixture, serve


async def replay(directory: Path) -> dict[str, object]:
    if (directory / "index.json").stat().st_size > 1024 * 1024:
        raise ValueError("Capture index limit")
    entries = json.loads((directory / "index.json").read_text())["captured"]
    if not 1 <= len(entries) <= 10:
        raise ValueError("Capture entry limit")
    bodies: dict[tuple[str, str | None], bytes] = {}
    for entry in entries:
        if entry["endpoint"] not in {"recipient_groups", "recipients"}:
            continue
        name = entry["file"]
        path = directory / name
        if Path(name).name != name or path.is_symlink() or path.stat().st_size > 262144:
            raise ValueError("Capture body path or size rejected")
        token = (entry["form"] or {}).get("typAdresata")
        bodies.setdefault((entry["endpoint"], token), path.read_bytes())
    fixture = SchoolFixture()

    async def groups(request: web.Request) -> web.Response:
        fixture.record(request)
        return web.Response(
            body=bodies[("recipient_groups", None)], content_type="text/html"
        )

    async def recipients(request: web.Request) -> web.Response:
        fixture.record(request)
        fields = await request.post()
        token = str(fields["typAdresata"])
        return web.Response(
            body=bodies[("recipients", token)], content_type="text/html"
        )

    app = fixture.app()
    app.router.add_get(ENDPOINTS["recipient_groups"].path, groups)
    app.router.add_post(ENDPOINTS["recipients"].path, recipients)
    counts: list[int] = []
    async with serve(app) as origin:
        fixture.origin = origin
        async with fixture.service() as service:
            client = service.account("student")
            budget = RequestBudget(max_requests=16)
            selectors = await client.recipient_groups(budget=budget, max_age_seconds=60)
            for group in selectors.groups:
                if ("recipients", group.reference.identifier) not in bodies:
                    continue
                result = await client.recipients(
                    group.reference, budget=budget, max_age_seconds=60
                )
                assert all(r.reference.account == "student" for r in result.items)
                before = budget.requests_dispatched
                assert (
                    await client.recipients(
                        group.reference, budget=budget, max_age_seconds=60
                    )
                    is result
                )
                assert budget.requests_dispatched == before
                counts.append(len(result.items))
    if not counts:
        raise ValueError("No captured populated lookup exercised")
    return {
        "group_types": len(selectors.groups),
        "lookups": len(counts),
        "recipient_counts": counts,
        "loopback_only": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(replay(args.directory))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))
