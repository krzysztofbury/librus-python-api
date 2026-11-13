"""Bounded e-Justifications list, independently authored from observed structure.

Fixtures and this parser follow a structure-only observation of two parent
logins (2026-11-13); no captured text is used.
"""

import re
from datetime import date, datetime

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    JUSTIFICATION_HEADERS,
    JUSTIFICATION_MAX_CONTENT_LENGTH,
    JUSTIFICATION_MAX_ITEMS,
    JUSTIFICATION_MAX_TEACHERS,
    JUSTIFICATION_MAX_TOTAL_TEXT_LENGTH,
    JUSTIFICATION_STATUSES,
    JUSTIFICATION_TABLE_CLASSES,
    JUSTIFICATION_WINDOW_FIELDS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import Justification, JustificationStatus
from librus_python_api.parsers import is_logged_out_page, parse_page

_DAY = r"([0-9]{4}-[0-9]{2}-[0-9]{2})"
_RANGE = re.compile(rf"od {_DAY} do {_DAY}")
# "lekcja" (one lesson) and "lekcje" were observed; "lekcji" is Polish for
# five or more and is accepted with them.
_ONE_DAY = re.compile(rf"{_DAY}, lekcj[aei]: ([0-9]{{1,2}}(?:, [0-9]{{1,2}})*)")
_SENT = re.compile(rf"{_DAY} ([0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}})")
_STATUS = re.compile(r"(\S+)(?: \((.+)\))?")


def _fail(kind: ErrorKind = ErrorKind.PARSE) -> LibrusError:
    return LibrusError(kind)


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _fail() from None


def _table(document: html.HtmlElement) -> html.HtmlElement:
    tables = [
        table
        for table in document.iter("table")
        if JUSTIFICATION_TABLE_CLASSES <= set(table.get("class", "").split())
    ]
    if len(tables) != 1:
        raise _fail()
    table = tables[0]
    if next(table.iterancestors("table"), None) is not None:
        raise _fail()
    return table


def _section(row: html.HtmlElement) -> str:
    parent = row.getparent()
    return str(parent.tag) if parent is not None else ""


def _header(rows: list[html.HtmlElement]) -> None:
    if len(rows) != 1:
        raise _fail()
    cells = markup.cells(rows[0])
    labels = tuple(markup.text(cell) for cell in cells)
    if labels != JUSTIFICATION_HEADERS:
        raise _fail()


def _window(document: html.HtmlElement) -> tuple[date, date]:
    days: list[date] = []
    for name in JUSTIFICATION_WINDOW_FIELDS:
        inputs = [node for node in document.iter("input") if node.get("name") == name]
        if len(inputs) != 1:
            raise _fail()
        value = inputs[0].get("value", "").strip()
        if not re.fullmatch(_DAY, value):
            raise _fail()
        days.append(_day(value))
    if days[0] > days[1]:
        raise _fail()
    for select in document.iter("select"):
        if select.get("name") != "status":
            continue
        chosen = [
            o.get("value") for o in select.iter("option") if "selected" in o.attrib
        ]
        # A list narrowed to one status would be a silently partial result.
        if any(value not in (None, "", "0") for value in chosen):
            raise _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    return days[0], days[1]


def _period(text: str) -> tuple[date, date, tuple[int, ...]]:
    match = _RANGE.fullmatch(text)
    if match:
        start, end = _day(match[1]), _day(match[2])
        if start > end:
            raise _fail()
        return start, end, ()
    match = _ONE_DAY.fullmatch(text)
    if not match:
        raise _fail()
    day = _day(match[1])
    lessons = tuple(int(item) for item in match[2].split(", "))
    if len(set(lessons)) != len(lessons):
        raise _fail()
    return day, day, lessons


def _teachers(cell: html.HtmlElement) -> tuple[str, ...]:
    text = markup.text(cell, markup.FIELD_LENGTH * 8, multiline=True)
    names = tuple(
        name
        for line in text.splitlines()
        for part in line.split(",")
        if (name := part.strip())
    )
    if len(names) > JUSTIFICATION_MAX_TEACHERS:
        raise _fail(ErrorKind.LIMIT)
    if any(len(name) > markup.FIELD_LENGTH for name in names):
        raise _fail(ErrorKind.LIMIT)
    return names


