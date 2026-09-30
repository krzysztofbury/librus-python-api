"""Pure, bounded, independently authored JSON and semantic HTML parsers."""

import json
import re
from typing import Any

from lxml import etree, html
from pydantic import ValidationError

from librus_python_api.config import PROFILE_LABELS
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    Availability,
    LuckyNumber,
    Person,
    ProfileFields,
    _EnvelopeWire,
)


def decode_json(body: bytes) -> Any:
    # Bound nesting before the decoder allocates recursive containers. Strings
    # and escaped quotes do not count as structure. Bytes were bounded by caller.
    depth = 0
    quoted = escaped = False
    for value in body:
        if quoted:
            if escaped:
                escaped = False
            elif value == 92:
                escaped = True
            elif value == 34:
                quoted = False
        elif value == 34:
            quoted = True
        elif value in (91, 123):
            depth += 1
            if depth > 32:
                raise LibrusError(ErrorKind.LIMIT)
        elif value in (93, 125):
            depth -= 1
    failed = False
    result: Any = None
    try:
        result = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        failed = True
    if failed:
        raise LibrusError(ErrorKind.PARSE)
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse_identity(body: bytes) -> tuple[Person, Person]:
    data = decode_json(body)
    failed = False
    envelope: _EnvelopeWire | None = None
    try:
        envelope = _EnvelopeWire.model_validate(data)
    except ValidationError:
        failed = True
    if failed:
        raise LibrusError(ErrorKind.PARSE)
    assert envelope is not None
    account, user = envelope.Me.Account, envelope.Me.User
    return (
        Person(account.Id, account.FirstName, account.LastName),
        Person(user.Id, user.FirstName, user.LastName),
    )


def parse_login(body: bytes) -> str:
    data = decode_json(body)
    if not isinstance(data, dict):
        raise LibrusError(ErrorKind.PARSE)
    if any(data.get(key) for key in ("captcha", "twoFactorRequired", "requiresAction")):
        raise LibrusError(ErrorKind.ACCOUNT_ACTION_REQUIRED)
    if data.get("status") == "error":
        raise LibrusError(ErrorKind.CREDENTIALS_REJECTED)
    location = data.get("goTo")
    if data.get("status") != "ok" or not isinstance(location, str) or not location:
        raise LibrusError(ErrorKind.ACCOUNT_ACTION_REQUIRED)
    if len(location) > 4096:
        raise LibrusError(ErrorKind.LIMIT)
    return location


def parse_html_document(body: bytes) -> html.HtmlElement:
    failed = False
    document: html.HtmlElement | None = None
    try:
        text = body.decode("utf-8")
        document = html.document_fromstring(
            text,
            parser=html.HTMLParser(no_network=True, recover=False, huge_tree=False),
        )
    except (UnicodeError, etree.LxmlError, ValueError):
        failed = True
    if failed:
        raise LibrusError(ErrorKind.PARSE)
    assert document is not None
    count = 0
    pending = [(document, 0)]
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > 8192 or depth > 32:
            raise LibrusError(ErrorKind.LIMIT)
        pending.extend((child, depth + 1) for child in node)
    return document


def parse_profile(body: bytes) -> ProfileFields:
    document = parse_html_document(body)
    required = {"name", "class_name", "register_number", "tutor", "school"}
    candidates: list[dict[str, str]] = []
    for table in document.iter("table"):
        fields: dict[str, str] = {}
        for row in table.iter("tr"):
            # Do not inherit rows of a nested table into its parent.
            if next(row.iterancestors("table"), None) is not table:
                continue
            cells = [child for child in row if child.tag in ("td", "th")]
            if len(cells) != 2:
                continue
            label = " ".join(cells[0].text_content().split()).rstrip(":")
            key = PROFILE_LABELS.get(label)
            if key is None:
                continue
            if key in fields or any(
                c.get("rowspan", "1") != "1" or c.get("colspan", "1") != "1"
                for c in cells
            ):
                raise LibrusError(ErrorKind.PARSE)
            value = " ".join(cells[1].text_content().split())
            if not value or len(value) > 1024:
                raise LibrusError(ErrorKind.PARSE)
            fields[key] = value
        if fields.keys() == required:
            candidates.append(fields)
    if len(candidates) != 1:
        raise LibrusError(ErrorKind.PARSE)
    if not re.fullmatch(r"[0-9]{1,4}", candidates[0]["register_number"]):
        raise LibrusError(ErrorKind.PARSE)
    markers = document.xpath('//*[@id="luckyNumber"]')
    if not markers:
        lucky = LuckyNumber(Availability.UNAVAILABLE)
    elif len(markers) == 1:
        value = " ".join(markers[0].text_content().split())
        if not re.fullmatch(r"[0-9]{1,4}", value):
            raise LibrusError(ErrorKind.PARSE)
        # No evidenced civil date in this marker. Never fabricate today's date.
        lucky = LuckyNumber(Availability.AVAILABLE, int(value))
    else:
        raise LibrusError(ErrorKind.PARSE)
    fields = candidates[0]
    return ProfileFields(
        fields["name"],
        fields["class_name"],
        int(fields["register_number"]),
        fields["tutor"],
        fields["school"],
        lucky,
    )
