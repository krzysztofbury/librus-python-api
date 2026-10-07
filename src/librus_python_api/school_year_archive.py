"""The school-year archive page (`/archiwum`), authored from an owner-authorized
structural observation; every fixture is synthetic.

One table holds every earlier school year: a year header row, a period row,
grade rows (subject marks or full-year descriptive text), then exactly one
behaviour section, one absences section and an empty footer, in that order.
A separate table lists achievements. Unknown layouts are unsupported;
contradictions inside the known layout are parse errors. The student's name in
the page header and the chart scripts are never read.
"""

import re
from typing import NoReturn

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    ARCHIVE_ABSENCE_LABELS,
    ARCHIVE_ABSENCES_HEADING,
    ARCHIVE_ACHIEVEMENT_HEADERS,
    ARCHIVE_ACHIEVEMENT_TABLE_CLASSES,
    ARCHIVE_BEHAVIOUR_HEADING,
    ARCHIVE_EMPTY_BOX_CLASSES,
    ARCHIVE_EMPTY_TITLE,
    ARCHIVE_MAX_ACHIEVEMENTS,
    ARCHIVE_MAX_DESCRIPTIVE,
    ARCHIVE_MAX_SUBJECTS,
    ARCHIVE_MAX_TEXT_LENGTH,
    ARCHIVE_MAX_TOTAL_TEXT_LENGTH,
    ARCHIVE_MAX_YEAR_HEADER_LENGTH,
    ARCHIVE_MAX_YEARS,
    ARCHIVE_PERIOD_LABELS,
    ARCHIVE_TABLE_CLASSES,
    ARCHIVE_YEAR_HEADER_TAGS,
    ARCHIVE_YEAR_PATTERN,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    ArchiveAbsences,
    ArchiveAchievement,
    ArchiveCounts,
    ArchiveDescriptive,
    ArchiveMarks,
    ArchiveSubject,
    ArchiveYear,
)
from librus_python_api.parsers import parse_page

_YEAR = re.compile(ARCHIVE_YEAR_PATTERN)
_COUNT = re.compile(r"[0-9]{1,6}")


def _fail(kind: ErrorKind) -> NoReturn:
    raise LibrusError(kind)


class _Text:
    """Rendered cell text under one total budget for the whole page."""

    def __init__(self) -> None:
        self.used = 0

    def __call__(
        self,
        cell: html.HtmlElement,
        *,
        multiline: bool = False,
        limit: int = markup.FIELD_LENGTH,
    ) -> str:
        value = markup.text(cell, limit, multiline=multiline)
        self.used += len(value)
        if self.used > ARCHIVE_MAX_TOTAL_TEXT_LENGTH:
            _fail(ErrorKind.LIMIT)
        return value


def _plain(cell: html.HtmlElement, allowed: frozenset[str] = frozenset()) -> None:
    """Only the observed child vocabulary; other markup is a new layout."""
    for node in cell.iterdescendants():
        if isinstance(node.tag, str) and node.tag not in allowed:
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    for node in cell.iter():
        if any(name == "title" or name.startswith("on") for name in node.attrib):
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)


def _td(cells: list[html.HtmlElement]) -> None:
    if any(cell.tag != "td" for cell in cells):
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)


def _classes(table: html.HtmlElement) -> set[str]:
    return set(table.get("class", "").split())


def _first_cells(table: html.HtmlElement) -> list[html.HtmlElement]:
    first = next(markup.rows(table), None)
    return [] if first is None else markup.cells(first)


def _is_archive(table: html.HtmlElement) -> bool:
    cells = _first_cells(table)
    return (
        len(cells) >= 2
        and markup.text(cells[0]) == ""
        and all(
            _YEAR.fullmatch(markup.text(cell, ARCHIVE_MAX_YEAR_HEADER_LENGTH))
            for cell in cells[1:]
        )
    )


