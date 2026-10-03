"""Independent offline Chromium semantics for 0.4.5 private capture replay."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from librus_python_api.exceptions import LibrusError
from librus_python_api.message_content import parse_message_content
from librus_python_api.messages import parse_messages
from librus_python_api.models import (
    MessageFolder,
    MessageReference,
    RecipientGroupReference,
)
from librus_python_api.recipients import (
    parse_recipient_group_choices,
    parse_recipient_groups,
    parse_recipients,
)
from scripts.capture_messages import write_private

RECIPIENT_DOM = r"""() => {
 const select = document.querySelector('select[name=idGrupy]');
 if (select) return {kind:'choices',items:[...select.options]
  .filter(o=>o.value!=='0').map(o=>({id:o.value,label:o.text,
   available:!o.disabled && !select.disabled}))};
 const notice = document.querySelector('p.msgEmptyTable');
 if (notice) {
  if (!notice.innerText.trim().startsWith('Uczeń nie jest przydzielony do klasy.'))
   throw Error('Unknown recipient notice');
  return {kind:'unavailable',error:'unsupported_capability'};
 }
 const labels = [...document.querySelectorAll('label')];
 if (labels.length) return {kind:'recipients',items:labels.map(l=>{
  const input=document.getElementById(l.htmlFor);
  if (!input || input.type!=='checkbox') throw Error('Invalid recipient control');
  return {id:input.value,label:l.innerText};
 })};
 const anonymous = document.querySelector('input[name=DoKogo]');
 const twin = document.querySelector('input[name="DoKogo_hid[]"]');
 if (!anonymous || !twin || anonymous.value!==twin.value)
  throw Error('Unrecognized unnamed target');
 return {kind:'recipients',items:[{id:anonymous.value,label:null}]};
}"""

CONTENT_DOM = r"""() => {
 const fields={},individual=[]; let read_timestamp=null;
 for (const t of document.querySelectorAll('table.stretch')) {
  if (t.classList.length!==1) continue;
  const rows=[...t.rows];
  if (rows[0].cells.length===1 && rows[0].innerText.trim()==='Przeczytano') {
   for (const r of rows.slice(1)) individual.push({recipient:r.cells[0].innerText,
    raw_status:r.cells[1].innerText});
  } else for (const r of rows) {
   const key=r.cells[0].innerText.trim().replace(/:$/,'');
   if (key==='Przeczytano') read_timestamp=r.cells[1].innerText;
   else fields[key]=r.cells[1].innerText;
  }
 }
 const body=document.querySelector('.container-message-content');
 if (!body || !fields.Temat || !fields['Wysłano']) throw Error('Missing content');
 return {correspondent:fields.Adresat ?? null,subject:fields.Temat,
  timestamp:fields['Wysłano'],read_timestamp,text:body.innerText,
  recipient_receipts:individual};
}"""


def normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    return value


def packet(operation: str, result: Any) -> dict[str, Any]:
    if operation == "recipient_groups":
        return {
            "kind": "groups",
            "items": [
                {
                    "type": g.reference.identifier,
                    "label": g.label,
                    "available": g.available,
                    "linked": True,
                }
                for g in result
            ],
        }
    if operation == "choices":
        return {
            "kind": "choices",
            "items": [
                {
                    "id": g.reference.selection_id,
                    "label": g.label,
                    "available": g.available,
                }
                for g in result
            ],
        }
    if operation == "recipients":
        return {
            "kind": "recipients",
            "items": [{"id": r.reference.identifier, "label": r.label} for r in result],
        }
    if operation.startswith("messages_"):
        items, count = result
        return {
            "kind": "messages",
            "page_count": count,
            "items": [
                {
                    "id": r.reference.identifier,
                    "correspondent": r.correspondent,
                    "subject": r.subject,
                    "timestamp": r.timestamp.raw,
                    "unread": r.unread,
                    "attachment": r.has_attachment,
                    "recipient_read_status": r.recipient_read_status,
                }
                for r in items
            ],
        }
    return {
        "kind": "content",
        "correspondent": result.correspondent,
        "subject": result.subject,
        "timestamp": result.timestamp.raw,
        "read_timestamp": result.read_timestamp.raw if result.read_timestamp else None,
        "text": result.text,
        "recipient_receipts": [
            {"recipient": r.recipient, "raw_status": r.raw_status}
            for r in result.recipient_receipts
        ],
        "attachments": len(result.attachments),
    }


def native(entry: dict[str, Any], body: bytes) -> dict[str, Any]:
    operation = entry["endpoint"]
    try:
        if operation == "recipient_groups":
            return packet(operation, parse_recipient_groups(body, "offline"))
        if operation == "recipients":
            group = RecipientGroupReference(
                entry["form"]["typAdresata"], "offline", entry["form"]["idGrupy"]
            )
            if group.identifier == "grupa" and group.selection_id == "0":
                return packet("choices", parse_recipient_group_choices(body, group))
            return packet(operation, parse_recipients(body, group))
        if operation.startswith("messages_"):
            items, count, _ = parse_messages(
                body,
                MessageFolder(operation.removeprefix("messages_")),
                int(entry["form"]["numer_strony105"]),
                "offline",
            )
            return packet(operation, (items, count))
        return packet(
            operation,
            parse_message_content(
                body,
                MessageReference(MessageFolder.SENT, entry["reference"], "offline"),
            ),
        )
    except LibrusError as error:
        return {"kind": "unavailable", "error": error.kind.value}


def load_capture(directory: Path) -> list[tuple[dict[str, Any], bytes]]:
    index = json.loads((directory / "index.json").read_bytes())["captured"]
    if len(index) > 24:
        raise ValueError("Capture count bound")
    loaded = []
    for entry in index:
        name = entry["file"]
        path = directory / name
        if Path(name).name != name or path.is_symlink() or path.stat().st_size > 262144:
            raise ValueError("Capture path/size")
        loaded.append((entry, path.read_bytes()))
    return loaded


async def check(directory: Path, expectations: Path) -> dict[str, object]:
    from playwright.async_api import async_playwright

    from scripts.crosscheck import GROUPS_DOM, MESSAGES_DOM

    captures = await asyncio.to_thread(load_capture, directory)
    output = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path="/usr/bin/chromium")
        try:
            context = await browser.new_context(java_script_enabled=False, offline=True)
            page = await context.new_page()
            await page.route("**/*", lambda route: route.abort())
            for entry, body in captures:
                await page.set_content(body.decode())
                operation = entry["endpoint"]
                if operation == "recipient_groups":
                    view = {"kind": "groups", "items": await page.evaluate(GROUPS_DOM)}
                elif operation == "recipients":
                    view = await page.evaluate(RECIPIENT_DOM)
                elif operation.startswith("messages_"):
                    import re

                    displayed = await page.evaluate(MESSAGES_DOM)
                    labels = displayed["pagination"]
                    count = 1
                    if labels:
                        assert len(labels) == 1
                        match = re.search(r"\bz\s*(\d+)", labels[0])
                        assert match is not None
                        count = int(match[1])
                    view = {"kind": "messages", "page_count": count, "items": []}
                    for row in displayed["rows"]:
                        links = row.pop("links")
                        identifiers = []
                        for link in links:
                            match = re.fullmatch(
                                r"/wiadomosci/1/[56]/([0-9]+)(?:/f0)?", link
                            )
                            assert match is not None
                            identifiers.append(match[1])
                        assert identifiers[0] == identifiers[1]
                        view["items"].append({"id": identifiers[0], **row})
                else:
                    view = {"kind": "content", **await page.evaluate(CONTENT_DOM)}
                    view["attachments"] = await page.locator(
                        '[onclick*="pobierz_zalacznik"]'
                    ).count()
                view = normalize(view)
                if normalize(native(entry, body)) != view:
                    raise AssertionError("Native/browser mismatch (values suppressed)")
                output.append({**entry, "expected": view})
        finally:
            await browser.close()
    await asyncio.to_thread(write_private, expectations, json.dumps(output).encode())
    return {
        "responses": len(output),
        "mismatches": 0,
        "scripts_and_network_disabled": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expectations", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(check(args.directory, args.expectations))
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
