"""Bounded modern mailbox parsing and continuation, with distinct backend references."""

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from librus_python_api.config import (
    MESSAGE_MAX_ATTACHMENTS,
    MESSAGE_MAX_BATCH_ITEMS,
    MESSAGE_MAX_BATCH_PAGES,
    MESSAGE_MAX_CURSOR_IDS,
    MESSAGE_MAX_FIELD_LENGTH,
    MESSAGE_MAX_TOTAL_TEXT_LENGTH,
    MODERN_MAX_LABEL,
    MODERN_MAX_RECIPIENTS,
    MODERN_MAX_UNREAD_COUNT,
    MODERN_UNREAD_COUNT_FIELDS,
    modern_mailbox_query,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    MessageFolder,
    ModernCorrespondent,
    ModernCorrespondentReference,
    ModernMessageAttachment,
    ModernMessageAttachmentReference,
    ModernMessageRecipientReceipt,
    ModernMessageReference,
    ModernMessagesCursor,
    ModernMessagesPage,
    ModernMessageSummary,
    ModernUnreadFolders,
)
from librus_python_api.modern_body import render_body
from librus_python_api.parsers import decode_json

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
        or type(reference.archived) is not bool
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


def _summary(
    data: Any, folder: MessageFolder, account: str, archived: bool
) -> ModernMessageSummary:
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
        ModernMessageReference(
            folder, identifier(data.get("messageId")), account, archived
        ),
        name,
        subject,
        _date(stamp),
        stamp,
        read_at,
        read_at is None if folder is MessageFolder.RECEIVED else None,
        has_attachment,
    )


def parse_page(
    body: bytes,
    folder: MessageFolder,
    page: int,
    page_size: int,
    account: str,
    archived: bool = False,
) -> tuple[tuple[ModernMessageSummary, ...], int, str, bool | None]:
    modern_mailbox_query(folder, page, page_size)
    data = decode_json(body)
    if not isinstance(data, dict) or not {"data", "total"} <= set(data):
        raise LibrusError(ErrorKind.PARSE)
    in_progress = data.get("archivingInProgress", False)
    if type(in_progress) is not bool:
        raise LibrusError(ErrorKind.PARSE)
    # Live archive pages report true while listing normally; it is a status
    # flag there. The current mailbox has never shown it.
    if in_progress and not archived:
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
    items = tuple(_summary(item, folder, account, archived) for item in entries)
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
    return items, total, fingerprint, in_progress if archived else None


@dataclass(frozen=True, slots=True, repr=False)
class ParsedContent:
    summary: ModernMessageSummary
    text: str
    attachments: tuple[ModernMessageAttachment, ...]
    receipts: tuple[ModernMessageRecipientReceipt, ...]
    recipient_count: int | None
    read_count: int | None
    receipt_source: Literal["receivers", "individualRecipients"] | None
    archived: bool
    withdrawn: bool
    original_subject: str | None
    original_text: str | None


def _flag(value: Any) -> bool:
    if type(value) not in (bool, int, str) or value not in (
        False,
        True,
        0,
        1,
        "0",
        "1",
    ):
        raise LibrusError(ErrorKind.PARSE)
    return value in (True, 1, "1")


def _receipts(
    content: dict[str, Any], folder: MessageFolder
) -> tuple[
    tuple[ModernMessageRecipientReceipt, ...],
    int | None,
    int | None,
    Literal["receivers", "individualRecipients"] | None,
]:
    if folder is MessageFolder.RECEIVED:
        return (), None, None, None
    counts = []
    for key in ("receiversCount", "readedCount"):
        value = content.get(key)
        if value is not None and (
            type(value) is not int or not 0 <= value <= MAX_TOTAL_MESSAGES
        ):
            raise LibrusError(ErrorKind.PARSE)
        counts.append(value)
    total, read_count = counts
    if total is not None and read_count is not None and read_count > total:
        raise LibrusError(ErrorKind.PARSE)
    source: Literal["receivers", "individualRecipients"] | None = None
    if (
        "individualRecipients" in content
        and content["individualRecipients"] is not None
    ):
        source = "individualRecipients"
    elif "receivers" in content:
        source = "receivers"
    if source is None:
        return (), total, read_count, None
    rows = content[source]
    if not isinstance(rows, list):
        raise LibrusError(ErrorKind.PARSE)
    if len(rows) > MESSAGE_MAX_BATCH_ITEMS:
        raise LibrusError(ErrorKind.LIMIT)
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise LibrusError(ErrorKind.PARSE)
        receiver_id = identifier(_string(row.get("receiverId")))
        if receiver_id in seen:
            raise LibrusError(ErrorKind.PARSE)
        seen.add(receiver_id)
        cc, bcc = row.get("isCc"), row.get("isBcc")
        if (
            type(cc) is not str
            or type(bcc) is not str
            or cc not in ("0", "1")
            or bcc not in ("0", "1")
            or cc == bcc == "1"
        ):
            raise LibrusError(ErrorKind.PARSE)
        stamp = row.get("readed")
        read_at = None if stamp in (None, "") else _date(stamp)
        name = _string(row.get("name"))
        if not name.strip():
            raise LibrusError(ErrorKind.PARSE)
        result.append(
            ModernMessageRecipientReceipt(
                receiver_id,
                name,
                "bcc" if bcc == "1" else "cc" if cc == "1" else "to",
                read_at is not None if "readed" in row else None,
                read_at,
            )
        )
    if (
        sum(len(r.name) + len(r.recipient_id) for r in result)
        > MESSAGE_MAX_TOTAL_TEXT_LENGTH
    ):
        raise LibrusError(ErrorKind.LIMIT)
    return tuple(result), total, read_count, source


