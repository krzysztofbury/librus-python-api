"""Independent bounded named-group and ID-bearing recipient parsing."""

import re

from lxml import html

from librus_python_api.config import (
    MESSAGE_INFORMATION_NOTICES,
    RECIPIENT_CLASS_UNAVAILABLE_NOTICE,
    RECIPIENT_GROUP_TYPE_PATTERN,
    RECIPIENT_MAX_GROUPS,
    RECIPIENT_MAX_ITEMS,
    RECIPIENT_MAX_LABEL_LENGTH,
    RECIPIENT_MAX_TOTAL_TEXT_LENGTH,
    RECIPIENT_SELECTION_PROMPT,
    RECIPIENT_UNSUPPORTED_TYPES,
    recipient_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.markup import rows, text
from librus_python_api.models import (
    Recipient,
    RecipientGroup,
    RecipientGroupChoice,
    RecipientGroupReference,
    RecipientReference,
)
from librus_python_api.parsers import page_notices, parse_page


def validate_group(
    reference: RecipientGroupReference, account: str, *, choices: bool = False
) -> None:
    if (
        not isinstance(reference, RecipientGroupReference)
        or reference.account != account
        or type(reference.identifier) is not str
        or RECIPIENT_GROUP_TYPE_PATTERN.fullmatch(reference.identifier) is None
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    recipient_form(reference.identifier, selection_id=reference.selection_id)
    if choices and (reference.identifier != "grupa" or reference.selection_id != "0"):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if (
        not choices
        and reference.identifier in RECIPIENT_UNSUPPORTED_TYPES
        and reference.selection_id == "0"
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _unavailable(document: html.HtmlElement) -> None:
    # Localized UI text is a capability failure, not proof of zero recipients.
    for marker in document.xpath('//p[@class="msgEmptyTable"]'):
        if text(marker) == RECIPIENT_CLASS_UNAVAILABLE_NOTICE:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _recipient_document(body: bytes) -> html.HtmlElement:
    document = parse_page(body)
    _unavailable(document)
    if any(n not in MESSAGE_INFORMATION_NOTICES for n in page_notices(document)):
        raise LibrusError(ErrorKind.PARSE)
    return document


def parse_recipient_group_choices(
    body: bytes, group: RecipientGroupReference
) -> tuple[RecipientGroupChoice, ...]:
    validate_group(group, group.account, choices=True)
    document = _recipient_document(body)
    selectors = document.xpath('//select[@name="idGrupy" and @id="idGrupy"]')
    if (
        len(selectors) != 1
        or len(document.xpath("//select")) != 1
        or document.xpath('//label|//input[@type="checkbox"]')
    ):
        raise LibrusError(ErrorKind.PARSE)
    markers = document.xpath('//p[@class="msgEmptyTable"]')
    if len(markers) != 1 or text(markers[0]) != RECIPIENT_SELECTION_PROMPT:
        raise LibrusError(ErrorKind.PARSE)
    options = list(selectors[0])
    if not options or len(options) > RECIPIENT_MAX_ITEMS + 1:
        raise LibrusError(ErrorKind.LIMIT if options else ErrorKind.PARSE)
    result = []
    seen = set()
    total = 0
    for option in options:
        if option.tag != "option":
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        identifier = option.get("value", "")
        if re.fullmatch(r"0|[1-9][0-9]{0,63}", identifier) is None:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if identifier in seen:
            raise LibrusError(ErrorKind.PARSE)
        seen.add(identifier)
        label = text(option, RECIPIENT_MAX_LABEL_LENGTH)
        if identifier == "0":
            if label:
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            continue
        if not label:
            raise LibrusError(ErrorKind.PARSE)
        total += len(label)
        if total > RECIPIENT_MAX_TOTAL_TEXT_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        result.append(
            RecipientGroupChoice(
                RecipientGroupReference("grupa", group.account, identifier),
                label,
                option.get("disabled") is None and selectors[0].get("disabled") is None,
            )
        )
    if "0" not in seen:
        raise LibrusError(ErrorKind.PARSE)
    return tuple(result)


def parse_recipient_groups(body: bytes, account: str) -> tuple[RecipientGroup, ...]:
    document = _recipient_document(body)
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
    document = _recipient_document(body)
    if document.xpath('//p[@class="msgEmptyTable"]'):
        # Explicit class-unavailable is handled above; unknown empty/prompt
        # states must not silently coexist with a successful recipient list.
        raise LibrusError(ErrorKind.PARSE)
    result: list[Recipient] = []
    seen: set[str] = set()
    total = 0
    labels = list(document.iter("label"))
    controls_by_id = {n.get("id"): n for n in document.iter("input") if n.get("id")}
    if not labels:
        if group.identifier == "sadmin":
            return _anonymous_recipient(document, group)
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
                RecipientReference(
                    identifier, group.account, group.identifier, group.selection_id
                ),
                name,
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


def _anonymous_recipient(
    document: html.HtmlElement, group: RecipientGroupReference
) -> tuple[Recipient, ...]:
    controls = list(document.iter("input"))
    if (
        len(controls) != 2
        or [c.get("name") for c in controls] != ["DoKogo", "DoKogo_hid[]"]
        or any(
            c.get("type", "").casefold() != "hidden" or c.get("id") for c in controls
        )
        or any(
            isinstance(n.tag, str)
            and n.tag not in {"html", "head", "body", "input", "script"}
            for n in document.iter()
        )
        # Page-level scripts are inert and not display labels. They are never
        # executed; only the exact hidden control pair defines this target.
        or "".join(document.xpath("//text()[not(ancestor::script)]")).strip()
    ):
        raise LibrusError(ErrorKind.PARSE)
    identifier = controls[0].get("value", "")
    if (
        re.fullmatch(r"[0-9]{1,64}", identifier) is None
        or controls[1].get("value") != identifier
    ):
        raise LibrusError(ErrorKind.PARSE)
    return (
        Recipient(
            RecipientReference(
                identifier, group.account, group.identifier, group.selection_id
            ),
            None,
        ),
    )