def _status(text: str) -> tuple[JustificationStatus, str | None]:
    match = _STATUS.fullmatch(text)
    if not match:
        raise _fail()
    value = JUSTIFICATION_STATUSES.get(match[1].casefold())
    if value is None:
        raise _fail()
    decided_by = match[2].strip() if match[2] is not None else None
    if decided_by == "":
        raise _fail()
    return JustificationStatus(value), decided_by


def _has_content(cell: html.HtmlElement) -> bool:
    # The attachment cell was empty on every observed entry; its filled markup
    # is unknown, so only its presence is reported and nothing is followed.
    return len(cell) > 0 or bool((cell.text or "").strip())


def _entry(row: html.HtmlElement) -> Justification:
    cells = markup.cells(row)
    if len(cells) != len(JUSTIFICATION_HEADERS):
        raise _fail()
    if any(
        cell.get("colspan", "1") != "1" or cell.get("rowspan", "1") != "1"
        for cell in cells
    ):
        raise _fail()
    attachment, period, count, content, teachers, sent, status = cells
    start, end, lessons = _period(markup.text(period))
    count_text = markup.text(count)
    if not re.fullmatch(r"[0-9]{1,4}", count_text):
        raise _fail()
    sent_match = _SENT.fullmatch(markup.text(sent))
    if not sent_match:
        raise _fail()
    try:
        sent_at = datetime.fromisoformat(f"{sent_match[1]} {sent_match[2]}")
    except ValueError:
        raise _fail() from None
    state, decided_by = _status(markup.text(status))
    return Justification(
        start=start,
        end=end,
        lessons=lessons,
        absence_count=int(count_text),
        content=markup.text(content, JUSTIFICATION_MAX_CONTENT_LENGTH, multiline=True),
        teachers=_teachers(teachers),
        sent_at=sent_at,
        status=state,
        decided_by=decided_by,
        has_attachment=_has_content(attachment),
    )


def _is_empty_marker(rows: list[html.HtmlElement]) -> bool:
    """The explicit empty row: one cell spanning the whole table.

    Recorded for a login without entries; its exact markup was not captured,
    so only this structural shape is accepted and its text is not read.
    """
    if len(rows) != 1:
        return False
    cells = markup.cells(rows[0])
    return (
        len(cells) == 1
        and cells[0].get("colspan") == str(len(JUSTIFICATION_HEADERS))
        and bool(markup.text(cells[0]))
    )


def parse_justifications(
    body: bytes,
) -> tuple[date, date, tuple[Justification, ...]] | None:
    """The list's window and entries, or None for the "Brak dostępu" page.

    That page is what a login without the module gets (both student logins),
    and also what a session Synergia no longer knows gets; the caller tells
    the two apart.
    """
    if is_logged_out_page(body):
        return None
    document = parse_page(body)
    table = _table(document)
    window = _window(document)
    header: list[html.HtmlElement] = []
    body_rows: list[html.HtmlElement] = []
    for row in markup.rows(table):
        section = _section(row)
        if section == "thead":
            header.append(row)
        elif section == "tfoot":
            if markup.text(row):
                raise _fail()
        else:
            body_rows.append(row)
    _header(header)
    if _is_empty_marker(body_rows):
        return (*window, ())
    if len(body_rows) > JUSTIFICATION_MAX_ITEMS:
        raise _fail(ErrorKind.LIMIT)
    items: list[Justification] = []
    total = 0
    for row in body_rows:
        item = _entry(row)
        total += len(item.content) + sum(len(name) for name in item.teachers)
        total += len(item.decided_by or "")
        if total > JUSTIFICATION_MAX_TOTAL_TEXT_LENGTH:
            raise _fail(ErrorKind.LIMIT)
        items.append(item)
    return (*window, tuple(items))
