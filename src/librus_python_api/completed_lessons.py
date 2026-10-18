"""Original bounded completed-lesson parsing and continuation integrity policy."""

import hashlib
import re
from dataclasses import astuple
from datetime import date

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    COMPLETED_LESSONS_COLUMNS,
    COMPLETED_LESSONS_MAX_BATCH_ITEMS,
    COMPLETED_LESSONS_MAX_BATCH_PAGES,
    COMPLETED_LESSONS_MAX_PAGE_COUNT,
    COMPLETED_LESSONS_MAX_PAGE_ITEMS,
    COMPLETED_LESSONS_OPTIONAL_HEADERS,
    SCHOOL_MAX_CONTENT_LENGTH,
    SCHOOL_MAX_FIELD_LENGTH,
    SCHOOL_MAX_TOTAL_TEXT_LENGTH,
    completed_lessons_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    CompletedLesson,
    CompletedLessonsCursor,
)
from librus_python_api.parsers import page_notices, parse_page


def validate_selection(
    start: date,
    end: date,
    cursor: CompletedLessonsCursor | None,
    max_pages: int,
    limit: int,
    account: str,
) -> None:
    completed_lessons_form(start, end, 0)
    if (
        type(max_pages) is not int
        or not 1 <= max_pages <= COMPLETED_LESSONS_MAX_BATCH_PAGES
        or type(limit) is not int
        or not 1 <= limit <= COMPLETED_LESSONS_MAX_BATCH_ITEMS
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if cursor is None:
        return
    # Cursors are caller-supplied dataclasses, not authenticated opaque tokens.
    if not isinstance(cursor, CompletedLessonsCursor):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if (
        cursor.account != account
        or cursor.start != start
        or cursor.end != end
        or type(cursor.page) is not int
        or type(cursor.offset) is not int
        or type(cursor.page_count) is not int
        or not 1 <= cursor.page_count <= COMPLETED_LESSONS_MAX_PAGE_COUNT
        or not 0 <= cursor.page < cursor.page_count
        or not 0 <= cursor.offset < COMPLETED_LESSONS_MAX_PAGE_ITEMS
        or (cursor.offset == 0 and cursor.page == 0)
        or not isinstance(cursor.fingerprint, str)
        or re.fullmatch(r"[0-9a-f]{64}", cursor.fingerprint) is None
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    completed_lessons_form(cursor.start, cursor.end, cursor.page)


def _pagination(document: html.HtmlElement, page: int) -> tuple[int, int | None]:
    """The page count and, when shown, the number of rows the page reports."""
    containers = [
        node
        for node in document.iter("div")
        if "pagination" in node.get("class", "").split()
    ]
    if not containers:
        if page != 0:
            raise LibrusError(ErrorKind.PARSE)
        return 1, None
    if len(containers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    spans = [node for node in containers[0] if node.tag == "span"]
    if len(spans) != 1:
        raise LibrusError(ErrorKind.PARSE)
    value = markup.text(spans[0], SCHOOL_MAX_FIELD_LENGTH)
    match = re.fullmatch(
        r"(?:Strona\s+)?([0-9]{1,4})\s+z\s+([0-9]{1,4})"
        r"(?:\s+Pozycje\s+([0-9]{1,6})\.\.([0-9]{1,6})\s+z\s+([0-9]{1,6}))?",
        value,
        re.I,
    )
    if match is None:
        raise LibrusError(ErrorKind.PARSE)
    current, count = int(match[1]), int(match[2])
    if count > COMPLETED_LESSONS_MAX_PAGE_COUNT:
        raise LibrusError(ErrorKind.LIMIT)
    if not 1 <= current <= count or current != page + 1:
        raise LibrusError(ErrorKind.PARSE)
    if match[3] is None:
        return count, None
    # Some schools append the item range: "Pozycje first..last z total".
    first, last, total = int(match[3]), int(match[4]), int(match[5])
    if not 1 <= first <= last <= total:
        raise LibrusError(ErrorKind.PARSE)
    return count, last - first + 1


def _optional_columns(table: html.HtmlElement) -> frozenset[int]:
    """Row positions of optional columns, located by their header labels."""
    positions: set[int] = set()
    for row in markup.rows(table):
        if not markup.in_header(row):
            continue
        position = 0
        labels = [
            (cell, markup.text(cell, SCHOOL_MAX_FIELD_LENGTH))
            for cell in markup.cells(row)
        ]
        if not any(label in COMPLETED_LESSONS_OPTIONAL_HEADERS for _, label in labels):
            continue
        if positions:
            raise LibrusError(ErrorKind.PARSE)
        for cell, label in labels:
            span = markup.colspan(cell)
            if label in COMPLETED_LESSONS_OPTIONAL_HEADERS:
                if span != 1:
                    raise LibrusError(ErrorKind.PARSE)
                positions.add(position)
            position += span
        # A labelled header must describe exactly the row layout it extends.
        if position != COMPLETED_LESSONS_COLUMNS + len(positions):
            raise LibrusError(ErrorKind.PARSE)
    return frozenset(positions)


def _closing_row(row: html.HtmlElement, width: int) -> bool:
    """A blank full-width row that closes some schools' tables, not a lesson."""
    cells = markup.cells(row)
    return (
        len(cells) == 1
        and cells[0].tag == "td"
        and markup.colspan(cells[0]) == width
        and not any(isinstance(node.tag, str) for node in cells[0])
        and not markup.text(cells[0], SCHOOL_MAX_FIELD_LENGTH)
    )


def _day(value: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        year, month, day = map(int, value.split("-"))
    elif re.fullmatch(r"[0-9]{2}-[0-9]{2}-[0-9]{4}", value):
        day, month, year = map(int, value.split("-"))
    else:
        raise LibrusError(ErrorKind.PARSE)
    invalid = False
    try:
        result = date(year, month, day)
    except ValueError:
        invalid = True
    if invalid:
        raise LibrusError(ErrorKind.PARSE)
    return result


def _lesson(
    row: html.HtmlElement, start: date, end: date, optional: frozenset[int]
) -> CompletedLesson:
    cells = markup.cells(row)
    if len(cells) != COMPLETED_LESSONS_COLUMNS + len(optional) or any(
        cell.tag != "td"
        or cell.get("rowspan", "1") != "1"
        or cell.get("colspan", "1") != "1"
        for cell in cells
    ):
        raise LibrusError(ErrorKind.PARSE)
    for index in optional:
        # Content in an optional column is not modelled; never drop it silently.
        if any(isinstance(node.tag, str) for node in cells[index]) or markup.text(
            cells[index], SCHOOL_MAX_FIELD_LENGTH
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    cells = [cell for index, cell in enumerate(cells) if index not in optional]
    date_cells = [
        c for c in cells if {"center", "small"} <= set(c.get("class", "").split())
    ]
    weekdays = [c for c in cells if "tiny" in c.get("class", "").split()]
    data = [c for c in cells if c not in date_cells and c not in weekdays]
    if len(date_cells) != 1 or len(weekdays) != 1 or len(data) != 5:
        raise LibrusError(ErrorKind.PARSE)
    raw_day = markup.text(date_cells[0], SCHOOL_MAX_FIELD_LENGTH)
    day = _day(raw_day)
    if not start <= day <= end:
        raise LibrusError(ErrorKind.PARSE)
    values = [
        markup.text(
            c,
            SCHOOL_MAX_CONTENT_LENGTH if i == 2 else SCHOOL_MAX_FIELD_LENGTH,
            multiline=True,
        )
        for i, c in enumerate(data)
    ]
    raw_number, combined, topic, z_value, symbol = values
    if raw_number not in {"", "-"} and re.fullmatch(r"[0-9]{1,2}", raw_number) is None:
        raise LibrusError(ErrorKind.PARSE)
    # Some schools render "<b>Subject</b>, <br>Teacher" or pad the comma.
    names = [name.strip() for name in combined.split(",")]
    subject, teacher = (names[0], names[1]) if len(names) == 2 else (combined, None)
    if not subject or teacher == "":
        raise LibrusError(ErrorKind.PARSE)
    anchors = list(data[4].iter("a"))
    if len(anchors) > 1:
        raise LibrusError(ErrorKind.PARSE)
    identifier = markup.attendance_detail_id(anchors[0]) if anchors else None
    if anchors and identifier is None:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return CompletedLesson(
        day,
        raw_day,
        markup.text(weekdays[0], SCHOOL_MAX_FIELD_LENGTH),
        int(raw_number) if raw_number not in {"", "-"} else None,
        raw_number,
        subject,
        teacher,
        combined,
        topic,
        z_value,
        symbol,
        identifier,
    )


def parse_completed_lessons(
    body: bytes,
    start: date,
    end: date,
    page: int,
) -> tuple[tuple[CompletedLesson, ...], int, str]:
    completed_lessons_form(start, end, page)
    document = parse_page(body)
    count, reported = _pagination(document, page)
    # A date-filter form table shares the "decorated" class with the data table.
    tables = [
        t
        for t in document.iter("table")
        if "decorated" in (classes := t.get("class", "").split())
        and "filters" not in classes
    ]
    empty = [
        n
        for n in document.iter()
        if isinstance(n.tag, str) and "msgEmptyTable" in n.get("class", "").split()
    ]
    if len(tables) > 1 or len(empty) > 1:
        raise LibrusError(ErrorKind.PARSE)
    items: list[CompletedLesson] = []
    total = 0
    if tables:
        if list(tables[0].iterdescendants("table")):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        optional = _optional_columns(tables[0])
        lines = [row for row in markup.rows(tables[0]) if not markup.in_header(row)]
        if lines and _closing_row(lines[-1], COMPLETED_LESSONS_COLUMNS + len(optional)):
            lines.pop()
        for row in lines:
            item = _lesson(row, start, end, optional)
            total += sum(len(v) for v in astuple(item) if isinstance(v, str))
            items.append(item)
            if (
                len(items) > COMPLETED_LESSONS_MAX_PAGE_ITEMS
                or total > SCHOOL_MAX_TOTAL_TEXT_LENGTH
            ):
                raise LibrusError(ErrorKind.LIMIT)
    if reported is not None and reported != len(items):
        raise LibrusError(ErrorKind.PARSE)
    if (items and empty) or (not items and (not empty or count != 1 or page != 0)):
        raise LibrusError(ErrorKind.PARSE)
    # An unrecognized notice next to an empty marker is not a valid empty page.
    if empty and (
        not markup.text(empty[0], SCHOOL_MAX_FIELD_LENGTH) or page_notices(document)
    ):
        raise LibrusError(ErrorKind.PARSE)
    rows = tuple(items)
    # Domain values, not HTML/CSRF noise or redacted reprs, define page integrity.
    fingerprint = hashlib.sha256(
        repr(tuple(astuple(i) for i in rows)).encode()
    ).hexdigest()
    return rows, count, fingerprint
