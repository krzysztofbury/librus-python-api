"""Bounded ordinary mailbox summaries; no body opens, mark-read, sends or deletes."""

import hashlib
import re
from dataclasses import astuple
from datetime import datetime

from lxml import html

from librus_python_api.config import (
    MESSAGE_EMPTY_TEXT,
    MESSAGE_HEADER_LABELS,
    MESSAGE_INFORMATION_NOTICES,
    MESSAGE_MAX_BATCH_ITEMS,
    MESSAGE_MAX_BATCH_PAGES,
    MESSAGE_MAX_CURSOR_IDS,
    MESSAGE_MAX_FIELD_LENGTH,
    MESSAGE_MAX_PAGE_COUNT,
    MESSAGE_MAX_PAGE_ITEMS,
    MESSAGE_MAX_TOTAL_TEXT_LENGTH,
    MESSAGE_REFERENCE_PREFIXES,
    message_page_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.markup import cells, in_header, rows, text
from librus_python_api.models import (
    MessageFolder,
    MessageReference,
    MessagesCursor,
    MessageSummary,
    MessageTimestamp,
)
from librus_python_api.parsers import page_notices, parse_page


def validate_selection(
    folder: MessageFolder,
    cursor: MessagesCursor | None,
    max_pages: int,
    limit: int,
    account: str,
) -> None:
    message_page_form(folder, 0)
    if type(max_pages) is not int or not 1 <= max_pages <= MESSAGE_MAX_BATCH_PAGES:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if type(limit) is not int or not 1 <= limit <= MESSAGE_MAX_BATCH_ITEMS:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if cursor is None:
        return
    if not isinstance(cursor, MessagesCursor):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if (
        cursor.account != account
        or cursor.folder is not folder
        or type(cursor.page_count) is not int
        or not 1 <= cursor.page_count <= MESSAGE_MAX_PAGE_COUNT
        or type(cursor.page) is not int
        or not 0 <= cursor.page < cursor.page_count
        or type(cursor.offset) is not int
        or not 0 <= cursor.offset < MESSAGE_MAX_PAGE_ITEMS
        or (cursor.page == 0 and cursor.offset == 0)
        or type(cursor.fingerprint) is not str
        or re.fullmatch(r"[0-9a-f]{64}", cursor.fingerprint) is None
        or type(cursor.seen_ids) is not tuple
        or not 1 <= len(cursor.seen_ids) <= MESSAGE_MAX_CURSOR_IDS
        or any(
            type(i) is not str or re.fullmatch(r"[0-9]{1,64}", i) is None
            for i in cursor.seen_ids
        )
        or len(set(cursor.seen_ids)) != len(cursor.seen_ids)
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)


def _pagination(document: html.HtmlElement, page: int) -> int:
    markers = document.xpath(
        '//div[contains(concat(" ",normalize-space(@class)," ")," pagination ")]'
    )
    if not markers:
        if page:
            raise LibrusError(ErrorKind.PARSE)
        return 1
    if len(markers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    spans = [s for s in markers[0] if s.tag == "span"]
    if len(spans) != 1:
        raise LibrusError(ErrorKind.PARSE)
    label = text(spans[0])
    match = re.fullmatch(
        r"(?:Strona\s*:?\s*)?([0-9]{1,4})\s+z\s+([0-9]{1,4})", label, re.I
    )
    if match is None:
        raise LibrusError(ErrorKind.PARSE)
    current, count = int(match[1]), int(match[2])
    if count > MESSAGE_MAX_PAGE_COUNT:
        raise LibrusError(ErrorKind.LIMIT)
    if not 1 <= current <= count or current != page + 1:
        raise LibrusError(ErrorKind.PARSE)
    return count


def _header(table: html.HtmlElement, folder: MessageFolder) -> int:
    width = 6 if folder is MessageFolder.RECEIVED else 7
    headers = [r for r in rows(table) if in_header(r)]
    if len(headers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    columns = cells(headers[0])
    if len(columns) != width or any(
        c.get("colspan", "1") != "1" or c.get("rowspan", "1") != "1" for c in columns
    ):
        raise LibrusError(ErrorKind.PARSE)
    labels = [text(c) for c in columns]
    if (
        labels[2] != MESSAGE_HEADER_LABELS[folder]
        or labels[3] != "Temat"
        or re.fullmatch(r"Wysłano(?: \[[↑↓]\])?", labels[4]) is None
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if folder is MessageFolder.SENT and labels[5] != "Przeczytano":
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return width


def _reference(
    correspondent: html.HtmlElement,
    subject: html.HtmlElement,
    folder: MessageFolder,
    account: str,
) -> MessageReference:
    identifiers = []
    for cell in (correspondent, subject):
        anchors = list(cell.iter("a"))
        if len(anchors) != 1:
            raise LibrusError(ErrorKind.PARSE)
        match = re.fullmatch(
            re.escape(MESSAGE_REFERENCE_PREFIXES[folder]) + r"([0-9]{1,64})(?:/f0)?",
            anchors[0].get("href", ""),
        )
        if match is None:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        identifiers.append(match[1])
    if identifiers[0] != identifiers[1]:
        raise LibrusError(ErrorKind.PARSE)
    return MessageReference(folder, identifiers[0], account)


def _timestamp(value: str) -> MessageTimestamp:
    if (
        re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}(?::[0-9]{2})?", value
        )
        is None
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    try:
        local = datetime.fromisoformat(value)
    except ValueError:
        local = None
    if local is None:
        raise LibrusError(ErrorKind.PARSE)
    # The page carries no UTC offset/fold. Retain school civil time, including
    # ambiguous DST wall times, rather than inventing a specific UTC instant.
    return MessageTimestamp(local, value)


def _unread(subject: html.HtmlElement) -> bool:
    weights = []
    for declaration in subject.get("style", "").split(";"):
        key, separator, value = declaration.partition(":")
        if separator and key.strip().casefold() == "font-weight":
            weights.append(value.strip().casefold().removesuffix("!important").strip())
    if not weights:
        return False
    if len(weights) != 1 or weights[0] not in {"bold", "normal", "400", "700"}:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return weights[0] in {"bold", "700"}


def _summary(
    row: html.HtmlElement, width: int, folder: MessageFolder, account: str
) -> MessageSummary:
    columns = cells(row)
    if len(columns) != width or any(
        c.tag != "td" or c.get("rowspan", "1") != "1" or c.get("colspan", "1") != "1"
        for c in columns
    ):
        raise LibrusError(ErrorKind.PARSE)
    correspondent, subject, stamp = [
        text(c, MESSAGE_MAX_FIELD_LENGTH, multiline=True) for c in columns[2:5]
    ]
    if not correspondent:
        raise LibrusError(ErrorKind.PARSE)
    return MessageSummary(
        _reference(columns[2], columns[3], folder, account),
        correspondent,
        subject,
        _timestamp(stamp),
        _unread(columns[3]) if folder is MessageFolder.RECEIVED else None,
        next(columns[1].iter("img"), None) is not None,
        text(columns[5], MESSAGE_MAX_FIELD_LENGTH, multiline=True)
        if folder is MessageFolder.SENT
        else None,
    )


def parse_messages(
    body: bytes, folder: MessageFolder, page: int, account: str
) -> tuple[tuple[MessageSummary, ...], int, str]:
    message_page_form(folder, page)
    document = parse_page(body)
    if any(
        notice not in MESSAGE_INFORMATION_NOTICES for notice in page_notices(document)
    ):
        raise LibrusError(ErrorKind.PARSE)
    count = _pagination(document, page)
    tables = [
        t
        for t in document.iter("table")
        if {"decorated", "stretch"} <= set(t.get("class", "").split())
    ]
    if len(tables) != 1:
        raise LibrusError(ErrorKind.PARSE)
    table = tables[0]
    if list(table.iterdescendants("table")):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    width = _header(table, folder)
    # The observed legacy table has a blank tfoot. Only tbody contains messages.
    body_rows = [
        r for r in rows(table) if (p := r.getparent()) is not None and p.tag == "tbody"
    ]
    if not body_rows:
        raise LibrusError(ErrorKind.PARSE)
    first = cells(body_rows[0])
    empty = len(first) == 1 and text(first[0]) == MESSAGE_EMPTY_TEXT
    items: list[MessageSummary] = []
    identifiers: set[str] = set()
    total = 0
    if empty:
        if (
            len(body_rows) != 1
            or first[0].get("colspan") != str(width)
            or first[0].get("rowspan", "1") != "1"
            or count != 1
            or page
        ):
            raise LibrusError(ErrorKind.PARSE)
    else:
        for row in body_rows:
            item = _summary(row, width, folder, account)
            if item.reference.identifier in identifiers:
                raise LibrusError(ErrorKind.PARSE)
            identifiers.add(item.reference.identifier)
            total += (
                len(item.correspondent)
                + len(item.subject)
                + len(item.timestamp.raw)
                + len(item.recipient_read_status or "")
            )
            if (
                len(items) >= MESSAGE_MAX_PAGE_ITEMS
                or total > MESSAGE_MAX_TOTAL_TEXT_LENGTH
            ):
                raise LibrusError(ErrorKind.LIMIT)
            items.append(item)
    if len(items) == MESSAGE_MAX_PAGE_ITEMS and not any(
        "pagination" in node.get("class", "").split() for node in document.iter("div")
    ):
        # A full page without a pager cannot prove this is the last page.
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    result = tuple(items)
    # Account/folder scope is already explicit; ordered row identities detect
    # mid-page drift. Read state is excluded: opening a message, here or on
    # another device, changes it without moving any row.
    fingerprint = hashlib.sha256(
        repr(
            tuple(
                (
                    astuple(i.reference),
                    i.correspondent,
                    i.subject,
                    astuple(i.timestamp),
                    i.has_attachment,
                )
                for i in result
            )
        ).encode()
    ).hexdigest()
    return result, count, fingerprint