def parse_content(body: bytes, reference: ModernMessageReference) -> ParsedContent:
    data = decode_json(body)
    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        raise LibrusError(ErrorKind.PARSE)
    content = data["data"]
    archived = _flag(content.get("archive", False))
    withdrawn = _flag(content.get("isMessageWithdrawn", False))
    entries = content.get("attachments")
    if not isinstance(entries, list) or len(entries) > MESSAGE_MAX_ATTACHMENTS:
        raise LibrusError(ErrorKind.PARSE)
    # Detail responses do not carry the mailbox's isAnyFileAttached field.
    has_attachment = content.get("isAnyFileAttached", bool(entries))
    if type(has_attachment) is not bool or has_attachment != bool(entries):
        raise LibrusError(ErrorKind.PARSE)
    summary = _summary(
        content | {"isAnyFileAttached": has_attachment},
        reference.folder,
        reference.account,
        reference.archived,
    )
    if summary.reference != reference:
        raise LibrusError(ErrorKind.PARSE)
    rendered = render_body(content.get("Message"))
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
                ModernMessageAttachmentReference(reference, file_id, archived), name
            )
        )
    receipts, total, read_count, source = _receipts(content, reference.folder)
    original = content.get("originalMessage")
    original_text = None if original in (None, "") else render_body(original)
    original_subject = (
        None if original_text is None else _string(content.get("originalTopic"))
    )
    return ParsedContent(
        summary,
        rendered,
        tuple(attachments),
        receipts,
        total,
        read_count,
        source,
        archived,
        withdrawn,
        original_subject,
        original_text,
    )


def validate_selection(
    folder: MessageFolder,
    cursor: ModernMessagesCursor | None,
    page_size: int,
    max_pages: int,
    limit: int,
    account: str,
    archived: bool = False,
    correspondent: str | None = None,
    unread_only: bool = False,
) -> None:
    modern_mailbox_query(
        folder, 1, page_size, correspondent=correspondent, unread_only=unread_only
    )
    if type(archived) is not bool:
        raise LibrusError(ErrorKind.INVALID_INPUT)
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
        or cursor.archived is not archived
        or cursor.correspondent != correspondent
        or cursor.unread_only is not unread_only
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
    archived: bool = False,
    correspondent: str | None = None,
    unread_only: bool = False,
) -> tuple[
    tuple[ModernMessageSummary, ...],
    int,
    int,
    ModernMessagesCursor | None,
    Literal["item_limit", "page_limit"] | None,
]:
    validate_selection(
        folder,
        cursor,
        page_size,
        max_pages,
        limit,
        account,
        archived,
        correspondent,
        unread_only,
    )
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
                        archived,
                        correspondent,
                        unread_only,
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
                    archived,
                    correspondent,
                    unread_only,
                ),
                "item_limit" if len(items) >= limit else "page_limit",
            )
        page, offset = page + 1, 0
    raise AssertionError("Bounded collector must terminate")


def _unread_folders(data: dict[str, Any], prefix: str) -> ModernUnreadFolders:
    values = []
    for name in MODERN_UNREAD_COUNT_FIELDS:
        key = prefix + name[0].upper() + name[1:] if prefix else name
        value = data.get(key)
        if type(value) is not int or value < 0:
            raise LibrusError(ErrorKind.PARSE)
        if value > MODERN_MAX_UNREAD_COUNT:
            raise LibrusError(ErrorKind.LIMIT)
        values.append(value)
    return ModernUnreadFolders(*values)


def parse_unread_counts(
    body: bytes,
) -> tuple[ModernUnreadFolders, ModernUnreadFolders]:
    """Current and archive counters; unknown extra counters stay inert."""
    data = decode_json(body)
    counts = data.get("data") if isinstance(data, dict) else None
    if not isinstance(counts, dict):
        raise LibrusError(ErrorKind.PARSE)
    return _unread_folders(counts, ""), _unread_folders(counts, "archive")


def validate_correspondent(
    reference: ModernCorrespondentReference | None, folder: MessageFolder, account: str
) -> str | None:
    """The filter value for a correspondent listed for this folder and login."""
    if reference is None:
        return None
    if (
        not isinstance(reference, ModernCorrespondentReference)
        or reference.folder is not folder
        or reference.account != account
        or type(reference.identifier) is not str
        or re.fullmatch(r"[0-9]{1,64}", reference.identifier) is None
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return reference.identifier


def _name(value: Any) -> str:
    if type(value) is not str or len(value) > MODERN_MAX_LABEL or "\x00" in value:
        raise LibrusError(ErrorKind.PARSE)
    return value


def parse_correspondents(
    body: bytes, folder: MessageFolder, account: str
) -> tuple[ModernCorrespondent, ...]:
    """People the folder's messages came from (received) or went to (sent)."""
    role = "sender" if folder is MessageFolder.RECEIVED else "receiver"
    data = decode_json(body)
    entries = data.get("data") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise LibrusError(ErrorKind.PARSE)
    if len(entries) > MODERN_MAX_RECIPIENTS:
        raise LibrusError(ErrorKind.LIMIT)
    items = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise LibrusError(ErrorKind.PARSE)
        first = _name(entry.get(f"{role}FirstName"))
        last = _name(entry.get(f"{role}LastName"))
        # Institutional senders can carry a single name part; never both empty.
        if not (first.strip() or last.strip()):
            raise LibrusError(ErrorKind.PARSE)
        reference = ModernCorrespondentReference(
            folder, identifier(entry.get(f"{role}Id")), account
        )
        items.append(ModernCorrespondent(reference, first, last))
    if len({item.reference.identifier for item in items}) != len(items):
        raise LibrusError(ErrorKind.PARSE)
    return tuple(items)