def _is_achievement_list(table: html.HtmlElement) -> bool:
    cells = _first_cells(table)
    return [
        markup.text(cell, ARCHIVE_MAX_YEAR_HEADER_LENGTH).casefold() for cell in cells
    ] == list(ARCHIVE_ACHIEVEMENT_HEADERS)


def _in_footer(row: html.HtmlElement) -> bool:
    return next(row.iterancestors("tfoot"), None) is not None


def _years(header: html.HtmlElement, text: _Text) -> list[tuple[str, str, int]]:
    cells = markup.cells(header)
    _td(cells)
    _plain(cells[0])
    if len(cells) - 1 > ARCHIVE_MAX_YEARS:
        _fail(ErrorKind.LIMIT)
    if markup.colspan(cells[0]) != 1:
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    years: list[tuple[str, str, int]] = []
    for cell in cells[1:]:
        if markup.colspan(cell) != 3:
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        _plain(cell, ARCHIVE_YEAR_HEADER_TAGS)
        match = _YEAR.fullmatch(text(cell, limit=ARCHIVE_MAX_YEAR_HEADER_LENGTH))
        if match is None:
            _fail(ErrorKind.PARSE)
        first, second = int(match["first"]), int(match["second"])
        if len(match["class_name"]) > markup.FIELD_LENGTH:
            _fail(ErrorKind.LIMIT)
        if second != first + 1 or any(first == seen for _, _, seen in years):
            _fail(ErrorKind.PARSE)
        years.append((match["class_name"], f"{first}/{second}", first))
    return years


def _check_periods(row: html.HtmlElement, count: int, text: _Text) -> None:
    cells = markup.cells(row)
    _td(cells)
    for cell in cells:
        _plain(cell)
    if (
        len(cells) != 1 + 3 * count
        or any(markup.colspan(cell) != 1 for cell in cells)
        or text(cells[0])
        or [text(cell).casefold() for cell in cells[1:]]
        != list(ARCHIVE_PERIOD_LABELS) * count
    ):
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)


