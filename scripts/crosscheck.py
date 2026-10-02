"""Compare parser output with Chromium's rendering of captured pages, offline.

Chromium parses HTML independently of lxml, so agreement guards against the
parser misreading structure. Scripts are disabled and every network request is
aborted. Requires a local Chromium and Playwright:

    uv run --with playwright python scripts/crosscheck.py DIR [DIR ...]
"""

import asyncio
import json
import sys
from collections.abc import Callable
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from librus_python_api.completed_lessons import parse_completed_lessons
from librus_python_api.exceptions import LibrusError
from librus_python_api.messages import parse_messages
from librus_python_api.models import MessageFolder
from librus_python_api.parsers import parse_profile
from librus_python_api.school_reads import (
    parse_agenda,
    parse_homework,
    parse_school_detail,
)
from librus_python_api.timetable import parse_timetable

CHROMIUM = "/usr/bin/chromium"

AGENDA_DOM = r"""() => [...document.querySelectorAll('div.kalendarz-dzien')].map(d => {
 const events = [...d.querySelectorAll('tr')].map(r => {
   const c = r.querySelector(':scope > td');
   const s = c.querySelector('span');
   const ids = [c,...c.querySelectorAll('[onclick]')].flatMap(n =>
    [...(n.getAttribute('onclick')||'').matchAll(
     /['"]\/terminarz\/szczegoly\/([0-9]+)['"]/g)].map(m=>m[1]));
   const t = document.createElement('div');
   t.innerHTML = c.getAttribute('title') || '';
   document.body.appendChild(t); const tooltip = t.innerText; t.remove();
   return {text:c.innerText, subject:s?s.innerText:null, tooltip,
    reference:ids[0]||null};
  });
 return {day:Number(d.querySelector('div.kalendarz-numer-dnia').innerText),events};
})"""

DETAIL_DOM = """() => [...document.querySelectorAll('div.container-background tr')]
 .map(r=>({header:!!r.closest('thead'),cells:[...r.children].map(c=>c.innerText)}))"""

HOMEWORK_DOM = """() => ({
 empty:document.querySelectorAll('p.msgEmptyTable').length,
 rows:[...document.querySelectorAll('table.myHomeworkTable tbody tr')]
  .map(r=>[...r.children].map(c=>c.innerText))
})"""

LESSONS_DOM = r"""() => ({
 pagination:[...document.querySelectorAll('div.pagination > span')]
  .map(n=>n.innerText),
 rows:[...document.querySelectorAll('table.decorated tr')]
  .filter(r=>!r.closest('thead')).map(r=>[...r.children].map(c=>c.innerText))
})"""


TIMETABLE_DOM = r"""() => [...document.querySelectorAll('td#timetableEntryBox')]
 .map(c => ({
  day: c.dataset.date, from: c.dataset.time_from,
  lessons: [...c.querySelectorAll('div.text')].map(d => d.innerText),
  changes: [...c.querySelectorAll('div.plan-lekcji-info')].map(d => {
    const a = d.closest('a[title]') || d.querySelector('a[title]');
    const t = document.createElement('div');
    t.innerHTML = a ? a.getAttribute('title') : '';
    document.body.appendChild(t); const tooltip = t.innerText; t.remove();
    return {label: d.innerText, tooltip};
  }),
 }))"""

PROFILE_DOM = """() => Object.fromEntries([...document.querySelectorAll('tr')]
 .filter(r => r.children.length === 2)
 .map(r => [r.children[0].innerText.replace(/:$/, '').trim(),
   r.children[1].innerText]))"""

MESSAGES_DOM = r"""() => {
 const table = document.querySelector('table.decorated.stretch');
 if (!table) throw Error('mailbox table absent');
 const headers = [...table.tHead.rows[0].cells].map(c=>c.innerText.trim());
 const sender = headers.indexOf('Nadawca'), recipient = headers.indexOf('Adresat');
 const role = sender === -1 ? recipient : sender;
 const subject = headers.indexOf('Temat');
 const sent = headers.findIndex(t=>t.startsWith('Wysłano'));
 const read = headers.indexOf('Przeczytano');
 const rows = [...table.tBodies].flatMap(b=>[...b.rows]);
 const empty = rows.length === 1 && rows[0].cells.length === 1 &&
  rows[0].innerText.trim() === 'Brak wiadomości';
 const pagination = [...document.querySelectorAll('div.pagination > span')]
  .map(n=>n.innerText);
 return {empty, pagination, rows: empty ? [] : rows.map(r=>({
   correspondent:r.cells[role].innerText, subject:r.cells[subject].innerText,
   timestamp:r.cells[sent].innerText,
   links:[r.cells[role],r.cells[subject]].map(c=>c.querySelector('a').getAttribute('href')),
   unread:sender === -1 ? null :
    Number(getComputedStyle(r.cells[subject]).fontWeight) >= 700,
   attachment:!!r.cells[1].querySelector('img'),
   recipient_read_status:read === -1 ? null : r.cells[read].innerText,
 }))};
}"""


