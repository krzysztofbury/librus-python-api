"""Bounded semantic school announcements, independently authored from requirements."""

import hashlib
import re
from datetime import date

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    ANNOUNCEMENT_EMPTY_CLASSES,
    ANNOUNCEMENT_EMPTY_MARKERS,
    ANNOUNCEMENT_LABELS,
    ANNOUNCEMENT_MAX_CONTENT_LENGTH,
    ANNOUNCEMENT_MAX_FIELD_LENGTH,
    ANNOUNCEMENT_MAX_ITEMS,
    ANNOUNCEMENT_MAX_TOTAL_TEXT_LENGTH,
    ANNOUNCEMENT_TABLE_CLASSES,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import Announcement
from librus_python_api.parsers import parse_page


def _label(cell: html.HtmlElement) -> str | None:
    return ANNOUNCEMENT_LABELS.get(
        markup.text(cell, ANNOUNCEMENT_MAX_FIELD_LENGTH).rstrip(":").casefold()
    )


def _empty(document: html.HtmlElement) -> bool:
    markers: list[html.HtmlElement] = []
    for node in document.iter("div"):
        if ANNOUNCEMENT_EMPTY_CLASSES <= set(node.get("class", "").split()):
            for child in node:
                if child.tag == "div":
                    markers.extend(p for p in child if p.tag == "p")
    if len(markers) > 1:
        raise LibrusError(ErrorKind.PARSE)
    return bool(markers) and (
        markup.text(markers[0], ANNOUNCEMENT_MAX_FIELD_LENGTH).rstrip(".").casefold()
        in ANNOUNCEMENT_EMPTY_MARKERS
    )


def _tables(document: html.HtmlElement) -> list[html.HtmlElement]:
    tables = []
    for table in document.iter("table"):
        classes = set(table.get("class", "").split())
        labels = {
            _label(cell)
            for row in markup.rows(table)
            for cell in markup.cells(row)
            if cell.tag == "th"
        } - {None}
        known = ANNOUNCEMENT_TABLE_CLASSES <= classes
        if not known and len(labels) >= 2:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if known:
            if next(table.iterancestors("table"), None) is not None:
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            tables.append(table)
            if len(tables) > ANNOUNCEMENT_MAX_ITEMS:
                raise LibrusError(ErrorKind.LIMIT)
    return tables


def _fields(table: html.HtmlElement) -> dict[str, str]:
    if len(list(table.iter("table"))) != 1:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    fields: dict[str, str] = {}
    for row in markup.rows(table):
        key: str | None
        cells = markup.cells(row)
        if next(row.iterancestors("thead"), None) is not None:
            if len(cells) != 1 or cells[0].tag != "td" or "title" in fields:
                raise LibrusError(ErrorKind.PARSE)
            key, cell = "title", cells[0]
            if cell.get("colspan", "1") not in {"1", "2"}:
                raise LibrusError(ErrorKind.PARSE)
        elif {"line0", "line1"}.intersection(row.get("class", "").split()):
            if len(cells) != 2 or [cell.tag for cell in cells] != ["th", "td"]:
                raise LibrusError(ErrorKind.PARSE)
            key, cell = _label(cells[0]), cells[1]
            if key is None:
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            if any(
                c.get("colspan", "1") != "1" or c.get("rowspan", "1") != "1"
                for c in cells
            ):
                raise LibrusError(ErrorKind.PARSE)
        elif markup.text(row, ANNOUNCEMENT_MAX_FIELD_LENGTH):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        else:
            continue
        if key in fields or cell.get("rowspan", "1") != "1":
            raise LibrusError(ErrorKind.PARSE)
        limit = (
            ANNOUNCEMENT_MAX_CONTENT_LENGTH
            if key == "content"
            else ANNOUNCEMENT_MAX_FIELD_LENGTH
        )
        fields[key] = markup.text(cell, limit, multiline=key == "content")
    if fields.keys() != {"title", "author", "date_text", "content"}:
        raise LibrusError(ErrorKind.PARSE)
    if any(not fields[key] for key in ("title", "author", "date_text")):
        raise LibrusError(ErrorKind.PARSE)
    return fields


def _day(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    raise LibrusError(ErrorKind.PARSE)


def _reference(account: str, fields: dict[str, str]) -> str:
    digest = hashlib.sha256(b"librus-announcements-v1\x00")
    for value in (
        account,
        *(fields[key] for key in ("title", "author", "date_text", "content")),
    ):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return "content-sha256:" + digest.hexdigest()


def parse_announcements(body: bytes, account: str) -> tuple[Announcement, ...]:
    if not isinstance(account, str) or not account or len(account) > 80:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    document = parse_page(body)
    tables, empty = _tables(document), _empty(document)
    if empty and tables:
        raise LibrusError(ErrorKind.PARSE)
    if not tables and not empty:
        raise LibrusError(ErrorKind.PARSE)
    items = []
    total = 0
    for table in tables:
        fields = _fields(table)
        total += sum(len(value) for value in fields.values())
        if total > ANNOUNCEMENT_MAX_TOTAL_TEXT_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        items.append(
            Announcement(
                reference=_reference(account, fields),
                published_on=_day(fields["date_text"]),
                title=fields["title"],
                author=fields["author"],
                date_text=fields["date_text"],
                content=fields["content"],
            )
        )
    return tuple(items)
