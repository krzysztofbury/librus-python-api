"""The grades page's formative-assessment table ("Oceny kształtujące").

Authored from an owner-authorized structural observation; fixtures are
synthetic. The table sits on the page `grades()` already reads, so no request
is added. Its subject may be the pseudo-subject "KARTA SPOSTRZEŻEŃ". Unknown
markup is unsupported; contradictions inside the known layout are parse errors.
"""

import re
from collections.abc import Callable
from typing import Literal, NoReturn, cast

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    FORMATIVE_DETAIL_PATH_PREFIX,
    FORMATIVE_HEADERS,
    FORMATIVE_MAX_TEXT_LENGTH,
    FORMATIVE_TEMPLATE_ID,
    GRADE_MAX_RECORDS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import FormativeGrade

_SPAN = re.compile(r"[1-9][0-9]{0,5}")


def _fail(kind: ErrorKind) -> NoReturn:
    raise LibrusError(kind)


def is_formative_table(table: html.HtmlElement) -> bool:
    # Cheap structural gates first: other tables' header text is never read.
    if not {"stretch", "decorated"} <= set(table.get("class", "").split()):
        return False
    heads = [row for row in markup.rows(table) if markup.in_header(row)]
    if len(heads) != 1:
        return False
    cells = markup.cells(heads[0])
    return len(cells) == len(FORMATIVE_HEADERS) and [
        markup.text(cell).casefold() for cell in cells
    ] == list(FORMATIVE_HEADERS)


def _single(cell: html.HtmlElement) -> None:
    if cell.get("colspan", "1") != "1" or cell.get("rowspan", "1") != "1":
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)


def _plain(cell: html.HtmlElement) -> str:
    _single(cell)
    if any(isinstance(node.tag, str) for node in cell.iterdescendants()):
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    return markup.text(cell)


def _link(cell: html.HtmlElement) -> tuple[str, str]:
    """The detail ID and full text of the assessment cell.

    Observed: one link whose optional first child is an empty coloured
    `span.grade-box` marker, followed by the text. Anything else is new markup.
    """
    _single(cell)
    anchors = [node for node in cell if isinstance(node.tag, str)]
    if len(anchors) != 1 or anchors[0].tag != "a":
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    anchor = anchors[0]
    children = [node for node in anchor.iterdescendants() if isinstance(node.tag, str)]
    if children:
        marker = children[0]
        if (
            len(children) != 1
            or marker.getparent() is not anchor
            or anchor.index(marker) != 0
            or marker.tag != "span"
            or "grade-box" not in marker.get("class", "").split()
            or markup.text(marker)
        ):
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    identifier = markup.detail_id(anchor.get("href"), FORMATIVE_DETAIL_PATH_PREFIX)
    if identifier is None:
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    return identifier, markup.text(anchor, FORMATIVE_MAX_TEXT_LENGTH)


def _template(row: html.HtmlElement) -> bool:
    """A hidden, empty template entry (ID 000000) rendered for scripts.

    Not observed inside this table (the page's observed template is an ordinary
    grade link in a separate hidden table); kept narrow on purpose.
    """
    hidden = "display:none" in row.get("style", "").replace(" ", "").casefold()
    links = [
        markup.detail_id(anchor.get("href"), FORMATIVE_DETAIL_PATH_PREFIX)
        for anchor in row.iter("a")
    ]
    if not hidden or links != [FORMATIVE_TEMPLATE_ID]:
        return False
    if any(markup.text(anchor) for anchor in row.iter("a")):
        _fail(ErrorKind.PARSE)
    return True


def _item(subject: str, cells: list[html.HtmlElement]) -> FormativeGrade:
    if len(cells) != 5:
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    identifier, text = _link(cells[0])
    category = _plain(cells[1])
    period = _plain(cells[2])
    day = markup.civil_date(_plain(cells[3]))
    kind = _plain(cells[4])
    if not text or period not in ("1", "2") or identifier == FORMATIVE_TEMPLATE_ID:
        _fail(ErrorKind.PARSE)
    return FormativeGrade(
        subject,
        text,
        category,
        cast(Literal[1, 2], int(period)),
        day,
        kind,
        identifier,
    )


def read_formative_table(
    table: html.HtmlElement, check_size: Callable[[int], None]
) -> tuple[FormativeGrade, ...]:
    """Rows in page order; a subject TH may span the rows of its group."""
    if any(nested is not table for nested in table.iter("table")):
        _fail(ErrorKind.PARSE)
    items: list[FormativeGrade] = []
    seen: set[str] = set()
    subject, remaining = "", 0
    for row in markup.rows(table):
        if markup.in_header(row):
            continue
        cells = markup.cells(row)
        if next(row.iterancestors("tfoot"), None) is not None:
            if len(cells) != 1 or markup.text(cells[0]):
                _fail(ErrorKind.PARSE)
            continue
        if _template(row):
            continue
        if remaining == 0:
            if not cells or cells[0].tag != "th":
                _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
            head = cells[0]
            span = head.get("rowspan", "1")
            if head.get("colspan", "1") != "1" or not _SPAN.fullmatch(span):
                _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
            remaining = int(span)
            if remaining > GRADE_MAX_RECORDS:
                _fail(ErrorKind.LIMIT)
            if any(isinstance(node.tag, str) for node in head.iterdescendants()):
                _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
            subject = markup.text(head)
            if not subject:
                _fail(ErrorKind.PARSE)
            cells = cells[1:]
        elif cells and cells[0].tag == "th":
            # A new subject before the spanning group ended.
            _fail(ErrorKind.PARSE)
        remaining -= 1
        item = _item(subject, cells)
        if item.detail_id in seen:
            _fail(ErrorKind.PARSE)
        seen.add(item.detail_id)
        items.append(item)
        check_size(len(items))
    if remaining:
        _fail(ErrorKind.PARSE)
    return tuple(items)
