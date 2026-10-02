"""Independent Chromium count semantics on private captured bytes, offline only."""

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from librus_python_api.config import NOTIFICATION_DESTINATIONS
from librus_python_api.notifications import parse_notification_counts
from scripts.capture_messages import write_private

COUNTS_DOM = """destinations => {
 const menu = document.querySelector('#graphic-menu');
 if (!menu) throw Error('menu missing');
 const items = [];
 for (const row of menu.querySelectorAll(':scope > ul > li')) {
  const links = [...row.querySelectorAll(':scope > a')];
  const candidates = links.filter(a => !a.classList.contains('counter') &&
      destinations[a.getAttribute('href')]);
  if (!candidates.length) continue;
  if (candidates.length !== 1) throw Error('ambiguous category');
  const counters = links.filter(a => a.classList.contains('counter'));
  if (counters.length > 1) throw Error('ambiguous count');
  const raw = counters.length ? counters[0].innerText.trim() : '0';
  if (!/^[0-9]+$/.test(raw)) throw Error('invalid count');
  items.push({category:destinations[candidates[0].getAttribute('href')],
      label:candidates[0].innerText.trim().replace(/\\s+/g, ' '), count:Number(raw)});
 }
 return items;
}"""


def load_capture(file: Path) -> bytes:
    if file.is_symlink() or file.stat().st_size > 262144:
        raise ValueError("Capture size/path rejected")
    return file.read_bytes()


async def check(file: Path, expected: Path) -> dict[str, object]:
    body = await asyncio.to_thread(load_capture, file)
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium")
        try:
            context = await browser.new_context(java_script_enabled=False, offline=True)
            page = await context.new_page()
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(body.decode())
            rendered = await page.evaluate(COUNTS_DOM, dict(NOTIFICATION_DESTINATIONS))
        finally:
            await browser.close()
    native = [
        {"category": r.category.value, "label": r.label, "count": r.count}
        for r in parse_notification_counts(body)
    ]
    assert native == rendered, "Count/category/label mismatch (values suppressed)"
    await asyncio.to_thread(write_private, expected, json.dumps(rendered).encode())
    return {
        "categories": len(rendered),
        "mismatches": 0,
        "scripts_and_network_disabled": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--expectations", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(check(args.file, args.expectations))
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
