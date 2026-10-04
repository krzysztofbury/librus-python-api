"""Bounded modern mailbox parsing and continuation, with distinct backend references."""

import base64
import binascii
import hashlib
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from librus_python_api.config import (
    MESSAGE_MAX_ATTACHMENTS,
    MESSAGE_MAX_BATCH_ITEMS,
    MESSAGE_MAX_BATCH_PAGES,
    MESSAGE_MAX_CONTENT_LENGTH,
    MESSAGE_MAX_CURSOR_IDS,
    MESSAGE_MAX_FIELD_LENGTH,
    MESSAGE_MAX_TOTAL_TEXT_LENGTH,
    modern_mailbox_query,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.markup import text
from librus_python_api.models import (
    MessageFolder,
    ModernMessageAttachment,
    ModernMessageAttachmentReference,
    ModernMessageReference,
    ModernMessagesCursor,
    ModernMessagesPage,
    ModernMessageSummary,
)
from librus_python_api.parsers import decode_json, parse_html_document

MAX_TOTAL_MESSAGES = 50000


def identifier(value: Any) -> str:
    # Modern message/attachment IDs are an explicit bounded compatibility policy;
    # directory identifiers remain independently validated strict strings.
    if type(value) is int and 0 < value < 10**64:
        value = str(value)
    if type(value) is not str or re.fullmatch(r"[0-9]{1,64}", value) is None:
        raise LibrusError(ErrorKind.PARSE)
    return value


def validate_reference(reference: ModernMessageReference, account: str) -> None:
    if (
        not isinstance(reference, ModernMessageReference)
        or not isinstance(reference.folder, MessageFolder)
        or reference.account != account
        or type(reference.identifier) is not str
        or re.fullmatch(r"[0-9]{1,64}", reference.identifier) is None
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)


def _string(value: Any, *, limit: int = MESSAGE_MAX_FIELD_LENGTH) -> str:
    if type(value) is not str or len(value) > limit or "\x00" in value:
        raise LibrusError(ErrorKind.PARSE)
    return value


def _date(value: Any) -> datetime:
    value = _string(value)
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?",
        value,
    ):
        raise LibrusError(ErrorKind.PARSE)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    raise LibrusError(ErrorKind.PARSE)


def _summary(data: Any, folder: MessageFolder, account: str) -> ModernMessageSummary:
    if not isinstance(data, dict):
        raise LibrusError(ErrorKind.PARSE)
    correspondent = (
        data.get("senderName")
        if folder is MessageFolder.RECEIVED
        else data.get("receiverName")
    )
    if folder is MessageFolder.SENT and correspondent in (None, ""):
        correspondent = data.get("senderName")
    name = _string(correspondent)
    if not name.strip():
        raise LibrusError(ErrorKind.PARSE)
    subject, stamp = _string(data.get("topic")), _string(data.get("sendDate"))
    has_attachment = data.get("isAnyFileAttached")
    if type(has_attachment) is not bool or (
        folder is MessageFolder.RECEIVED and "readDate" not in data
    ):
        raise LibrusError(ErrorKind.PARSE)
    # The observed outbox omits readDate. No recipient receipt is inferred.
    read = data.get("readDate")
    read_at = None if read in (None, "") else _date(read)
    return ModernMessageSummary(
        ModernMessageReference(folder, identifier(data.get("messageId")), account),
        name,
        subject,
        _date(stamp),
        stamp,
        read_at,
        read_at is None if folder is MessageFolder.RECEIVED else None,
        has_attachment,
    )


