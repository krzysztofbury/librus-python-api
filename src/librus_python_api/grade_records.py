"""Original bounded parser for inline semester grades and school averages."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, cast

from lxml import html

from librus_python_api.config import (
    GRADE_AVERAGE_HEADERS,
    GRADE_BODY_PREFIX_COLUMNS,
    GRADE_CURRENT_HEADER,
    GRADE_EMPTY_MARKERS,
    GRADE_MAX_METADATA_FIELDS,
    GRADE_MAX_METADATA_LENGTH,
    GRADE_MAX_RECORDS,
    GRADE_MAX_SUBJECTS,
    GRADE_PERIOD_HEADERS,
    GRADE_PREDICTED_ANNUAL_HEADER,
    GRADE_PREDICTED_PERIOD_HEADERS,
    GRADE_PUBLICATION_DATE_LABEL,
    GRADE_PUBLICATION_PERIOD_LABELS,
    GRADE_PUBLICATION_TEACHER_LABEL,
    GRADE_WEEKDAY_LABELS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.grade_parsers import (
    _cells,
    _locate,
    _rows,
    _span,
    _subject_rows,
    _summary,
    _text,
)
from librus_python_api.models import (
    Availability,
    DescriptiveGrade,
    DescriptiveGradeSummary,
    GradeKind,
    GradeRecords,
    GradeSummaryValue,
    NumericGrade,
    SchoolAverage,
)
from librus_python_api.parsers import parse_html_document


def _label(title: str) -> str:
    return " ".join(re.split(r"<br\s*/?>", title, flags=re.I)[0].split())


def _layout(table: html.HtmlElement) -> tuple[list[int], dict[int, int]]:
    current: list[int] = []
    averages: dict[int, int] = {}
    for row in _rows(table):
        if next(row.iterancestors("thead"), None) is None:
            continue
        cells = _cells(row)
        if not any(_text(c) == GRADE_CURRENT_HEADER for c in cells):
            continue
        if current:
            raise LibrusError(ErrorKind.PARSE)
        position = GRADE_BODY_PREFIX_COLUMNS
        for cell in cells:
            if _text(cell) == GRADE_CURRENT_HEADER:
                if _span(cell) != 1:
                    raise LibrusError(ErrorKind.PARSE)
                current.append(position)
            period = GRADE_AVERAGE_HEADERS.get(_label(cell.get("title", "")))
            if period is not None:
                if period in averages or _span(cell) != 1:
                    raise LibrusError(ErrorKind.PARSE)
                averages[period] = position
            position += _span(cell)
    if len(current) != 2:
        raise LibrusError(ErrorKind.PARSE)
    return current, averages


def _metadata(element: html.HtmlElement) -> dict[str, str]:
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
        # Tooltips are HTML strings inside HTML attributes. Parse markup only
        # where present; apply the same bounded document rules to that tree.
        rendered = (
            _text(parse_html_document(chunk.encode()))
            if "<" in chunk
            else " ".join(chunk.split())
        )
        key, separator, value = rendered.partition(":")
        key, value = key.strip(), value.strip()
        if not separator or not key or key in result:
            raise LibrusError(ErrorKind.PARSE)
        result[key] = value
    return result


def _day(value: str | None) -> date:
    failed = False
    match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2})(?: \(([^()]+)\))?", value or "")
    if match is None or (match[2] is not None and match[2] not in GRADE_WEEKDAY_LABELS):
        raise LibrusError(ErrorKind.PARSE)
    try:
        return date.fromisoformat(match[1])
    except ValueError:
        failed = True
    assert failed
    raise LibrusError(ErrorKind.PARSE)


def _numeric(
    element: html.HtmlElement,
    subject: str,
    semester: Literal[0, 1, 2],
    kind: GradeKind = GradeKind.CURRENT,
) -> NumericGrade:
    metadata = _metadata(element)
    counts = metadata.get("Licz do średniej")
    if counts is not None and counts.casefold() not in ("tak", "nie"):
        raise LibrusError(ErrorKind.PARSE)
    weight = metadata.get("Waga")
    if weight is not None and not re.fullmatch(r"[0-9]{1,4}", weight):
        raise LibrusError(ErrorKind.PARSE)
    raw = _text(element)
    if not raw:
        raise LibrusError(ErrorKind.PARSE)
    href = element.get("href")
    if href is not None and len(href) > GRADE_MAX_METADATA_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    return NumericGrade(
        subject,
        raw,
        _day(metadata.get("Data")),
        semester,
        None if counts is None else counts.casefold() == "tak",
        None if weight is None else int(weight),
        metadata.get("Kategoria"),
        metadata.get("Nauczyciel"),
        metadata.get("Komentarz"),
        href,
        tuple(metadata.items()),
        kind,
    )


def _descriptive(
    box: html.HtmlElement,
    element: html.HtmlElement,
    subject: str,
    semester: Literal[0, 1, 2],
    kind: GradeKind = GradeKind.CURRENT,
) -> DescriptiveGrade:
    metadata = _metadata(box)
    raw = _text(element)
    if not raw:
        raise LibrusError(ErrorKind.PARSE)
    return DescriptiveGrade(
        subject,
        raw,
        _day(metadata.get("Data")),
        semester,
        metadata.get("Nauczyciel"),
        metadata.get("Komentarz"),
        tuple(metadata.items()),
        kind,
    )


@dataclass(slots=True)
class _Collection:
    numeric: list[NumericGrade] = field(default_factory=list, repr=False)
    descriptive: list[DescriptiveGrade] = field(default_factory=list, repr=False)
    descriptive_summaries: list[DescriptiveGradeSummary] = field(
        default_factory=list, repr=False
    )
    averages: list[SchoolAverage] = field(default_factory=list, repr=False)
    subjects: set[tuple[bool, str]] = field(default_factory=set, repr=False)
    consumed: set[html.HtmlElement] = field(default_factory=set, repr=False)
    publication_rows: set[html.HtmlElement] = field(default_factory=set, repr=False)

    def check_size(self) -> None:
        if (
            len(self.numeric) + len(self.descriptive) + len(self.descriptive_summaries)
            > GRADE_MAX_RECORDS
        ):
            raise LibrusError(ErrorKind.LIMIT)

    def subject(self, value: str, *, descriptive: bool = False) -> None:
        key = (descriptive, value)
        if not value or key in self.subjects:
            raise LibrusError(ErrorKind.PARSE)
        self.subjects.add(key)
        if len(self.subjects) > GRADE_MAX_SUBJECTS:
            raise LibrusError(ErrorKind.LIMIT)


def _boxes(cell: html.HtmlElement) -> list[html.HtmlElement]:
    return [
        node
        for node in cell.iter("span")
        if "grade-box" in node.get("class", "").split()
    ]


def _entries(
    cell: html.HtmlElement,
    subject: str,
    period: Literal[0, 1, 2],
    collection: _Collection,
    *,
    kind: GradeKind = GradeKind.CURRENT,
    descriptive: bool = False,
    require_empty_marker: bool = True,
) -> None:
    boxes = _boxes(cell)
    if not boxes and require_empty_marker and _text(cell) not in GRADE_EMPTY_MARKERS:
        if (
            not descriptive
            or period == 0
            or any(isinstance(node.tag, str) for node in cell)
        ):
            raise LibrusError(ErrorKind.PARSE)
        raw = _text(cell)
        if len(raw) > GRADE_MAX_METADATA_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        collection.descriptive_summaries.append(
            DescriptiveGradeSummary(subject, period, raw)
        )
        collection.check_size()
    for box in boxes:
        anchors = [e for e in box if e.tag == "a"]
        descriptions = [
            e for e in box if e.tag == "span" and "ocena" in e.get("class", "").split()
        ]
        if len(anchors) + len(descriptions) != 1:
            raise LibrusError(ErrorKind.PARSE)
        if anchors:
            record = _numeric(anchors[0], subject, period, kind)
            if descriptive:
                href = record.href
                if href is not None and re.sub(
                    r"[\x00-\x20]", "", href
                ).casefold().startswith(("javascript:", "data:", "vbscript:")):
                    href = None
                collection.descriptive.append(
                    DescriptiveGrade(
                        record.subject,
                        record.raw,
                        record.day,
                        record.semester,
                        record.teacher,
                        record.comment,
                        record.metadata,
                        kind,
                        href,
                    )
                )
            else:
                collection.numeric.append(record)
        else:
            collection.descriptive.append(
                _descriptive(box, descriptions[0], subject, period, kind)
            )
        collection.consumed.add(box)
        collection.check_size()


def _descriptive_row(cells: list[html.HtmlElement]) -> bool:
    return (
        len(cells) in (4, 6)
        and {"micro", "center", "screen-only"} <= set(cells[0].get("class", "").split())
        and all(_span(cell) == 1 for cell in cells)
    )


def _read_descriptive_row(
    cells: list[html.HtmlElement], collection: _Collection
) -> None:
    subject = _text(cells[1])
    collection.subject(subject, descriptive=True)
    for period in (1, 2):
        _entries(cells[period + 1], subject, period, collection, descriptive=True)
    if len(cells) == 6:
        for cell in cells[4:]:
            if _boxes(cell):
                # These columns have no established semester semantics.
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _period_columns(table: html.HtmlElement) -> dict[tuple[int, GradeKind], int]:
    result: dict[tuple[int, GradeKind], int] = {}
    for row in _rows(table):
        cells = _cells(row)
        if next(row.iterancestors("thead"), None) is None or not any(
            _text(c) == GRADE_CURRENT_HEADER for c in cells
        ):
            continue
        position = GRADE_BODY_PREFIX_COLUMNS
        for cell in cells:
            label = _label(cell.get("title", ""))
            period = GRADE_PERIOD_HEADERS.get(label)
            kind = GradeKind.ANNUAL if period == 0 else GradeKind.PERIOD
            if label == GRADE_PREDICTED_ANNUAL_HEADER:
                period, kind = 0, GradeKind.PREDICTED_ANNUAL
            elif label in GRADE_PREDICTED_PERIOD_HEADERS:
                period, kind = (
                    GRADE_PREDICTED_PERIOD_HEADERS[label],
                    GradeKind.PREDICTED_PERIOD,
                )
            if period is not None:
                if (period, kind) in result or _span(cell) != 1:
                    raise LibrusError(ErrorKind.PARSE)
                result[(period, kind)] = position
            position += _span(cell)
    return result


def _read_numeric_table(table: html.HtmlElement, collection: _Collection) -> None:
    # Preserve the established full-row and summary alignment validation.
    _, fields, width = _locate(table)
    current, means = _layout(table)
    periods = _period_columns(table)
    for cells in _subject_rows(table, width):
        if cells[0].getparent() in collection.publication_rows:
            continue
        if _descriptive_row(cells):
            _read_descriptive_row(cells, collection)
            continue
        subject = _summary(cells, fields, width).subject
        collection.subject(subject)
        columns = [cell for cell in cells for _ in range(_span(cell))]
        for period in (1, 2, 0):
            index = means.get(period)
            value = (
                GradeSummaryValue(Availability.UNAVAILABLE, None)
                if index is None or _span(columns[index]) != 1
                else GradeSummaryValue(Availability.AVAILABLE, _text(columns[index]))
            )
            collection.averages.append(SchoolAverage(subject, period, value))
        if columns[current[0]] is columns[current[1]] and _boxes(columns[current[0]]):
            raise LibrusError(ErrorKind.PARSE)
        seen: set[html.HtmlElement] = set()
        for period, index in enumerate(current, start=1):
            if columns[index] not in seen:
                _entries(
                    columns[index], subject, cast(Literal[1, 2], period), collection
                )
                seen.add(columns[index])
        for (period, kind), index in periods.items():
            cell = columns[index]
            if cell in seen and _boxes(cell):
                raise LibrusError(ErrorKind.PARSE)
            _entries(
                cell,
                subject,
                cast(Literal[0, 1, 2], period),
                collection,
                kind=kind,
                require_empty_marker=False,
            )


def _read_publications(table: html.HtmlElement, collection: _Collection) -> None:
    rows = list(_rows(table))
    for index, row in enumerate(rows):
        headers = [
            cell
            for cell in _cells(row)
            if cell.tag == "th"
            and list(cell.iter("strong"))
            and GRADE_PUBLICATION_DATE_LABEL in cell.text_content()
        ]
        if not headers:
            continue
        if len(headers) != 1 or index + 1 == len(rows):
            raise LibrusError(ErrorKind.PARSE)
        header = headers[0]
        titles = list(header.iter("strong"))
        if len(titles) != 1:
            raise LibrusError(ErrorKind.PARSE)
        title = _text(titles[0])
        info = _text(header)
        date_info = info.partition(GRADE_PUBLICATION_DATE_LABEL)[2].strip()
        day = _day(date_info[:10])
        if len(date_info) > 10 and date_info[10] not in (" ", ",", ")"):
            raise LibrusError(ErrorKind.PARSE)
        teacher_info = info.partition(GRADE_PUBLICATION_TEACHER_LABEL)[2].strip()
        teacher = teacher_info.rsplit(")", 1)[0].strip() if teacher_info else None
        matching = {
            period
            for label, period in GRADE_PUBLICATION_PERIOD_LABELS.items()
            if re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", title)
        }
        if len(matching) > 1:
            raise LibrusError(ErrorKind.PARSE)
        paragraphs = list(rows[index + 1].iter("p"))
        raw = "\n".join(_text(paragraph) for paragraph in paragraphs).strip()
        if not title or not raw:
            raise LibrusError(ErrorKind.PARSE)
        if len(raw) > GRADE_MAX_METADATA_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        metadata = (("Data", date_info[:10]),)
        collection.descriptive.append(
            DescriptiveGrade(
                title,
                raw,
                day,
                cast(Literal[1, 2] | None, next(iter(matching), None)),
                teacher,
                None,
                metadata,
                GradeKind.PUBLICATION,
            )
        )
        collection.consumed.add(header)
        collection.publication_rows.update((row, rows[index + 1]))
        collection.check_size()


def parse_grade_records(body: bytes) -> GradeRecords:
    document = parse_html_document(body)
    collection = _Collection()
    numeric_tables = []
    tables = list(document.iter("table"))
    for table in tables:
        if not {"decorated", "stretch"} <= set(table.get("class", "").split()):
            continue
        if any(
            next(row.iterancestors("thead"), None) is not None
            and any(_text(c) == GRADE_CURRENT_HEADER for c in _cells(row))
            for row in _rows(table)
        ):
            numeric_tables.append(table)
    if len(numeric_tables) > 1:
        raise LibrusError(ErrorKind.PARSE)
    for table in tables:
        _read_publications(table, collection)
        if table in numeric_tables:
            _read_numeric_table(table, collection)
        else:
            for row in _rows(table):
                cells = _cells(row)
                if _descriptive_row(cells):
                    _read_descriptive_row(cells, collection)
                elif (
                    cells
                    and cells[0].tag == "td"
                    and {"micro", "center", "screen-only"}
                    <= set(cells[0].get("class", "").split())
                ):
                    raise LibrusError(ErrorKind.PARSE)
    for element in document.iter():
        if not isinstance(element.tag, str) or element in collection.consumed:
            continue
        dated_box = "grade-box" in element.get("class", "").split() and any(
            "Data:" in (node.get("title") or "") for node in element.iter()
        )
        if dated_box:
            if any(
                parent in numeric_tables for parent in element.iterancestors("table")
            ):
                # Expanded full-row detail mirrors were intentionally excluded.
                cell = next(element.iterancestors("td", "th"), None)
                if (
                    cell is not None
                    and next(cell.iterancestors("table"), None) not in numeric_tables
                ):
                    continue
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if not collection.subjects and not collection.descriptive:
        raise LibrusError(ErrorKind.PARSE)
    for descriptive, subject in sorted(collection.subjects):
        if descriptive and (False, subject) not in collection.subjects:
            collection.averages.extend(
                SchoolAverage(
                    subject,
                    period,
                    GradeSummaryValue(Availability.UNAVAILABLE, None),
                )
                for period in (1, 2, 0)
            )
    return GradeRecords(
        tuple(collection.numeric),
        tuple(collection.descriptive),
        tuple(collection.averages),
        tuple(collection.descriptive_summaries),
    )
