"""Original bounded parser for inline semester grades and school averages."""

import re
from dataclasses import dataclass, field
from typing import Literal, cast

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    BEHAVIOUR_POINTS_DETAIL_PATH_PREFIX,
    FORMATIVE_DETAIL_PATH_PREFIX,
    GRADE_AVERAGE_HEADERS,
    GRADE_BODY_PREFIX_COLUMNS,
    GRADE_CURRENT_HEADER,
    GRADE_EMPTY_MARKERS,
    GRADE_MAX_METADATA_LENGTH,
    GRADE_MAX_RECORDS,
    GRADE_MAX_SUBJECTS,
    GRADE_MERGED_SUBJECTS,
    GRADE_PERIOD_HEADERS,
    GRADE_POINT_RESULT_HEADER,
    GRADE_POINT_RESULT_PERIODS,
    GRADE_PREDICTED_ANNUAL_HEADER,
    GRADE_PREDICTED_PERIOD_HEADERS,
    GRADE_PUBLICATION_DATE_LABEL,
    GRADE_PUBLICATION_PERIOD_LABELS,
    GRADE_PUBLICATION_TEACHER_LABEL,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.formative_grades import is_formative_table, read_formative_table
from librus_python_api.grade_parsers import (
    _locate,
    _subject_columns,
    _subject_rows,
    _summary,
    is_point_table,
    point_layout,
    title_label,
)
from librus_python_api.models import (
    Availability,
    DescriptiveGrade,
    DescriptiveGradeSummary,
    FormativeGrade,
    GradeKind,
    GradeRecords,
    GradeSummaryValue,
    NumericGrade,
    SchoolAverage,
)
from librus_python_api.parsers import parse_page


def _label(title: str, *, points: bool = False) -> str:
    return title_label(title, points=points)


def _layout(
    table: html.HtmlElement, *, points: bool = False
) -> tuple[list[int], dict[int, int]]:
    current: list[int] = []
    averages: dict[int, int] = {}
    for row in markup.rows(table):
        if next(row.iterancestors("thead"), None) is None:
            continue
        cells = markup.cells(row)
        if not any(markup.text(c) == GRADE_CURRENT_HEADER for c in cells):
            continue
        if current:
            raise LibrusError(ErrorKind.PARSE)
        position = GRADE_BODY_PREFIX_COLUMNS
        for cell in cells:
            if markup.text(cell) == GRADE_CURRENT_HEADER:
                if markup.colspan(cell) != 1:
                    raise LibrusError(ErrorKind.PARSE)
                current.append(position)
            period = GRADE_AVERAGE_HEADERS.get(
                _label(cell.get("title", ""), points=points)
            )
            result = GRADE_POINT_RESULT_HEADER.fullmatch(markup.text(cell))
            if points and period is None and result is not None:
                period = GRADE_POINT_RESULT_PERIODS[result.group(1)]
            if period is not None:
                if period in averages or markup.colspan(cell) != 1:
                    raise LibrusError(ErrorKind.PARSE)
                averages[period] = position
            position += markup.colspan(cell)
    if len(current) != 2:
        raise LibrusError(ErrorKind.PARSE)
    return current, averages


