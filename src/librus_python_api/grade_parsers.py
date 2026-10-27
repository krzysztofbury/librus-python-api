"""Original bounded HTML summary parsing from source-informed requirements."""

import re
from collections.abc import Iterator

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    GRADE_BODY_PREFIX_COLUMNS,
    GRADE_CURRENT_HEADER,
    GRADE_EMPTY_MARKERS,
    GRADE_INLINE_DETAIL_LABEL,
    GRADE_MAX_COLUMNS,
    GRADE_MAX_SUBJECTS,
    GRADE_MAX_VALUE_LENGTH,
    GRADE_MERGED_SUBJECTS,
    GRADE_POINT_ROW_NODE,
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


def is_point_table(table: html.HtmlElement) -> bool:
    """A grade table whose subject rows carry point-grade expander images."""
    if not {"decorated", "stretch"} <= set(table.get("class", "").split()):
        return False
    return any(
        GRADE_POINT_ROW_NODE.fullmatch(image.get("id", ""))
        for row in markup.rows(table)
        for cell in markup.cells(row)[:1]
        for image in cell.iter("img")
    )


def _current_header(table: html.HtmlElement) -> bool:
    """A grade table: decorated, with a current-grade header row."""
    return {"decorated", "stretch"} <= set(table.get("class", "").split()) and any(
        next(row.iterancestors("thead"), None) is not None
        and any(markup.text(cell) == GRADE_CURRENT_HEADER for cell in markup.cells(row))
        for row in markup.rows(table)
    )


def point_layout(table: html.HtmlElement) -> tuple[dict[str, int], int]:
    """Summary fields and width from the point table's current-grade header row.

    Point tables are not required to have an annual column, so the row with
    the two current-grade headers defines the body alignment instead.
    """
    headers = [
        row
        for row in markup.rows(table)
        if next(row.iterancestors("thead"), None) is not None
        and any(markup.text(cell) == GRADE_CURRENT_HEADER for cell in markup.cells(row))
    ]
    if len(headers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    return _header(headers[0])


def _candidates(
    document: html.HtmlElement,
) -> list[tuple[html.HtmlElement, dict[str, int], int]]:
    candidates: list[tuple[html.HtmlElement, dict[str, int], int]] = []
    for table in document.iter("table"):
        if not {"decorated", "stretch"} <= set(table.get("class", "").split()):
            continue
        if is_point_table(table):
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
    return candidates


def _locate(
    document: html.HtmlElement,
) -> tuple[html.HtmlElement, dict[str, int], int]:
    candidates = _candidates(document)
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


def _subject_columns(
    cells: list[html.HtmlElement], width: int
) -> tuple[str, list[html.HtmlElement]]:
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
    return subject, columns


def _summary(
    cells: list[html.HtmlElement],
    fields: dict[str, int],
    width: int,
) -> SubjectGradeSummary:
    subject, columns = _subject_columns(cells, width)
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
        # Only a point table may lack the annual column.
        values.get("annual", absent),
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


def merge_value(
    first: GradeSummaryValue, other: GradeSummaryValue
) -> GradeSummaryValue:
    """One subject's value shown by both grade tables.

    An assigned value fills an unassigned one and equal values are one value;
    two different assigned values are ambiguous.
    """
    first_set, other_set = (
        value.raw is not None and value.raw not in GRADE_EMPTY_MARKERS
        for value in (first, other)
    )
    if first_set and other_set and first.raw != other.raw:
        raise LibrusError(ErrorKind.PARSE)
    if other_set and not first_set:
        return other
    # An unassigned shown column still says more than an absent one.
    return other if first.availability is Availability.UNAVAILABLE else first


def parse_final_grades(body: bytes) -> tuple[SubjectGradeSummary, ...]:
    document = parse_page(body)
    point_tables = [table for table in document.iter("table") if is_point_table(table)]
    if len(point_tables) > 1:
        raise LibrusError(ErrorKind.PARSE)
    # A point-grade school may show the ordinary table or omit it. An ordinary
    # grade table without an annual column is still an unknown layout.
    sources = _candidates(document)
    if len(sources) > 1 or not (sources or point_tables):
        raise LibrusError(ErrorKind.PARSE)
    if point_tables:
        located = {id(table) for table, _, _ in sources}
        if any(
            _current_header(table) and id(table) not in located
            for table in document.iter("table")
            if table not in point_tables
        ):
            raise LibrusError(ErrorKind.PARSE)
        fields, width = point_layout(point_tables[0])
        if fields:
            sources.append((point_tables[0], fields, width))
    items: dict[str, SubjectGradeSummary] = {}
    for table, fields, width in sources:
        family_subjects: set[str] = set()
        for cells in _subject_rows(table, width):
            item = _summary(cells, fields, width)
            if item.subject in family_subjects:
                raise LibrusError(ErrorKind.PARSE)
            family_subjects.add(item.subject)
            previous = items.get(item.subject)
            items[item.subject] = (
                item
                if previous is None
                else SubjectGradeSummary(
                    item.subject,
                    merge_value(previous.midterm, item.midterm),
                    merge_value(previous.predicted_annual, item.predicted_annual),
                    merge_value(previous.annual, item.annual),
                )
            )
            if len(items) > GRADE_MAX_SUBJECTS:
                raise LibrusError(ErrorKind.LIMIT)
    # No evidenced no-subject marker exists. Missing rows are not empty success;
    # a valid all-unassigned page still lists its subjects with raw '-' values.
    if not items:
        raise LibrusError(ErrorKind.PARSE)
    return tuple(items.values())