class _Body:
    """The section order: grades, behaviour, absences, footer."""

    def __init__(self, count: int, text: _Text) -> None:
        self.count = count
        self.text = text
        self.state = "grades"
        self.labels: set[str] = set()
        self.subjects: list[tuple[str, list[ArchiveMarks]]] = []
        self.descriptive: list[tuple[str, list[str]]] = []
        self.behaviour: list[tuple[str, str]] = []
        self.absences: dict[str, list[ArchiveCounts]] = {}

    def read(self, row: html.HtmlElement) -> None:
        cells = markup.cells(row)
        spans = [markup.colspan(cell) for cell in cells]
        full = [1 + 3 * self.count]
        heading = spans == full and "bolded" in row.get("class", "").split()
        if self.state == "grades":
            if heading:
                self._heading(cells, ARCHIVE_BEHAVIOUR_HEADING, "behaviour")
            else:
                self._grade(cells, spans)
        elif self.state == "behaviour":
            self._behaviour(cells, spans, heading)
        elif self.state == "absences_heading":
            if not heading:
                _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
            self._heading(cells, ARCHIVE_ABSENCES_HEADING, "absences")
        elif self.state == "absences":
            if spans == full and not heading:
                self._footer(cells)
            else:
                self._absence(cells, spans)
        else:
            _fail(ErrorKind.PARSE)

    def _heading(self, cells: list[html.HtmlElement], label: str, state: str) -> None:
        _td(cells)
        _plain(cells[0])
        if self.text(cells[0]).casefold() != label:
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        self.state = state

    def _label(self, cells: list[html.HtmlElement]) -> str:
        if not cells or cells[0].tag != "th":
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        _plain(cells[0])
        return self.text(cells[0])

    def _values(
        self,
        cells: list[html.HtmlElement],
        *,
        multiline: bool = False,
        limit: int = markup.FIELD_LENGTH,
    ) -> list[str]:
        _td(cells)
        values = []
        for cell in cells:
            _plain(cell, frozenset({"br"}) if multiline else frozenset())
            values.append(self.text(cell, multiline=multiline, limit=limit))
        return values

    def _grade(self, cells: list[html.HtmlElement], spans: list[int]) -> None:
        label = self._label(cells)
        if not label:
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        if spans == [1] * (1 + 3 * self.count):
            values = self._values(cells[1:])
            marks = [
                ArchiveMarks(*values[3 * i : 3 * i + 3]) for i in range(self.count)
            ]
            self.subjects.append((label, marks))
            limit, size = ARCHIVE_MAX_SUBJECTS, len(self.subjects)
        elif spans == [1] + [3] * self.count:
            texts = self._values(
                cells[1:], multiline=True, limit=ARCHIVE_MAX_TEXT_LENGTH
            )
            self.descriptive.append((label, texts))
            limit, size = ARCHIVE_MAX_DESCRIPTIVE, len(self.descriptive)
        else:
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        if label in self.labels:
            _fail(ErrorKind.PARSE)
        self.labels.add(label)
        if size > limit:
            _fail(ErrorKind.LIMIT)

    def _behaviour(
        self, cells: list[html.HtmlElement], spans: list[int], heading: bool
    ) -> None:
        if heading or spans != [1] + [1, 2] * self.count or self._label(cells):
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        values = self._values(cells[1:])
        self.behaviour = [(values[2 * i], values[2 * i + 1]) for i in range(self.count)]
        self.state = "absences_heading"

    def _absence(self, cells: list[html.HtmlElement], spans: list[int]) -> None:
        field = ARCHIVE_ABSENCE_LABELS.get(self._label(cells).casefold())
        if field is None or spans != [1] * (1 + 3 * self.count):
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        if field in self.absences:
            _fail(ErrorKind.PARSE)
        values = self._values(cells[1:])
        if not all(_COUNT.fullmatch(value) for value in values):
            _fail(ErrorKind.PARSE)
        numbers = [int(value) for value in values]
        self.absences[field] = [
            ArchiveCounts(*numbers[3 * i : 3 * i + 3]) for i in range(self.count)
        ]

    def _footer(self, cells: list[html.HtmlElement]) -> None:
        _td(cells)
        _plain(cells[0])
        if self.text(cells[0]) or len(self.absences) != len(ARCHIVE_ABSENCE_LABELS):
            _fail(ErrorKind.PARSE)
        self.state = "end"


def _archive(table: html.HtmlElement, text: _Text) -> tuple[ArchiveYear, ...]:
    rows = list(markup.rows(table))
    if len(rows) < 2:
        _fail(ErrorKind.PARSE)
    years = _years(rows[0], text)
    _check_periods(rows[1], len(years), text)
    body = _Body(len(years), text)
    for row in rows[2:]:
        body.read(row)
    if body.state != "end":
        _fail(ErrorKind.PARSE)
    return tuple(
        ArchiveYear(
            class_name=class_name,
            school_year=school_year,
            first_year=first_year,
            subjects=tuple(
                ArchiveSubject(label, marks[i]) for label, marks in body.subjects
            ),
            descriptive=tuple(
                ArchiveDescriptive(label, texts[i]) for label, texts in body.descriptive
            ),
            behaviour_first_semester=body.behaviour[i][0],
            behaviour_second_semester_and_year_end=body.behaviour[i][1],
            absences=ArchiveAbsences(
                unexcused=body.absences["unexcused"][i],
                excused=body.absences["excused"][i],
                late=body.absences["late"][i],
            ),
        )
        for i, (class_name, school_year, first_year) in enumerate(years)
    )