def normalized(value: str | None) -> str:
    return " ".join((value or "").split())


def same(native: list[Any], rendered: list[Any], what: str) -> None:
    left, right = list(map(normalized, native)), list(map(normalized, rendered))
    if left != right:
        raise AssertionError(f"{what}: parser {left!r} != browser {right!r}")


type Form = dict[str, str]


def check_agenda(body: bytes, form: Form, view: Any) -> str:
    year, month = int(form["rok"]), int(form["miesiac"])
    days = parse_agenda(body, year, month, "crosscheck")
    if [day.day.day for day in days] != [day["day"] for day in view]:
        raise AssertionError("agenda days differ")
    for day, rendered in zip(days, view, strict=True):
        if len(day.events) != len(rendered["events"]):
            raise AssertionError(f"agenda day {day.day.day}: event count differs")
        for event, cell in zip(day.events, rendered["events"], strict=True):
            same(
                [event.text, event.subject, event.metadata_text],
                [cell["text"], cell["subject"], cell["tooltip"]],
                "event",
            )
            reference = event.reference.identifier if event.reference else None
            if reference != cell["reference"]:
                raise AssertionError("agenda reference differs")
    return f"{sum(len(day.events) for day in days)} events"


def check_detail(body: bytes, form: Form, view: Any) -> str:
    title, fields, notes = parse_school_detail(body)
    pairs = [row["cells"] for row in view if len(row["cells"]) == 2]
    same([value for pair in fields for value in pair], sum(pairs, []), "fields")
    singles = [row for row in view if len(row["cells"]) == 1]
    same(
        [title] if title else [],
        [r["cells"][0] for r in singles if r["header"]],
        "title",
    )
    rendered_notes = [r["cells"][0] for r in singles if not r["header"]]
    same(list(notes), [note for note in rendered_notes if normalized(note)], "notes")
    return f"{len(fields)} fields"


def check_homework(body: bytes, form: Form, view: Any) -> str:
    items = parse_homework(body, "crosscheck")
    if not items and view["empty"] != 1:
        raise AssertionError("empty homework without an empty marker")
    if len(items) != len(view["rows"]):
        raise AssertionError("homework row count differs")
    for item, cells in zip(items, view["rows"], strict=True):
        native = [item.subject, item.teacher, item.topic, item.category]
        same(native, cells[:4], "homework text")
        same([item.assigned_on.isoformat()], [cells[4]], "assigned date")
        same([item.due_on.isoformat()], [cells[6]], "due date")
        same([item.submission_status], [cells[8]], "submission status")
    return f"{len(items)} rows"


def check_lessons(body: bytes, form: Form, view: Any) -> str:
    items, count, _ = parse_completed_lessons(
        body,
        date.fromisoformat(form["data1"]),
        date.fromisoformat(form["data2"]),
        int(form["numer_strony1001"]),
    )
    if len(items) != len(view["rows"]):
        raise AssertionError("lesson row count differs")
    return f"{len(items)} lessons, {count} pages"


def check_timetable(body: bytes, form: Form, view: Any) -> str:
    monday = date.fromisoformat(form["tydzien"].partition("_")[0])
    slots = {
        (period.interval.starts_at.strftime("%H:%M"), day.day.isoformat()): period
        for day in parse_timetable(body, monday)
        for period in day.periods
    }
    if len(slots) != len(view):
        raise AssertionError("timetable slot count differs")
    for cell in view:
        period = slots[(cell["from"], cell["day"])]
        if len(period.lessons) != len(cell["lessons"]):
            raise AssertionError("timetable lesson count differs")
        for lesson, text in zip(period.lessons, cell["lessons"], strict=True):
            # The page renders "Subject -Teacher"; compare the parts, not spacing.
            rendered = normalized(text)
            if not rendered.startswith(lesson.subject):
                raise AssertionError("timetable subject differs")
            teacher = rendered[len(lesson.subject) :].strip().removeprefix("-")
            same([lesson.teacher_and_classroom or ""], [teacher], "teacher")
        notices = cell["changes"]
        same([c.label for c in period.changes], [n["label"] for n in notices], "notice")
        for change, notice in zip(period.changes, notices, strict=True):
            fields = [f"{key}: {value}" for key, value in change.metadata]
            same([" ".join(fields)], [notice["tooltip"]], "notice tooltip")
    return f"{len(slots)} slots"


