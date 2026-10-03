"""Offline original acknowledgement fixtures, Chromium and inert apix comparison.

No credentials, sessions, HTTP requests or live sends. Synthetic comparison is
not live qualification. Requires optional Playwright and a local apix reference.
"""

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from librus_python_api.config import ENDPOINTS
from librus_python_api.exceptions import LibrusError
from librus_python_api.sending import parse_send_acknowledgement
from scripts.compare_messages import load_reference
from tests.sending_support import acknowledgement


class InertSendClient:
    SEND_MESSAGE_URL = ENDPOINTS["send_message"].path

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    def post(self, url: str, *, data: dict[str, Any]) -> SimpleNamespace:
        assert url == self.SEND_MESSAGE_URL
        assert data["DoKogo"] == ["101"]
        self.calls += 1
        assert self.calls == 1
        return SimpleNamespace(text=self.body.decode(), status_code=200)


async def compare(reference_path: Path) -> dict[str, object]:
    from playwright.async_api import async_playwright

    reference, _ = load_reference(reference_path)
    cases = [
        ("accepted", "Wiadomość została wysłana."),
        ("rejected", "Wiadomość nie została wysłana."),
        ("unknown", "Fixture unknown state"),
    ]
    records = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path="/usr/bin/chromium")
        try:
            context = await browser.new_context(java_script_enabled=False, offline=True)
            page = await context.new_page()
            await page.route("**/*", lambda route: route.abort())
            for expected, marker in cases:
                body = acknowledgement(marker).encode()
                await page.set_content(body.decode())
                rendered = await page.locator(
                    "div.container-background > p"
                ).all_inner_texts()
                assert rendered == [marker]
                try:
                    native = parse_send_acknowledgement(body).value
                except LibrusError:
                    native = "unknown"
                assert native == expected
                client = InertSendClient(body)
                try:
                    external = reference.send_message(
                        client, "Fixture subject", "Fixture body", ["101"]
                    )
                    record = {"apix_boolean": external[0]}
                except Exception as error:
                    record = {"apix_error_type": type(error).__name__}
                assert client.calls == 1
                records.append(
                    {"native": native, "browser_text_matches": True, **record}
                )
        finally:
            await browser.close()
    return {
        "synthetic_only": True,
        "live_requests": 0,
        "same_bytes": True,
        "cases": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(compare(args.reference)), indent=2))