def _achievements(
    table: html.HtmlElement, text: _Text
) -> tuple[ArchiveAchievement, ...]:
    items: list[ArchiveAchievement] = []
    rows = list(markup.rows(table))
    headers = markup.cells(rows[0])
    _td(headers)
    for cell in headers:
        _plain(cell)
        if markup.colspan(cell) != 1:
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        text(cell)
    finished = False
    for row in rows[1:]:
        if finished:
            _fail(ErrorKind.PARSE)
        cells = markup.cells(row)
        _td(cells)
        if _in_footer(row):
            if len(cells) != 1 or text(cells[0]):
                _fail(ErrorKind.PARSE)
            _plain(cells[0])
            if markup.colspan(cells[0]) != 4:
                _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
            finished = True
            continue
        if len(cells) != 4 or any(markup.colspan(cell) != 1 for cell in cells):
            _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
        for i, cell in enumerate(cells):
            _plain(cell, frozenset({"br"}) if i == 3 else frozenset())
        items.append(
            ArchiveAchievement(
                day=markup.civil_date(text(cells[0])),
                class_name=text(cells[1]),
                category=text(cells[2]),
                text=text(cells[3], multiline=True, limit=ARCHIVE_MAX_TEXT_LENGTH),
            )
        )
        if len(items) > ARCHIVE_MAX_ACHIEVEMENTS:
            _fail(ErrorKind.LIMIT)
    return tuple(items)


def _explicit_empty(document: html.HtmlElement) -> bool:
    notices = []
    for box in document.iter("div"):
        if not ARCHIVE_EMPTY_BOX_CLASSES <= _classes(box):
            continue
        parent = box.getparent()
        if parent is None or "container-background" not in _classes(parent):
            continue
        for head in box:
            if head.tag != "div" or "warning-head" not in _classes(head):
                continue
            for title in head:
                if title.tag == "span" and "warning-title" in _classes(title):
                    _plain(title)
                    if markup.text(title).casefold() != ARCHIVE_EMPTY_TITLE:
                        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
                    notices.append(title)
    if len(notices) > 1:
        _fail(ErrorKind.PARSE)
    if notices and any("decorated" in _classes(t) for t in document.iter("table")):
        _fail(ErrorKind.PARSE)
    return bool(notices)


def _check_nesting(table: html.HtmlElement, *, chart_trailer: bool = False) -> None:
    if next(table.iterancestors("table"), None) is not None:
        _fail(ErrorKind.PARSE)
    nested = [node for node in table.iter("table") if node is not table]
    if not nested:
        return
    # Live HTML nests the post-footer charts in a stray opening table. Permit
    # that single rowless trailing container, never nested tabular data.
    if not chart_trailer or len(nested) != 1:
        _fail(ErrorKind.PARSE)
    trailer = nested[0]
    previous = trailer.getprevious()
    if (
        trailer.getparent() is not table
        or trailer.getnext() is not None
        or previous is None
        or previous.tag != "tfoot"
        or trailer.attrib
        or any(
            node.tag in {"tr", "td", "th", "thead", "tbody", "tfoot"}
            for node in trailer.iterdescendants()
        )
    ):
        _fail(ErrorKind.PARSE)


def parse_school_year_archive(
    body: bytes,
) -> tuple[tuple[ArchiveYear, ...], tuple[ArchiveAchievement, ...]]:
    document = parse_page(body)
    archives = [t for t in document.iter("table") if _is_archive(t)]
    lists = [t for t in document.iter("table") if _is_achievement_list(t)]
    if _explicit_empty(document):
        if archives or lists:
            _fail(ErrorKind.PARSE)
        return (), ()
    if len(archives) != 1 or len(lists) != 1:
        _fail(ErrorKind.PARSE)
    archive, achievements = archives[0], lists[0]
    _check_nesting(archive)
    _check_nesting(achievements, chart_trailer=True)
    if not ARCHIVE_TABLE_CLASSES <= _classes(archive) or not (
        ARCHIVE_ACHIEVEMENT_TABLE_CLASSES <= _classes(achievements)
    ):
        _fail(ErrorKind.UNSUPPORTED_CAPABILITY)
    text = _Text()
    return _archive(archive, text), _achievements(achievements, text)
