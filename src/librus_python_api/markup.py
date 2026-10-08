"""Bounded HTML reading helpers shared by every Synergia page parser."""

import re
from collections.abc import Iterator
from datetime import date
from urllib.parse import urlsplit

from lxml import etree, html

from librus_python_api.config import (
    ATTENDANCE_DETAIL_PATH_PREFIX,
    GRADE_MAX_COLUMNS,
    GRADE_MAX_METADATA_FIELDS,
    GRADE_MAX_METADATA_LENGTH,
    UPSTREAM_ORIGINS,
    WEEKDAY_LABELS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.parsers import parse_html_document

FIELD_LENGTH = 1024
_ACTIVE_CONTENT = frozenset({"script", "style", "iframe", "object", "embed", "form"})
_BLOCKS = frozenset({"br", "p", "div", "li"})


def text(
    element: html.HtmlElement, limit: int = FIELD_LENGTH, *, multiline: bool = False
) -> str:
    """Rendered text with block boundaries as line breaks; never truncated.

    Active content inside a data cell is an unsupported layout, not text.
    """
    parts: list[str] = []
    for event, node in etree.iterwalk(element, events=("start", "end", "comment")):
        if node.tag in _ACTIVE_CONTENT:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if node.tag in _BLOCKS:
            parts.append("\n")
        if event == "start" and isinstance(node.tag, str) and node.text:
            parts.append(re.sub(r"\s+", " ", node.text))
        if event in ("end", "comment") and node is not element and node.tail:
            parts.append(re.sub(r"\s+", " ", node.tail))
    rendered = "".join(parts)
    value = (
        "\n".join(
            line for raw in rendered.splitlines() if (line := " ".join(raw.split()))
        )
        if multiline
        else " ".join(rendered.split())
    )
    if len(value) > limit:
        raise LibrusError(ErrorKind.LIMIT)
    return value


def cells(row: html.HtmlElement) -> list[html.HtmlElement]:
    return [item for item in row if item.tag in ("td", "th")]


def rows(table: html.HtmlElement) -> Iterator[html.HtmlElement]:
    """Rows of this table only, never rows of a nested table."""
    for row in table.iter("tr"):
        if next(row.iterancestors("table"), None) is table:
            yield row


def in_header(row: html.HtmlElement) -> bool:
    return next(row.iterancestors("thead"), None) is not None


def colspan(cell: html.HtmlElement) -> int:
    value = cell.get("colspan", "1")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", value):
        raise LibrusError(ErrorKind.PARSE)
    span = int(value)
    if span > GRADE_MAX_COLUMNS:
        raise LibrusError(ErrorKind.LIMIT)
    if cell.get("rowspan", "1") != "1":
        raise LibrusError(ErrorKind.PARSE)
    return span


def tooltip_fields(element: html.HtmlElement) -> dict[str, str]:
    """Parse a 'Label: value<br>' title attribute into unique labelled fields."""
    title = element.get("title", "")
    if len(title) > GRADE_MAX_METADATA_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    result: dict[str, str] = {}
    chunks = re.split(r"<br\s*/?>|\n", title, flags=re.I)
    if len(chunks) > GRADE_MAX_METADATA_FIELDS:
        raise LibrusError(ErrorKind.LIMIT)
    for chunk in chunks:
        if not chunk.strip():
            continue
        # Tooltips are HTML inside an attribute; parse markup only where present.
        rendered = (
            text(parse_html_document(chunk.encode()))
            if "<" in chunk
            else " ".join(chunk.split())
        )
        key, separator, value = rendered.partition(":")
        key, value = key.strip(), value.strip()
        if not separator or not key or key in result:
            raise LibrusError(ErrorKind.PARSE)
        result[key] = value
    return result


def civil_date(value: str | None) -> date:
    """An ISO date, optionally followed by its weekday label in parentheses."""
    match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2})(?: \(([^()]+)\))?", value or "")
    if match is None or (match[2] is not None and match[2] not in WEEKDAY_LABELS):
        raise LibrusError(ErrorKind.PARSE)
    try:
        return date.fromisoformat(match[1])
    except ValueError:
        pass
    raise LibrusError(ErrorKind.PARSE)


def attendance_detail_id(element: html.HtmlElement) -> str | None:
    """The numeric ID of an inert attendance-detail popup link, if any."""
    script = element.get("onclick", "")
    if len(script) > GRADE_MAX_METADATA_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    match = re.fullmatch(
        r"\s*otworz_w_nowym_oknie\(\s*(['\"])([^'\"\\\s]+)\1"
        r"""(?:\s*,\s*(?:'[^'\\\r\n]*'|"[^"\\\r\n]*"|[0-9]{1,6})){1,4}"""
        r"\s*\)\s*;?\s*",
        script,
    )
    if match is None:
        return None
    return detail_id(match[2], ATTENDANCE_DETAIL_PATH_PREFIX)


def detail_id(link: str | None, prefix: str) -> str | None:
    """The numeric ID of a relative or same-origin Synergia detail link.

    Recognition only: the link is never followed. Queries, fragments, other
    origins, credentials and non-digit IDs are not detail links.
    """
    if link is None or len(link) > GRADE_MAX_METADATA_LENGTH:
        return None
    try:
        target = urlsplit(link)
    except ValueError:
        return None
    if target.query or target.fragment or target.username or target.password:
        return None
    if target.scheme or target.netloc:
        expected = urlsplit(UPSTREAM_ORIGINS["synergia"])
        if (target.scheme, target.netloc) != (expected.scheme, expected.netloc):
            return None
    if not target.path.startswith(prefix):
        return None
    identifier = target.path[len(prefix) :]
    return identifier if re.fullmatch(r"[0-9]{1,64}", identifier) else None
