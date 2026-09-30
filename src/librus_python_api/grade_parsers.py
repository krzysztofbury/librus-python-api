"""Original bounded HTML summary parsing from source-informed requirements."""

import re
from collections.abc import Iterator

from lxml import etree, html

from librus_python_api.config import (
    GRADE_BODY_PREFIX_COLUMNS,
    GRADE_INLINE_DETAIL_LABEL,
    GRADE_MAX_COLUMNS,
    GRADE_MAX_SUBJECTS,
    GRADE_MAX_VALUE_LENGTH,
    GRADE_MERGED_SUBJECTS,
    GRADE_SUMMARY_HEADERS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    Availability,
    GradeSummaryValue,
    SubjectGradeSummary,
)
from librus_python_api.parsers import parse_html_document


def _text(element: html.HtmlElement) -> str:
    # Render block/line boundaries, but keep inline grade symbols together.
    # The shared document parser has already bounded this tree's nodes/depth.
    parts: list[str] = []
    for event, node in etree.iterwalk(element, events=("start", "end")):
        if node.tag in ("br", "p", "div", "li"):
            parts.append(" ")
        if event == "start" and node.text:
            parts.append(node.text)
        if event == "end" and node is not element and node.tail:
            parts.append(node.tail)
    value = " ".join("".join(parts).split())
    if len(value) > GRADE_MAX_VALUE_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    return value


def _cells(row: html.HtmlElement) -> list[html.HtmlElement]:
    return [item for item in row if item.tag in ("td", "th")]


def _span(cell: html.HtmlElement) -> int:
    value = cell.get("colspan", "1")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", value):
        raise LibrusError(ErrorKind.PARSE)
    span = int(value)
    if span > GRADE_MAX_COLUMNS:
        raise LibrusError(ErrorKind.LIMIT)
    if cell.get("rowspan", "1") != "1":
        raise LibrusError(ErrorKind.PARSE)
    return span


def _rows(table: html.HtmlElement) -> Iterator[html.HtmlElement]:
    for row in table.iter("tr"):
        if next(row.iterancestors("table"), None) is table:
            yield row


def _summary_field(cell: html.HtmlElement) -> str | None:
    title = cell.get("title", "")
    if len(title) > GRADE_MAX_VALUE_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    label = " ".join(re.split(r"<br\s*/?>", title, flags=re.I)[0].split())
    return GRADE_SUMMARY_HEADERS.get(label)


def _header(row: html.HtmlElement) -> tuple[dict[str, int], int]:
    fields: dict[str, int] = {}
    position = GRADE_BODY_PREFIX_COLUMNS
    for cell in _cells(row):
        span = _span(cell)
        if position + span > GRADE_MAX_COLUMNS:
            raise LibrusError(ErrorKind.LIMIT)
        field = _summary_field(cell)
        if field is not None:
            if field in fields:
                raise LibrusError(ErrorKind.PARSE)
            fields[field] = position
        position += span
    return fields, position


def _locate(
    document: html.HtmlElement,
) -> tuple[html.HtmlElement, dict[str, int], int]:
    candidates: list[tuple[html.HtmlElement, dict[str, int], int]] = []
    for table in document.iter("table"):
        if not {"decorated", "stretch"} <= set(table.get("class", "").split()):
            continue
        for row in _rows(table):
            if next(row.iterancestors("thead"), None) is None:
                continue
            # Group-heading rows can span the entire table. Only the row with
            # an annual summary title defines the body alignment contract.
            if not any(_summary_field(cell) == "annual" for cell in _cells(row)):
                continue
            fields, width = _header(row)
            candidates.append((table, fields, width))
    if len(candidates) != 1:
        raise LibrusError(ErrorKind.PARSE)
    return candidates[0]


def _outside_nested_tables(row: html.HtmlElement) -> str:
    """Reject a subject row masquerading as an expanded-detail wrapper."""
    parts: list[str] = []
    pending = [row]
    while pending:
        element = pending.pop()
        if element.tail:
            parts.append(element.tail)
        if element.tag == "table":
            continue
        if element.text:
            parts.append(element.text)
        pending.extend(element)
    return " ".join(parts).strip()


def _summary(
    cells: list[html.HtmlElement],
    fields: dict[str, int],
    width: int,
) -> SubjectGradeSummary:
    if len(cells) < GRADE_BODY_PREFIX_COLUMNS:
        raise LibrusError(ErrorKind.PARSE)
    subject = _text(cells[1])
    if not subject or _span(cells[0]) != 1 or _span(cells[1]) != 1:
        raise LibrusError(ErrorKind.PARSE)
    columns: list[html.HtmlElement] = []
    for cell in cells:
        span = _span(cell)
        if span > 1 and subject not in GRADE_MERGED_SUBJECTS:
            raise LibrusError(ErrorKind.PARSE)
        if len(columns) + span > GRADE_MAX_COLUMNS:
            raise LibrusError(ErrorKind.LIMIT)
        columns.extend([cell] * span)
    if len(columns) != width:
        raise LibrusError(ErrorKind.PARSE)
    selected = [columns[index] for index in fields.values()]
    if len({id(cell) for cell in selected}) != len(selected):
        # A single merged value cannot mean two different summary fields.
        raise LibrusError(ErrorKind.PARSE)
    values = {
        name: GradeSummaryValue(Availability.AVAILABLE, _text(columns[index]))
        for name, index in fields.items()
    }
    absent = GradeSummaryValue(Availability.UNAVAILABLE, None)
    return SubjectGradeSummary(
        subject,
        values.get("midterm", absent),
        values.get("predicted_annual", absent),
        values["annual"],
    )


def parse_final_grades(body: bytes) -> tuple[SubjectGradeSummary, ...]:
    table, fields, width = _locate(parse_html_document(body))
    items: list[SubjectGradeSummary] = []
    subjects: set[str] = set()
    for row in _rows(table):
        if next(row.iterancestors("thead"), None) is not None:
            continue
        cells = _cells(row)
        if not cells:
            raise LibrusError(ErrorKind.PARSE)
        if list(row.iter("table")):
            if _outside_nested_tables(row):
                raise LibrusError(ErrorKind.PARSE)
            continue
        # An empty full-width layout spacer is not an unassigned subject. Keep
        # this exception narrow: content or a different width remains malformed.
        if len(cells) == 1 and _span(cells[0]) == width and not _text(cells[0]):
            continue
        # Expanded inline detail labels are not subjects. Recognize this narrow
        # source-informed variant, never discard arbitrary malformed subject rows.
        if len(cells) > 1 and _text(cells[1]) == GRADE_INLINE_DETAIL_LABEL:
            continue
        item = _summary(cells, fields, width)
        if item.subject in subjects:
            raise LibrusError(ErrorKind.PARSE)
        subjects.add(item.subject)
        items.append(item)
        if len(items) > GRADE_MAX_SUBJECTS:
            raise LibrusError(ErrorKind.LIMIT)
    # No evidenced no-subject marker exists. Missing rows are not empty success;
    # a valid all-unassigned page still lists its subjects with raw '-' values.
    if not items:
        raise LibrusError(ErrorKind.PARSE)
    return tuple(items)
