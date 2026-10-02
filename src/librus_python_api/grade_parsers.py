"""Original bounded HTML summary parsing from source-informed requirements."""

import re
from collections.abc import Iterator

from lxml import html

from librus_python_api import markup
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
from librus_python_api.parsers import parse_page


def _summary_field(cell: html.HtmlElement) -> str | None:
    title = cell.get("title", "")
    if len(title) > GRADE_MAX_VALUE_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    label = " ".join(re.split(r"<br\s*/?>", title, flags=re.I)[0].split())
    return GRADE_SUMMARY_HEADERS.get(label)


def _header(row: html.HtmlElement) -> tuple[dict[str, int], int]:
    fields: dict[str, int] = {}
    position = GRADE_BODY_PREFIX_COLUMNS
    for cell in markup.cells(row):
        span = markup.colspan(cell)
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
        for row in markup.rows(table):
            if next(row.iterancestors("thead"), None) is None:
                continue
            # Group-heading rows can span the entire table. Only the row with
            # an annual summary title defines the body alignment contract.
            if not any(_summary_field(cell) == "annual" for cell in markup.cells(row)):
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
    subject = markup.text(cells[1])
    if not subject or markup.colspan(cells[0]) != 1 or markup.colspan(cells[1]) != 1:
        raise LibrusError(ErrorKind.PARSE)
    columns: list[html.HtmlElement] = []
    for cell in cells:
        span = markup.colspan(cell)
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
        name: GradeSummaryValue(Availability.AVAILABLE, markup.text(columns[index]))
        for name, index in fields.items()
    }
    absent = GradeSummaryValue(Availability.UNAVAILABLE, None)
    return SubjectGradeSummary(
        subject,
        values.get("midterm", absent),
        values.get("predicted_annual", absent),
        values["annual"],
    )


def _subject_rows(
    table: html.HtmlElement, width: int
) -> Iterator[list[html.HtmlElement]]:
    for row in markup.rows(table):
        if next(row.iterancestors("thead"), None) is not None:
            continue
        cells = markup.cells(row)
        if not cells:
            raise LibrusError(ErrorKind.PARSE)
        if list(row.iter("table")):
            if _outside_nested_tables(row):
                raise LibrusError(ErrorKind.PARSE)
            continue
        # An empty full-width layout spacer is not an unassigned subject. Keep
        # this exception narrow: content or a different width remains malformed.
        if (
            len(cells) == 1
            and markup.colspan(cells[0]) == width
            and not markup.text(cells[0])
        ):
            continue
        # Expanded inline detail labels are not subjects. Recognize this narrow
        # source-informed variant, never discard arbitrary malformed subject rows.
        if len(cells) > 1 and markup.text(cells[1]) == GRADE_INLINE_DETAIL_LABEL:
            continue
        yield cells


def parse_final_grades(body: bytes) -> tuple[SubjectGradeSummary, ...]:
    table, fields, width = _locate(parse_page(body))
    items: list[SubjectGradeSummary] = []
    subjects: set[str] = set()
    for cells in _subject_rows(table, width):
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
