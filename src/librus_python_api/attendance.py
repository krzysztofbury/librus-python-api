"""Original bounded attendance HTML parser from source-informed requirements."""

import re
from typing import Literal, cast
from urllib.parse import urlsplit

from lxml import html

from librus_python_api.config import (
    ATTENDANCE_DETAIL_MAX_FIELDS,
    ATTENDANCE_DETAIL_PATH_PREFIX,
    ATTENDANCE_EMPTY_MARKERS,
    ATTENDANCE_MAX_RECORDS,
    ATTENDANCE_SEMESTER_LABELS,
    GRADE_MAX_METADATA_LENGTH,
    GRADE_MAX_VALUE_LENGTH,
    UPSTREAM_ORIGINS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.grade_parsers import _cells, _rows, _text
from librus_python_api.grade_records import _day, _metadata
from librus_python_api.models import (
    AttendanceDetailContent,
    AttendanceRecord,
    AttendanceRecords,
)
from librus_python_api.parsers import parse_html_document


def _detail_id(element: html.HtmlElement) -> str | None:
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
    failed = False
    target = None
    try:
        target = urlsplit(match[2])
    except ValueError:
        failed = True
    if failed or target is None:
        return None
    if target.query or target.fragment or target.username or target.password:
        return None
    if target.scheme or target.netloc:
        expected = urlsplit(UPSTREAM_ORIGINS["synergia"])
        if (target.scheme, target.netloc) != (expected.scheme, expected.netloc):
            return None
    if not target.path.startswith(ATTENDANCE_DETAIL_PATH_PREFIX):
        return None
    identifier = target.path[len(ATTENDANCE_DETAIL_PATH_PREFIX) :]
    return identifier if re.fullmatch(r"[0-9]{1,64}", identifier) else None


def _entry(element: html.HtmlElement, semester: Literal[1, 2]) -> AttendanceRecord:
    # Some source-informed tooltips separate complete bold label/value blocks
    # without BR tags. Retain the closing tags while adding field boundaries.
    title = element.get("title", "")
    if len(title) > GRADE_MAX_METADATA_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    holder = html.Element("span")
    holder.set("title", re.sub(r"</b>\s*(?=<b[ >])", "</b>\n", title, flags=re.I))
    fields = _metadata(holder)
    if any(
        max(len(key), len(value)) > GRADE_MAX_VALUE_LENGTH
        for key, value in fields.items()
    ):
        raise LibrusError(ErrorKind.LIMIT)
    period = fields.get("Godzina lekcyjna")
    if period is not None and not re.fullmatch(r"[0-9]{1,2}", period):
        raise LibrusError(ErrorKind.PARSE)
    excursion = fields.get("Czy wycieczka")
    if excursion is not None and excursion.casefold() not in ("tak", "nie"):
        raise LibrusError(ErrorKind.PARSE)
    symbol = _text(element)
    if not symbol:
        raise LibrusError(ErrorKind.PARSE)
    return AttendanceRecord(
        symbol,
        _day(fields.get("Data")),
        semester,
        fields.get("Rodzaj"),
        fields.get("Nauczyciel"),
        None if period is None else int(period),
        None if excursion is None else excursion.casefold() == "tak",
        fields.get("Temat zajęć"),
        fields.get("Lekcja"),
        _detail_id(element),
        tuple(fields.items()),
    )


def _plain_cell_is_layout(cell: html.HtmlElement) -> bool:
    value = _text(cell)
    if value in ATTENDANCE_EMPTY_MARKERS or re.fullmatch(r"[0-9]{1,2}", value):
        return True
    # Civil day labels in grid cells do not create attendance records.
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?: \([^()]+\))?", value):
        _day(value)
        return True
    return False


def parse_attendance(body: bytes) -> AttendanceRecords:
    document = parse_html_document(body)
    tables = [
        table
        for table in document.iter("table")
        if {"center", "big", "decorated"} <= set(table.get("class", "").split())
    ]
    if len(tables) != 1:
        raise LibrusError(ErrorKind.PARSE)
    table = tables[0]
    if list(table.iterdescendants("table")):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    for anchor in document.iter("a"):
        if table not in anchor.iterancestors("table") and "Data:" in anchor.get(
            "title", ""
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    semesters: list[Literal[1, 2]] = []
    semester: Literal[1, 2] | None = None
    items: list[AttendanceRecord] = []
    for row in _rows(table):
        if next(row.iterancestors("thead"), None) is not None:
            continue
        cells = _cells(row)
        if not cells or any(c.get("rowspan", "1") != "1" for c in cells):
            raise LibrusError(ErrorKind.PARSE)
        headings = [
            c for c in cells if {"bolded", "center"} <= set(c.get("class", "").split())
        ]
        if headings:
            if len(headings) != 1 or list(row.iter("a")):
                raise LibrusError(ErrorKind.PARSE)
            period = ATTENDANCE_SEMESTER_LABELS.get(
                _text(headings[0]).casefold().rstrip(":")
            )
            if period is None or period in semesters:
                raise LibrusError(ErrorKind.PARSE)
            semester = cast(Literal[1, 2], period)
            semesters.append(semester)
            continue
        for cell in cells:
            anchors = list(cell.iter("a"))
            if anchors:
                if semester is None or "center" not in cell.get("class", "").split():
                    raise LibrusError(ErrorKind.PARSE)
                for anchor in anchors:
                    items.append(_entry(anchor, semester))
                    if len(items) > ATTENDANCE_MAX_RECORDS:
                        raise LibrusError(ErrorKind.LIMIT)
            elif "center" in cell.get(
                "class", ""
            ).split() and not _plain_cell_is_layout(cell):
                raise LibrusError(ErrorKind.PARSE)
    if not semesters:
        raise LibrusError(ErrorKind.PARSE)
    return AttendanceRecords(tuple(items), tuple(semesters))


def parse_attendance_detail(body: bytes) -> AttendanceDetailContent:
    document = parse_html_document(body)
    containers = [
        node
        for node in document.iter("div")
        if "container-background" in node.get("class", "").split()
    ]
    if len(containers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    fields: dict[str, str] = {}
    notes: list[str] = []
    tables: set[html.HtmlElement] = set()
    for row in containers[0].iter("tr"):
        if not {"line0", "line1"}.intersection(row.get("class", "").split()):
            continue
        cells = _cells(row)
        table = next(row.iterancestors("table"), None)
        if table is None:
            raise LibrusError(ErrorKind.PARSE)
        tables.add(table)
        if (
            fields
            and len(cells) == 1
            and cells[0].tag == "td"
            and cells[0].get("colspan") == "2"
            and cells[0].get("rowspan", "1") == "1"
        ):
            notes.append(_text(cells[0]))
            if len(fields) + len(notes) > ATTENDANCE_DETAIL_MAX_FIELDS:
                raise LibrusError(ErrorKind.LIMIT)
            continue
        if (
            len(cells) != 2
            or cells[0].tag != "th"
            or cells[1].tag != "td"
            or any(
                c.get("rowspan", "1") != "1" or c.get("colspan", "1") != "1"
                for c in cells
            )
        ):
            raise LibrusError(ErrorKind.PARSE)
        label = _text(cells[0]).rstrip(":")
        if not label or label in fields:
            raise LibrusError(ErrorKind.PARSE)
        fields[label] = _text(cells[1])
        if len(fields) + len(notes) > ATTENDANCE_DETAIL_MAX_FIELDS:
            raise LibrusError(ErrorKind.LIMIT)
    if not fields or len(tables) != 1:
        raise LibrusError(ErrorKind.PARSE)
    return AttendanceDetailContent(tuple(fields.items()), tuple(notes))
