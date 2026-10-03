"""Pure bounded message content and inert attachment metadata extraction."""

import re

from lxml import html

from librus_python_api.config import (
    MESSAGE_ATTACHMENT_PATH_PREFIX,
    MESSAGE_INFORMATION_NOTICES,
    MESSAGE_MAX_ATTACHMENTS,
    MESSAGE_MAX_CONTENT_LENGTH,
    MESSAGE_MAX_FIELD_LENGTH,
    MESSAGE_MAX_RECEIPT_TEXT_LENGTH,
    MESSAGE_MAX_RECIPIENT_RECEIPTS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.markup import cells, rows, text
from librus_python_api.messages import _timestamp
from librus_python_api.models import (
    MessageAttachment,
    MessageAttachmentReference,
    MessageContentData,
    MessageFolder,
    MessageRecipientReceipt,
    MessageReference,
)
from librus_python_api.parsers import page_notices, parse_page


def validate_reference(reference: MessageReference, account: str) -> None:
    if (
        not isinstance(reference, MessageReference)
        or not isinstance(reference.folder, MessageFolder)
        or reference.account != account
        or type(reference.identifier) is not str
        or re.fullmatch(r"[0-9]{1,64}", reference.identifier) is None
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)


def _recipient_receipts(
    table_rows: list[html.HtmlElement],
) -> tuple[MessageRecipientReceipt, ...]:
    if not 2 <= len(table_rows) <= MESSAGE_MAX_RECIPIENT_RECEIPTS + 1:
        raise LibrusError(
            ErrorKind.LIMIT
            if len(table_rows) > MESSAGE_MAX_RECIPIENT_RECEIPTS + 1
            else ErrorKind.PARSE
        )
    heading = cells(table_rows[0])
    if (
        len(heading) != 1
        or text(heading[0]).rstrip(":") != "Przeczytano"
        or heading[0].get("colspan") != "3"
        or heading[0].get("rowspan", "1") != "1"
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    result = []
    total = 0
    for row in table_rows[1:]:
        columns = cells(row)
        if len(columns) != 2 or any(
            c.tag != "td"
            or c.get("colspan", "1") != "1"
            or c.get("rowspan", "1") != "1"
            or next(c.iterdescendants("table"), None) is not None
            for c in columns
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        recipient, status = [
            text(c, MESSAGE_MAX_FIELD_LENGTH, multiline=True) for c in columns
        ]
        if not recipient or not status:
            raise LibrusError(ErrorKind.PARSE)
        total += len(recipient) + len(status)
        if total > MESSAGE_MAX_RECEIPT_TEXT_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        stamp = None if status == "NIE" else _timestamp(status)
        result.append(MessageRecipientReceipt(recipient, status, stamp))
    return tuple(result)


def _metadata(
    document: html.HtmlElement, folder: MessageFolder
) -> tuple[list[str | None], str | None, tuple[MessageRecipientReceipt, ...]]:
    candidates = [
        t for t in document.iter("table") if t.get("class", "").split() == ["stretch"]
    ]
    main = []
    receipt: str | None = None
    individual: tuple[MessageRecipientReceipt, ...] = ()
    for table in candidates:
        table_rows = list(rows(table))
        first = cells(table_rows[0]) if table_rows else []
        if len(first) == 1 and text(first[0]).rstrip(":") == "Przeczytano":
            if folder is not MessageFolder.SENT or individual or receipt is not None:
                raise LibrusError(ErrorKind.PARSE)
            individual = _recipient_receipts(table_rows)
            continue
        if len(table_rows) == 1:
            columns = cells(table_rows[0])
            if receipt is not None or individual:
                raise LibrusError(ErrorKind.PARSE)
            if (
                len(columns) != 2
                or text(columns[0]).rstrip(":") != "Przeczytano"
                or any(
                    c.get("colspan", "1") != "1" or c.get("rowspan", "1") != "1"
                    for c in columns
                )
            ):
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            receipt = text(columns[1], MESSAGE_MAX_FIELD_LENGTH)
        else:
            main.append(table_rows)
    if len(main) != 1:
        raise LibrusError(ErrorKind.PARSE)
    return _main_metadata(main[0], folder), receipt, individual


def _main_metadata(
    table_rows: list[html.HtmlElement], folder: MessageFolder
) -> list[str | None]:
    short_sent = folder is MessageFolder.SENT and len(table_rows) == 2
    if len(table_rows) != 3 and not short_sent:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    expected: tuple[str, ...] = (
        "Nadawca" if folder is MessageFolder.RECEIVED else "Adresat",
        "Temat",
        "Wysłano",
    )
    if short_sent:
        expected = expected[1:]
    result: list[str | None] = [None] if short_sent else []
    for row, label in zip(table_rows, expected, strict=True):
        columns = cells(row)
        if (
            len(columns) != 2
            or text(columns[0]).rstrip(":") != label
            or any(
                c.get("colspan", "1") != "1" or c.get("rowspan", "1") != "1"
                for c in columns
            )
            or any(next(c.iterdescendants("table"), None) is not None for c in columns)
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        result.append(text(columns[1], MESSAGE_MAX_FIELD_LENGTH, multiline=True))
    if not short_sent and not result[0]:
        raise LibrusError(ErrorKind.PARSE)
    return result


def _attachments(
    document: html.HtmlElement, reference: MessageReference
) -> tuple[MessageAttachment, ...]:
    result: list[MessageAttachment] = []
    seen: set[str] = set()
    for element in document.iter():
        if not isinstance(element.tag, str):
            continue
        if "pobierz_zalacznik" in element.get("href", ""):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        # Markers live in download-icon handlers. They are parsed as data only,
        # never evaluated, requested or exposed as arbitrary authenticated URLs.
        handler = element.get("onclick", "")
        if "pobierz_zalacznik" not in handler:
            continue
        if len(handler) > MESSAGE_MAX_FIELD_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        literals = re.findall(r"(['\"])([^'\"]+)\1", handler.replace(r"\/", "/"))
        targets = [
            re.fullmatch(
                re.escape(MESSAGE_ATTACHMENT_PATH_PREFIX)
                + r"([0-9]{1,64})/([0-9]{1,64})",
                value,
            )
            for _, value in literals
        ]
        matches = [m for m in targets if m is not None]
        if (
            len(matches) != 1
            or handler.count("pobierz_zalacznik") != 1
            or element.tag != "img"
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        message_id, file_id = matches[0].groups()
        if message_id != reference.identifier or file_id in seen:
            raise LibrusError(ErrorKind.PARSE)
        row = next(element.iterancestors("tr"), None)
        columns = cells(row) if row is not None else []
        if not columns:
            raise LibrusError(ErrorKind.PARSE)
        name = text(columns[0], MESSAGE_MAX_FIELD_LENGTH)
        if not name:
            raise LibrusError(ErrorKind.PARSE)
        if len(result) >= MESSAGE_MAX_ATTACHMENTS:
            raise LibrusError(ErrorKind.LIMIT)
        seen.add(file_id)
        result.append(
            MessageAttachment(MessageAttachmentReference(reference, file_id), name)
        )
    return tuple(result)


def parse_message_content(
    body: bytes, reference: MessageReference
) -> MessageContentData:
    validate_reference(reference, reference.account)
    document = parse_page(body)
    if any(n not in MESSAGE_INFORMATION_NOTICES for n in page_notices(document)):
        raise LibrusError(ErrorKind.PARSE)
    metadata, receipt, individual = _metadata(document, reference.folder)
    correspondent, subject, stamp = metadata
    assert subject is not None and stamp is not None
    containers = document.xpath(
        '//*[contains(concat(" ",normalize-space(@class)," "),'
        '" container-message-content ")]'
    )
    if len(containers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    return MessageContentData(
        reference,
        correspondent,
        subject,
        _timestamp(stamp),
        _timestamp(receipt) if receipt is not None else None,
        text(containers[0], MESSAGE_MAX_CONTENT_LENGTH, multiline=True),
        _attachments(document, reference),
        individual,
    )