def parse_page(
    body: bytes, folder: MessageFolder, page: int, page_size: int, account: str
) -> tuple[tuple[ModernMessageSummary, ...], int, str]:
    modern_mailbox_query(folder, page, page_size)
    data = decode_json(body)
    if not isinstance(data, dict) or not {"data", "total"} <= set(data):
        raise LibrusError(ErrorKind.PARSE)
    if data.get("archivingInProgress", False) is not False:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    entries, total = data["data"], data["total"]
    if (
        not isinstance(entries, list)
        or type(total) is not int
        or not 0 <= total <= MAX_TOTAL_MESSAGES
    ):
        raise LibrusError(ErrorKind.PARSE)
    if page > max(1, (total + page_size - 1) // page_size):
        raise LibrusError(ErrorKind.STALE_CURSOR)
    expected = min(page_size, max(0, total - (page - 1) * page_size))
    if len(entries) != expected:
        raise LibrusError(ErrorKind.PARSE)
    items = tuple(_summary(item, folder, account) for item in entries)
    if len({item.reference.identifier for item in items}) != len(items):
        raise LibrusError(ErrorKind.PARSE)
    if (
        sum(
            len(item.subject) + len(item.correspondent) + len(item.raw_sent_at)
            for item in items
        )
        > MESSAGE_MAX_TOTAL_TEXT_LENGTH
    ):
        raise LibrusError(ErrorKind.LIMIT)
    fingerprint = hashlib.sha256(
        repr(
            tuple(
                (
                    i.reference.identifier,
                    i.correspondent,
                    i.subject,
                    i.raw_sent_at,
                    i.has_attachment,
                )
                for i in items
            )
        ).encode()
    ).hexdigest()
    return items, total, fingerprint


def parse_content(
    body: bytes, reference: ModernMessageReference
) -> tuple[ModernMessageSummary, str, tuple[ModernMessageAttachment, ...]]:
    data = decode_json(body)
    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        raise LibrusError(ErrorKind.PARSE)
    content = data["data"]
    if content.get("archive", False) not in (False, 0, "0"):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    summary = _summary(content, reference.folder, reference.account)
    if summary.reference != reference:
        raise LibrusError(ErrorKind.PARSE)
    encoded = _string(content.get("Message"), limit=4 * MESSAGE_MAX_CONTENT_LENGTH)
    try:
        decoded = base64.b64decode(encoded, validate=True)
        decoded.decode("utf-8", errors="strict")
    except (ValueError, UnicodeError, binascii.Error):
        raise LibrusError(ErrorKind.PARSE) from None
    if len(decoded) > MESSAGE_MAX_CONTENT_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    rendered = text(
        parse_html_document(decoded), MESSAGE_MAX_CONTENT_LENGTH, multiline=True
    )
    entries = content.get("attachments")
    if not isinstance(entries, list) or len(entries) > MESSAGE_MAX_ATTACHMENTS:
        raise LibrusError(ErrorKind.PARSE)
    attachments = []
    seen = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise LibrusError(ErrorKind.PARSE)
        file_id, name = identifier(raw.get("id")), _string(raw.get("filename"))
        if not name.strip() or file_id in seen:
            raise LibrusError(ErrorKind.PARSE)
        seen.add(file_id)
        attachments.append(
            ModernMessageAttachment(
                ModernMessageAttachmentReference(reference, file_id), name
            )
        )
    return summary, rendered, tuple(attachments)


def validate_selection(
    folder: MessageFolder,
    cursor: ModernMessagesCursor | None,
    page_size: int,
    max_pages: int,
    limit: int,
    account: str,
) -> None:
    modern_mailbox_query(folder, 1, page_size)
    if type(max_pages) is not int or not 1 <= max_pages <= MESSAGE_MAX_BATCH_PAGES:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if type(limit) is not int or not 1 <= limit <= MESSAGE_MAX_BATCH_ITEMS:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if cursor is None:
        return
    if not isinstance(cursor, ModernMessagesCursor):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    modern_mailbox_query(folder, cursor.page, cursor.page_size)
    if (
        cursor.account != account
        or cursor.folder is not folder
        or cursor.page_size != page_size
        or type(cursor.offset) is not int
        or not 0 <= cursor.offset < page_size
        or type(cursor.total_count) is not int
        or not 1 <= cursor.total_count <= MAX_TOTAL_MESSAGES
        or type(cursor.fingerprint) is not str
        or re.fullmatch(r"[0-9a-f]{64}", cursor.fingerprint) is None
        or type(cursor.seen_ids) is not tuple
        or not 1 <= len(cursor.seen_ids) <= MESSAGE_MAX_CURSOR_IDS
        or any(
            type(i) is not str or re.fullmatch(r"[0-9]{1,64}", i) is None
            for i in cursor.seen_ids
        )
        or len(set(cursor.seen_ids)) != len(cursor.seen_ids)
        or cursor.page > (cursor.total_count + page_size - 1) // page_size
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)


async def collect(
    fetch: Callable[[int], Awaitable[ModernMessagesPage]],
    folder: MessageFolder,
    account: str,
    cursor: ModernMessagesCursor | None,
    page_size: int,
    max_pages: int,
    limit: int,
) -> tuple[
    tuple[ModernMessageSummary, ...],
    int,
    int,
    ModernMessagesCursor | None,
    Literal["item_limit", "page_limit"] | None,
]:
    validate_selection(folder, cursor, page_size, max_pages, limit, account)
    page = cursor.page if cursor else 1
    offset = cursor.offset if cursor else 0
    seen = list(cursor.seen_ids) if cursor else []
    seen_set = set(seen)
    items = []
    total = cursor.total_count if cursor else None
    pages = duplicates = 0
    for _ in range(max_pages):
        result = await fetch(page)
        pages += 1
        if (total is not None and result.total_count != total) or (
            cursor
            and cursor.offset
            and pages == 1
            and result.fingerprint != cursor.fingerprint
        ):
            raise LibrusError(ErrorKind.STALE_CURSOR)
        total = result.total_count
        if offset and offset >= len(result.items):
            raise LibrusError(ErrorKind.STALE_CURSOR)
        if (
            result.items
            and offset == 0
            and all(item.reference.identifier in seen_set for item in result.items)
        ):
            raise LibrusError(ErrorKind.STALE_CURSOR)
        new = 0
        for index in range(offset, len(result.items)):
            item = result.items[index]
            if item.reference.identifier in seen_set:
                duplicates += 1
                continue
            if len(seen) >= MESSAGE_MAX_CURSOR_IDS:
                raise LibrusError(ErrorKind.LIMIT)
            items.append(item)
            new += 1
            seen.append(item.reference.identifier)
            seen_set.add(item.reference.identifier)
            if len(items) == limit and index + 1 < len(result.items):
                return (
                    tuple(items),
                    pages,
                    duplicates,
                    ModernMessagesCursor(
                        account,
                        folder,
                        page,
                        index + 1,
                        page_size,
                        total,
                        result.fingerprint,
                        tuple(seen),
                    ),
                    "item_limit",
                )
        if result.items and not new and pages > 1:
            raise LibrusError(ErrorKind.STALE_CURSOR)
        if page * page_size >= total:
            return tuple(items), pages, duplicates, None, None
        if page >= 1000:
            raise LibrusError(ErrorKind.LIMIT)
        if len(items) >= limit or pages == max_pages:
            # At a page boundary, preserve the previous fingerprint for repeated
            # page rejection; only a mid-page cursor claims its current fingerprint.
            return (
                tuple(items),
                pages,
                duplicates,
                ModernMessagesCursor(
                    account,
                    folder,
                    page + 1,
                    0,
                    page_size,
                    total,
                    result.fingerprint,
                    tuple(seen),
                ),
                "item_limit" if len(items) >= limit else "page_limit",
            )
        page, offset = page + 1, 0
    raise AssertionError("Bounded collector must terminate")