def _numeric(
    element: html.HtmlElement,
    subject: str,
    semester: Literal[0, 1, 2],
    kind: GradeKind = GradeKind.CURRENT,
) -> NumericGrade:
    metadata = markup.tooltip_fields(element)
    counts = metadata.get("Licz do średniej")
    if counts is not None and counts.casefold() not in ("tak", "nie"):
        raise LibrusError(ErrorKind.PARSE)
    weight = metadata.get("Waga")
    if weight is not None and not re.fullmatch(r"[0-9]{1,4}", weight):
        raise LibrusError(ErrorKind.PARSE)
    raw = markup.text(element)
    if not raw:
        raise LibrusError(ErrorKind.PARSE)
    href = element.get("href")
    if href is not None and len(href) > GRADE_MAX_METADATA_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    return NumericGrade(
        subject,
        raw,
        markup.civil_date(metadata.get("Data")),
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
    metadata = markup.tooltip_fields(box)
    raw = markup.text(element)
    if not raw:
        raise LibrusError(ErrorKind.PARSE)
    return DescriptiveGrade(
        subject,
        raw,
        markup.civil_date(metadata.get("Data")),
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
    point_results: list[SchoolAverage] = field(default_factory=list, repr=False)
    subjects: set[tuple[bool, str]] = field(default_factory=set, repr=False)
    point_subjects: set[str] = field(default_factory=set, repr=False)
    consumed: set[html.HtmlElement] = field(default_factory=set, repr=False)
    publication_rows: set[html.HtmlElement] = field(default_factory=set, repr=False)
    formative: int = 0

    def check_size(self) -> None:
        if (
            len(self.numeric)
            + len(self.descriptive)
            + len(self.descriptive_summaries)
            + self.formative
            > GRADE_MAX_RECORDS
        ):
            raise LibrusError(ErrorKind.LIMIT)

    def count_formative(self, count: int) -> None:
        self.formative = count
        self.check_size()

    def subject(self, value: str, *, descriptive: bool = False) -> None:
        key = (descriptive, value)
        if not value or key in self.subjects:
            raise LibrusError(ErrorKind.PARSE)
        self.subjects.add(key)
        if len(self.subjects) + len(self.point_subjects) > GRADE_MAX_SUBJECTS:
            raise LibrusError(ErrorKind.LIMIT)

    def point_subject(self, value: str) -> None:
        # A subject can appear in both the ordinary and the point table.
        if not value or value in self.point_subjects:
            raise LibrusError(ErrorKind.PARSE)
        self.point_subjects.add(value)
        if len(self.subjects) + len(self.point_subjects) > GRADE_MAX_SUBJECTS:
            raise LibrusError(ErrorKind.LIMIT)


def _boxes(cell: html.HtmlElement) -> list[html.HtmlElement]:
    return [
        node
        for node in cell.iter("span")
        if "grade-box" in node.get("class", "").split()
    ]


def _behaviour_points(cell: html.HtmlElement, collection: _Collection) -> bool:
    """Recognize and validate a behaviour-points cell; points are not grades.

    The cell holds one points tooltip (starting points or a running total; its
    title is not interpreted) and point entries linking to behaviour details,
    each with its own unlabelled tooltip. Any other content next to the points
    tooltip fails instead of being skipped.
    """
    tallies = [
        node
        for node in cell
        if node.tag == "span" and "tooltip" in node.get("class", "").split()
    ]
    if not tallies:
        return False
    elements = [node for node in cell if isinstance(node.tag, str)]
    boxes = [node for node in elements if node not in tallies]
    if (
        len(tallies) != 1
        or len(tallies[0])
        or not re.fullmatch(r"-?[0-9]{1,4}", markup.text(tallies[0]))
        or (cell.text or "").strip()
        or any((node.tail or "").strip() for node in cell)
        or _boxes(cell) != boxes
    ):
        raise LibrusError(ErrorKind.PARSE)
    for box in boxes:
        anchors = [node for node in box if isinstance(node.tag, str)]
        if (
            box.getparent() is not cell
            or len(anchors) != 1
            or anchors[0].tag != "a"
            or len(anchors[0])
            or markup.detail_id(
                anchors[0].get("href"), BEHAVIOUR_POINTS_DETAIL_PATH_PREFIX
            )
            is None
            or not re.fullmatch(r"[+-]?[0-9]{1,4}", markup.text(anchors[0]))
        ):
            raise LibrusError(ErrorKind.PARSE)
        collection.consumed.add(box)
    return True


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
    if (
        not boxes
        and require_empty_marker
        and markup.text(cell) not in GRADE_EMPTY_MARKERS
    ):
        if (
            not descriptive
            or period == 0
            or any(isinstance(node.tag, str) for node in cell)
        ):
            raise LibrusError(ErrorKind.PARSE)
        raw = markup.text(cell)
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
        and all(markup.colspan(cell) == 1 for cell in cells)
    )


def _read_descriptive_row(
    cells: list[html.HtmlElement], collection: _Collection
) -> None:
    subject = markup.text(cells[1])
    collection.subject(subject, descriptive=True)
    for period in (1, 2):
        _entries(cells[period + 1], subject, period, collection, descriptive=True)
    if len(cells) == 6:
        for cell in cells[4:]:
            if _boxes(cell):
                # These columns have no established semester semantics.
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _period_columns(
    table: html.HtmlElement, *, points: bool = False
) -> dict[tuple[int, GradeKind], int]:
    result: dict[tuple[int, GradeKind], int] = {}
    for row in markup.rows(table):
        cells = markup.cells(row)
        if next(row.iterancestors("thead"), None) is None or not any(
            markup.text(c) == GRADE_CURRENT_HEADER for c in cells
        ):
            continue
        position = GRADE_BODY_PREFIX_COLUMNS
        for cell in cells:
            label = _label(cell.get("title", ""), points=points)
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
                if (period, kind) in result or markup.colspan(cell) != 1:
                    raise LibrusError(ErrorKind.PARSE)
                result[(period, kind)] = position
            position += markup.colspan(cell)
    return result


def _read_numeric_table(
    table: html.HtmlElement, collection: _Collection, *, points: bool = False
) -> None:
    # Preserve the established full-row and summary alignment validation. A
    # point table aligns on its current-grade header row and may lack summaries.
    if points:
        fields, width = point_layout(table)
    else:
        _, fields, width = _locate(table)
    current, means = _layout(table, points=points)
    periods = _period_columns(table, points=points)
    averages = collection.point_results if points else collection.averages
    # Period grades shown by both tables are one record, kept from the first.
    prior = set(collection.numeric) if points else set()
    for cells in _subject_rows(table, width, points=points):
        if cells[0].getparent() in collection.publication_rows:
            continue
        if points:
            subject = _subject_columns(cells, width)[0]
            collection.point_subject(subject)
        elif _descriptive_row(cells):
            _read_descriptive_row(cells, collection)
            continue
        else:
            subject = _summary(cells, fields, width).subject
            collection.subject(subject)
        columns = [cell for cell in cells for _ in range(markup.colspan(cell))]
        for period in (1, 2, 0):
            index = means.get(period)
            value = (
                GradeSummaryValue(Availability.UNAVAILABLE, None)
                if index is None or markup.colspan(columns[index]) != 1
                else GradeSummaryValue(
                    Availability.AVAILABLE, markup.text(columns[index])
                )
            )
            averages.append(SchoolAverage(subject, period, value))
        if columns[current[0]] is columns[current[1]] and _boxes(columns[current[0]]):
            raise LibrusError(ErrorKind.PARSE)
        seen: set[html.HtmlElement] = set()
        for period, index in enumerate(current, start=1):
            if columns[index] not in seen:
                if not (
                    subject in GRADE_MERGED_SUBJECTS
                    and _behaviour_points(columns[index], collection)
                ):
                    start = len(collection.numeric)
                    _entries(
                        columns[index], subject, cast(Literal[1, 2], period), collection
                    )
                    # A point entry without its detail link would pass as a
                    # grade symbol; an unseen link layout fails instead. The
                    # observed point table also shows formative entries.
                    if points and any(
                        record.point_grade_id is None and record.formative_id is None
                        for record in collection.numeric[start:]
                    ):
                        raise LibrusError(ErrorKind.PARSE)
                seen.add(columns[index])
        for (period, kind), index in periods.items():
            cell = columns[index]
            if cell in seen and _boxes(cell):
                raise LibrusError(ErrorKind.PARSE)
            start = len(collection.numeric)
            _entries(
                cell,
                subject,
                cast(Literal[0, 1, 2], period),
                collection,
                kind=kind,
                require_empty_marker=False,
            )
            collection.numeric[start:] = [
                record for record in collection.numeric[start:] if record not in prior
            ]


def _read_publications(table: html.HtmlElement, collection: _Collection) -> None:
    rows = list(markup.rows(table))
    for index, row in enumerate(rows):
        headers = [
            cell
            for cell in markup.cells(row)
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
        title = markup.text(titles[0])
        info = markup.text(header)
        date_info = info.partition(GRADE_PUBLICATION_DATE_LABEL)[2].strip()
        day = markup.civil_date(date_info[:10])
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
        raw = "\n".join(markup.text(paragraph) for paragraph in paragraphs).strip()
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
    document = parse_page(body)
    collection = _Collection()
    numeric_tables = []
    tables = list(document.iter("table"))
    point_tables = [table for table in tables if is_point_table(table)]
    if len(point_tables) > 1:
        raise LibrusError(ErrorKind.PARSE)
    for table in tables:
        if not {"decorated", "stretch"} <= set(
            table.get("class", "").split()
        ) or is_point_table(table):
            continue
        if any(
            next(row.iterancestors("thead"), None) is not None
            and any(markup.text(c) == GRADE_CURRENT_HEADER for c in markup.cells(row))
            for row in markup.rows(table)
        ):
            numeric_tables.append(table)
    if len(numeric_tables) > 1:
        raise LibrusError(ErrorKind.PARSE)
    formative_tables = [table for table in tables if is_formative_table(table)]
    if len(formative_tables) > 1:
        raise LibrusError(ErrorKind.PARSE)
    formative: tuple[FormativeGrade, ...] = ()
    for table in tables:
        if table in formative_tables:
            formative = read_formative_table(table, collection.count_formative)
            continue
        _read_publications(table, collection)
        if table in numeric_tables:
            _read_numeric_table(table, collection)
        elif table in point_tables:
            _read_numeric_table(table, collection, points=True)
        else:
            for row in markup.rows(table):
                cells = markup.cells(row)
                if _descriptive_row(cells):
                    _read_descriptive_row(cells, collection)
                elif (
                    cells
                    and cells[0].tag == "td"
                    and {"micro", "center", "screen-only"}
                    <= set(cells[0].get("class", "").split())
                ):
                    raise LibrusError(ErrorKind.PARSE)
    grade_tables = numeric_tables + point_tables
    for element in document.iter():
        if not isinstance(element.tag, str) or element in collection.consumed:
            continue
        dated_box = "grade-box" in element.get("class", "").split() and any(
            "Data:" in (node.get("title") or "") for node in element.iter()
        )
        if dated_box:
            if any(parent in grade_tables for parent in element.iterancestors("table")):
                # Expanded full-row detail mirrors were intentionally excluded.
                cell = next(element.iterancestors("td", "th"), None)
                if (
                    cell is not None
                    and next(cell.iterancestors("table"), None) not in grade_tables
                ):
                    continue
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    for anchor in document.iter("a"):
        # A formative link outside the known tables is a new layout.
        if markup.detail_id(
            anchor.get("href"), FORMATIVE_DETAIL_PATH_PREFIX
        ) and not any(
            parent in grade_tables or parent in formative_tables
            for parent in anchor.iterancestors("table")
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if (
        not collection.subjects
        and not collection.point_subjects
        and not collection.descriptive
    ):
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
        formative,
        tuple(collection.point_results),
    )
