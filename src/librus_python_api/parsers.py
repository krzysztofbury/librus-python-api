"""Pure, bounded, independently authored JSON and semantic HTML parsers."""

import json
import math
import re
import typing
from html import unescape
from html.entities import html5
from typing import Any

from lxml import etree, html
from pydantic import BaseModel, ValidationError

from librus_python_api.config import (
    LOGGED_IN_PAGE_MARKER,
    LOGGED_OUT_HEADING,
    PAGE_NOTICES,
    PROFILE_LABELS,
    PROFILE_LUCKY_NUMBER_CLASS,
    PROFILE_LUCKY_NUMBER_DISABLED,
)
from librus_python_api.exceptions import ErrorKind, LibrusError, ParseError
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
        result = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
            parse_float=_finite_float,
        )
    except (ValueError, UnicodeError, RecursionError):
        failed = True
    if failed:
        raise LibrusError(ErrorKind.PARSE)
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError("Non-standard JSON number")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse_identity(body: bytes) -> tuple[Person, Person]:
    owner, student, _ = parse_identity_record(body)
    return owner, student


def parse_identity_record(body: bytes) -> tuple[Person, Person, int | None]:
    """The login owner, the represented student and the account group, if any."""
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
    # Gateway variants omit User.Id but supply its explicit Account.UserId
    # reference. Account.Id remains the login owner, never the represented user.
    student_id = user.Id if user.Id is not None else account.UserId
    if student_id is None or (
        user.Id is not None and account.UserId is not None and user.Id != account.UserId
    ):
        raise LibrusError(ErrorKind.PARSE)
    return (
        Person(account.Id, account.FirstName, account.LastName),
        Person(student_id, user.FirstName, user.LastName),
        account.GroupId,
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


# Browser HTML commonly contains stray closing tags; every libxml2 reports them.
HTML_RECOVERIES = frozenset({"ERR_TAG_NAME_MISMATCH"})
# libxml2 2.14 parses HTML as HTML5 does and reports none of these; the 2.11.9
# that lxml's Windows wheels bundle (#121) reports each one where a browser
# repairs the markup. Accepted only below 2.14, so newer libxml2 is unchanged.
# Seen on live pages: the first four. In the suite's fixtures and message
# bodies under 2.11: the rest. A misplaced html, head or body tag, which 2.14
# rejects too, is accepted only there.
HTML_RECOVERIES_BEFORE_2_14 = HTML_RECOVERIES | frozenset(
    {
        "ERR_ATTRIBUTE_REDEFINED",  # a repeated attribute; the first one is kept
        "ERR_NAME_REQUIRED",  # a stray character where a name belongs
        "ERR_ENTITYREF_SEMICOL_MISSING",  # "&nbsp" without its ";"
        "HTML_UNKNOWN_TAG",  # an element HTML 4 does not list, such as nobr
        "ERR_INVALID_CHAR",  # a control character, dropped; 2.14 keeps it
        "ERR_SPACE_REQUIRED",  # "<?" without an XML processing instruction
        "ERR_GT_REQUIRED",  # a start tag the document ends inside
        "ERR_COMMENT_ABRUPTLY_ENDED",  # "<!-->"
        "HTML_INCORRECTLY_OPENED_COMMENT",  # "<!" that starts no comment
        "HTML_STRUCURE_ERROR",  # a misplaced DOCTYPE, html, head or body tag
    }
)
_LEGACY_REFERENCES = frozenset(name for name in html5 if not name.endswith(";"))
# A named reference without its ";", which libxml2 2.11 keeps as text.
_BARE_REFERENCE = re.compile(r"&[A-Za-z][A-Za-z0-9]*+(?!;)")
# An escaped "&" before a name; parsed, it looks like a bare reference.
_ESCAPED_REFERENCE = re.compile(
    r"&(?:amp;|#0*38;|#[xX]0*26;)([A-Za-z][A-Za-z0-9]*+)(?!;)"
)
_RAW_TEXT_ELEMENTS = frozenset({"script", "style"})


def _legacy(name: str) -> bool:
    """Whether HTML5 decodes "&" + name without ";": a legacy name prefixes it."""
    return any(name[:end] in _LEGACY_REFERENCES for end in range(len(name), 1, -1))


def _decode_bare_references(source: str, document: html.HtmlElement) -> None:
    """Decode text the way libxml2 2.14 and browsers do, where 2.11 did not.

    Synergia templates write "&nbsp" without ";" (#121: every timetable entry).
    HTML5 decodes such a reference in text when a legacy name starts it, as
    `html.unescape` does; libxml2 2.11 leaves it as text. Once parsed, an
    escaped "&amp;para" looks the same as a bare "&para", so a document with
    both fails instead of guessing; no live Synergia page had one. Only text
    and tails change: the observed attribute values parse alike.
    """
    if any(_legacy(match.group(1)) for match in _ESCAPED_REFERENCE.finditer(source)):
        raise LibrusError(ErrorKind.PARSE)

    def decode(value: str | None) -> str | None:
        if not value or "&" not in value:
            return value
        return _BARE_REFERENCE.sub(lambda match: unescape(match.group()), value)

    for node in document.iter():
        if isinstance(node.tag, str) and node.tag not in _RAW_TEXT_ELEMENTS:
            node.text = decode(node.text)
        node.tail = decode(node.tail)


def parse_html_document(
    body: bytes, *, repeatable_id: str | None = None
) -> html.HtmlElement:
    failed = False
    document: html.HtmlElement | None = None
    parser = html.HTMLParser(no_network=True, recover=True, huge_tree=False)
    try:
        text = body.decode("utf-8")
        document = html.document_fromstring(
            text,
            parser=parser,
        )
    except (UnicodeError, etree.LxmlError, ValueError):
        failed = True
    # Accept only the repairs a browser makes too; semantic tables, spans, IDs
    # and bounds still validate independently. Do not blanket-ignore arbitrary
    # parser errors, such as an exhausted allocation.
    recoveries = (
        HTML_RECOVERIES
        if etree.LIBXML_VERSION >= (2, 14)
        else HTML_RECOVERIES_BEFORE_2_14
    )
    if failed or any(
        error.type_name not in recoveries
        and not (
            repeatable_id is not None
            and error.type_name == "DTD_ID_REDEFINED"
            and error.message == f"ID {repeatable_id} already defined"
        )
        for error in parser.error_log
    ):
        raise LibrusError(ErrorKind.PARSE)
    assert document is not None
    if etree.LIBXML_VERSION < (2, 14) and any(
        error.type_name == "ERR_ENTITYREF_SEMICOL_MISSING" for error in parser.error_log
    ):
        _decode_bare_references(text, document)
    count = 0
    pending = [(document, 0)]
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > 8192 or depth > 32:
            raise LibrusError(ErrorKind.LIMIT)
        pending.extend((child, depth + 1) for child in node)
    return document


def page_notices(document: html.HtmlElement) -> tuple[str, ...]:
    """Texts of page-level information boxes, which replace requested content."""
    nodes = document.xpath(
        '//div[contains(concat(" ",normalize-space(@class)," ")," warning-content ")]'
    )
    return tuple(" ".join(node.text_content().split()) for node in nodes)


def parse_page(body: bytes, *, repeatable_id: str | None = None) -> html.HtmlElement:
    """Parse a whole Synergia page and raise for a recognized notice.

    Notices such as a view disabled by the school administrator are typed
    outcomes, never parse failures or empty collections.
    """
    document = parse_html_document(body, repeatable_id=repeatable_id)
    for notice in page_notices(document):
        kind = PAGE_NOTICES.get(notice)
        if kind is not None:
            raise LibrusError(kind)
    return document


def _wire_names(model: type[BaseModel], seen: set[type[BaseModel]]) -> set[str]:
    """Every field name of a wire model and the models nested in it."""
    if model in seen:
        return set()
    seen.add(model)
    names: set[str] = set()
    for name, field in model.model_fields.items():
        names.add(name)
        if field.alias:
            names.add(field.alias)
        pending: list[object] = [field.annotation]
        while pending:
            kind = pending.pop()
            if isinstance(kind, type) and issubclass(kind, BaseModel):
                names |= _wire_names(kind, seen)
            pending.extend(typing.get_args(kind))
    return names


def wire_failure(error: ValidationError, model: type[BaseModel]) -> str:
    """Where a wire model rejected a body: field path and rule, never a value.

    A path part is shown only when it is a list index or a field name of
    `model`; anything else (such as a dict key from the body) is `?`.
    """
    names = _wire_names(model, set())
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    shown: list[str] = []
    for item in errors[:3]:
        path = ""
        for part in item["loc"]:
            if type(part) is int:
                path += f"[{part}]"
            else:
                path += ("." if path else "") + (part if part in names else "?")
        shown.append(f"{path or '(body)'} {item['type']}")
    more = f"; {len(errors)} errors" if len(errors) > 3 else ""
    return "; ".join(shown) + more


def validate_wire[M: BaseModel](model: type[M], data: object) -> M:
    """`model` validated from decoded JSON; PARSE naming the failing field."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        failure = wire_failure(error, model)
    parse = ParseError(ErrorKind.PARSE)
    parse._wire_failure = failure
    raise parse


def is_logged_out_page(body: bytes) -> bool:
    """Synergia's page for a session it no longer knows; never raises."""
    if LOGGED_OUT_HEADING.encode() not in body:
        return False
    try:
        parser = html.HTMLParser(no_network=True, recover=True, huge_tree=False)
        document = html.document_fromstring(body.decode("utf-8"), parser=parser)
    except (UnicodeError, etree.LxmlError, ValueError):
        return False
    if document.get_element_by_id(LOGGED_IN_PAGE_MARKER, None) is not None:
        return False
    headings = [
        " ".join(h.text_content().split()) for h in document.iter("h1", "h2", "h3")
    ]
    return headings == [LOGGED_OUT_HEADING]


def parse_profile(body: bytes) -> ProfileFields:
    document = parse_page(body)
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
    markers = document.xpath(
        '//span[contains(concat(" ",normalize-space(@class)," "),$token)]',
        token=f" {PROFILE_LUCKY_NUMBER_CLASS} ",
    )
    if not markers:
        lucky = LuckyNumber(Availability.UNAVAILABLE)
    elif len(markers) == 1:
        value = " ".join(markers[0].text_content().split())
        if value in ("", PROFILE_LUCKY_NUMBER_DISABLED):
            lucky = LuckyNumber(Availability.UNAVAILABLE)
        elif re.fullmatch(r"[0-9]{1,4}", value):
            # No evidenced civil date in this marker. Never fabricate today's date.
            lucky = LuckyNumber(Availability.AVAILABLE, int(value))
        else:
            raise LibrusError(ErrorKind.PARSE)
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
