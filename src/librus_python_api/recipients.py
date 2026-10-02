"""Independent bounded named-group and ID-bearing recipient parsing."""

import re

from librus_python_api.config import (
    MESSAGE_INFORMATION_NOTICES,
    RECIPIENT_GROUP_TYPE_PATTERN,
    RECIPIENT_MAX_GROUPS,
    RECIPIENT_MAX_ITEMS,
    RECIPIENT_MAX_LABEL_LENGTH,
    RECIPIENT_MAX_TOTAL_TEXT_LENGTH,
    RECIPIENT_UNSUPPORTED_TYPES,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.markup import rows, text
from librus_python_api.models import (
    Recipient,
    RecipientGroup,
    RecipientGroupReference,
    RecipientReference,
)
from librus_python_api.parsers import page_notices, parse_page


def validate_group(reference: RecipientGroupReference, account: str) -> None:
    if (
        not isinstance(reference, RecipientGroupReference)
        or reference.account != account
        or type(reference.identifier) is not str
        or RECIPIENT_GROUP_TYPE_PATTERN.fullmatch(reference.identifier) is None
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if reference.identifier in RECIPIENT_UNSUPPORTED_TYPES:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def parse_recipient_groups(body: bytes, account: str) -> tuple[RecipientGroup, ...]:
    document = parse_page(body)
    if any(n not in MESSAGE_INFORMATION_NOTICES for n in page_notices(document)):
        raise LibrusError(ErrorKind.PARSE)
    tables = document.xpath(
        '//table[contains(concat(" ",normalize-space(@class)," "),'
        '" message-recipients ")]'
    )
    if len(tables) != 1:
        raise LibrusError(ErrorKind.PARSE)
    result: list[RecipientGroup] = []
    seen: set[str] = set()
    for row in rows(tables[0]):
        parent = row.getparent()
        if parent is None or parent.tag != "tbody":
            continue
        inputs = row.xpath(
            './/input[contains(concat(" ",normalize-space(@class)," "),'
            '" recipiantTypeRadio ")]'
        )
        if len(inputs) != 1:
            raise LibrusError(ErrorKind.PARSE)
        radio = inputs[0]
        identifier = radio.get("value", "")
        if RECIPIENT_GROUP_TYPE_PATTERN.fullmatch(identifier) is None:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if (
            radio.get("type") != "radio"
            or radio.get("id") != "radio_" + identifier
            or identifier in seen
        ):
            raise LibrusError(ErrorKind.PARSE)
        labels = row.xpath(".//label")
        if len(labels) != 1 or labels[0].get("for") != radio.get("id"):
            raise LibrusError(ErrorKind.PARSE)
        label = text(labels[0], RECIPIENT_MAX_LABEL_LENGTH)
        if not label:
            raise LibrusError(ErrorKind.PARSE)
        if len(result) >= RECIPIENT_MAX_GROUPS:
            raise LibrusError(ErrorKind.LIMIT)
        seen.add(identifier)
        result.append(
            RecipientGroup(
                RecipientGroupReference(identifier, account),
                label,
                radio.get("disabled") is None,
                identifier not in RECIPIENT_UNSUPPORTED_TYPES,
            )
        )
    if not result:
        raise LibrusError(ErrorKind.PARSE)
    return tuple(result)


def parse_recipients(
    body: bytes, group: RecipientGroupReference
) -> tuple[Recipient, ...]:
    validate_group(group, group.account)
    document = parse_page(body)
    result: list[Recipient] = []
    seen: set[str] = set()
    total = 0
    labels = list(document.iter("label"))
    controls_by_id = {n.get("id"): n for n in document.iter("input") if n.get("id")}
    if not labels:
        raise LibrusError(ErrorKind.PARSE)
    for label in labels:
        target = label.get("for", "")
        match = re.fullmatch(r"(?:[A-Za-z][A-Za-z0-9]*_)+([0-9]{1,64})", target)
        if match is None:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        identifier = match[1]
        control = controls_by_id.get(target)
        if (
            control is None
            or control.get("type") != "checkbox"
            or control.get("value") != identifier
            or identifier in seen
        ):
            raise LibrusError(ErrorKind.PARSE)
        name = text(label, RECIPIENT_MAX_LABEL_LENGTH)
        if not name:
            raise LibrusError(ErrorKind.PARSE)
        total += len(name)
        if (
            len(result) >= RECIPIENT_MAX_ITEMS
            or total > RECIPIENT_MAX_TOTAL_TEXT_LENGTH
        ):
            raise LibrusError(ErrorKind.LIMIT)
        seen.add(identifier)
        result.append(
            Recipient(
                RecipientReference(identifier, group.account, group.identifier), name
            )
        )
    # The observed response has one ID/value-free select-all checkbox. Every
    # recipient checkbox must instead have a numeric value and a matching label.
    controls = 0
    for node in document.iter("input"):
        if node.get("type") != "checkbox":
            continue
        identifier, value = node.get("id"), node.get("value")
        if identifier is None and value is None:
            continue
        if not identifier or re.fullmatch(r"[0-9]{1,64}", value or "") is None:
            raise LibrusError(ErrorKind.PARSE)
        controls += 1
    if controls != len(result):
        raise LibrusError(ErrorKind.PARSE)
    return tuple(result)