def check_profile(body: bytes, form: Form, view: Any) -> str:
    fields = parse_profile(body)
    labels = {
        "name": "Imię i nazwisko ucznia",
        "class_name": "Klasa",
        "tutor": "Wychowawca",
        "school": "Szkoła",
    }
    for attribute, label in labels.items():
        same([getattr(fields, attribute)], [view.get(label)], label)
    same([str(fields.register_number)], [view.get("Nr w dzienniku")], "number")
    return "profile fields"


def check_messages(folder: MessageFolder, body: bytes, form: Form, view: Any) -> str:
    items, count, _ = parse_messages(
        body, folder, int(form["numer_strony105"]), "crosscheck"
    )
    if len(items) != len(view["rows"]) or (not items) != view["empty"]:
        raise AssertionError("mailbox row count/empty marker differs")
    for item, row in zip(items, view["rows"], strict=True):
        fields = [
            item.correspondent,
            item.subject,
            item.timestamp.raw,
            item.recipient_read_status,
        ]
        rendered = [
            row["correspondent"],
            row["subject"],
            row["timestamp"],
            row["recipient_read_status"],
        ]
        if list(map(normalized, fields)) != list(map(normalized, rendered)):
            raise AssertionError("mailbox visible fields differ")
        if item.unread != row["unread"] or item.has_attachment != row["attachment"]:
            raise AssertionError("mailbox rendered flags differ")
        for link in row["links"]:
            parts = link.split("/")
            if parts[4] != item.reference.identifier or parts[3] != (
                "5" if folder is MessageFolder.RECEIVED else "6"
            ):
                raise AssertionError("mailbox reference differs")
    if not view["pagination"] and count != 1:
        raise AssertionError("mailbox page count differs")
    return (
        f"{len(items)} messages, {count} pages; visible fields/references/flags agree"
    )


CHECKS: dict[str, tuple[str, Callable[[bytes, Form, Any], str]]] = {
    "messages_received": (
        MESSAGES_DOM,
        partial(check_messages, MessageFolder.RECEIVED),
    ),
    "messages_sent": (MESSAGES_DOM, partial(check_messages, MessageFolder.SENT)),
    "agenda": (AGENDA_DOM, check_agenda),
    "agenda_detail": (DETAIL_DOM, check_detail),
    "homework_detail": (DETAIL_DOM, check_detail),
    "homework": (HOMEWORK_DOM, check_homework),
    "completed_lessons": (LESSONS_DOM, check_lessons),
    "timetable": (TIMETABLE_DOM, check_timetable),
    "student_information": (PROFILE_DOM, check_profile),
}


async def check_directory(page: Page, directory: Path) -> bool:
    passed = True
    for entry in json.loads((directory / "index.json").read_text())["captured"]:
        check = CHECKS.get(entry["endpoint"])
        if check is None:
            continue
        body = (directory / entry["file"]).read_bytes()
        await page.set_content(body.decode())
        script, compare = check
        try:
            detail = compare(body, entry["form"] or {}, await page.evaluate(script))
        except LibrusError as error:
            detail = f"typed {type(error).__name__}"
            if entry["endpoint"].startswith("messages_"):
                passed = False
        except AssertionError as error:
            passed = False
            detail = f"MISMATCH {error}"
        print(f"{directory.name}/{entry['file']}: {detail}")
    return passed


async def main(directories: list[Path]) -> int:
    async with async_playwright() as engine:
        browser = await engine.chromium.launch(executable_path=CHROMIUM)
        context = await browser.new_context(java_script_enabled=False, offline=True)
        page = await context.new_page()
        await page.route("**/*", lambda route: route.abort())
        results = [await check_directory(page, path) for path in directories]
        await browser.close()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main([Path(arg) for arg in sys.argv[1:]])))
