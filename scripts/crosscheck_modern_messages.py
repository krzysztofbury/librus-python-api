"""Offline real-browser plain-text check of actual original-fixture POST bytes.

No external app code is executed or retained. The independent reader applies
the source-informed Base64/UTF-8/newline/HTML semantics, not a live server claim.
Requires optional Playwright and local Chromium.
"""

import asyncio
import json
from typing import Any

from librus_python_api import ModernRecipientReference, SendStatus
from tests.modern_support import ModernFixture


async def crosscheck() -> dict[str, Any]:
    from playwright.async_api import async_playwright

    fixture = ModernFixture()
    bodies = [
        "Fixture body\r\n<plain> &+",
        'Zażółć 😀 <script>alert("fixture")</script> &amp; <b>literal</b>',
        "Fixture\rCR\nLF\r\nCRLF",
    ]
    payloads = []
    async with fixture.running() as service:
        client = service.account("student")
        for body in bodies:
            attempt = client.prepare_modern_send(
                recipients=(
                    ModernRecipientReference(
                        "701", "901", "student", "parentsCouncil", "Fixture class"
                    ),
                ),
                subject="Fixture α subject",
                body=body,
            )
            assert (await attempt.execute()).status is SendStatus.UNKNOWN
            payloads.append(json.loads(fixture.sends[-1][1]))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path="/usr/bin/chromium")
        try:
            context = await browser.new_context(offline=True, service_workers="block")
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            for expected, payload in zip(bodies, payloads, strict=True):
                await page.set_content(
                    '<div id="message"></div><div id="subject"></div>'
                )
                await page.evaluate(
                    r"""payload => {
                    const decode = value => new TextDecoder('utf-8', {fatal: true})
                        .decode(Uint8Array.from(atob(value), c => c.charCodeAt(0)));
                    document.querySelector('#subject').textContent =
                        decode(payload.topic);
                    document.querySelector('#message').innerHTML =
                        decode(payload.content)
                        .replace(/\r\n|\r|\n/g, '<br>');
                }""",
                    payload,
                )
                assert (
                    await page.locator("#subject").inner_text() == "Fixture α subject"
                )
                rendered = await page.locator("#message").inner_text()
                assert rendered == expected.replace("\r\n", "\n").replace("\r", "\n")
                assert await page.locator("#message > :not(br)").count() == 0
                assert payload["receivers"] == {
                    "schoolReceivers": [{"accountId": "701"}]
                }
        finally:
            await browser.close()
    return {
        "synthetic_only": True,
        "live_requests": 0,
        "live_sends": 0,
        "same_wire_bytes": True,
        "browser_text_matches": len(bodies),
        "browser_literal_markup_matches": len(bodies),
        "external_reference_execution": False,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(crosscheck()), indent=2))
