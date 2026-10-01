"""Independently authored bounded timetable parser with explicit week identity."""

import re
from dataclasses import replace
from datetime import date, time, timedelta

from lxml import html

from librus_python_api.config import (
    TIMETABLE_DATE_ATTRIBUTE,
    TIMETABLE_END_ATTRIBUTE,
    TIMETABLE_MAX_CHANGES_PER_SLOT,
    TIMETABLE_MAX_LESSONS_PER_SLOT,
    TIMETABLE_MAX_PERIODS,
    TIMETABLE_START_ATTRIBUTE,
    timetable_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.grade_parsers import _cells, _rows, _text
from librus_python_api.grade_records import _metadata
from librus_python_api.models import (
    TimetableChange,
    TimetableDay,
    TimetableInterval,
    TimetableLesson,
    TimetablePeriod,
)
from librus_python_api.parsers import parse_html_document


def _clock(value: str | None) -> time:
    if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value or ""):
        raise LibrusError(ErrorKind.PARSE)
    failed = False
    try:
        return time.fromisoformat(value or "")
    except ValueError:
        failed = True
    assert failed
    raise LibrusError(ErrorKind.PARSE)


def _interval(start: str | None, end: str | None) -> TimetableInterval:
    first, last = _clock(start), _clock(end)
    if first >= last:
        raise LibrusError(ErrorKind.PARSE)
    return TimetableInterval(first, last)


def _lesson(element: html.HtmlElement) -> TimetableLesson:
    subjects = list(element.iter("b"))
    if len(subjects) != 1:
        raise LibrusError(ErrorKind.PARSE)
    subject, rendered = _text(subjects[0]), _text(element)
    if not subject or not rendered.startswith(subject):
        raise LibrusError(ErrorKind.PARSE)
    remainder = rendered[len(subject) :].strip()
    if remainder and not remainder.startswith("-"):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    teacher = remainder.removeprefix("-").strip() or None
    return TimetableLesson(subject, teacher)


def _change(element: html.HtmlElement) -> TimetableChange:
    label = _text(element)
    anchors = list(element.iter("a"))
    if not label or len(anchors) > 1:
        raise LibrusError(ErrorKind.PARSE)
    if anchors and anchors[0].get("title") is None:
        raise LibrusError(ErrorKind.PARSE)
    metadata = _metadata(anchors[0]) if anchors else {}
    if any(len(key) > 1024 or len(value) > 1024 for key, value in metadata.items()):
        raise LibrusError(ErrorKind.LIMIT)
    return TimetableChange(label, tuple(metadata.items()))


def _content(
    cell: html.HtmlElement,
) -> tuple[tuple[TimetableLesson, ...], tuple[TimetableChange, ...]]:
    if list(cell.iter("table")):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    lessons: list[TimetableLesson] = []
    changes: list[TimetableChange] = []
    consumed: set[html.HtmlElement] = set()
    for node in cell.iter("div"):
        classes = set(node.get("class", "").split())
        if "text" in classes or {"center", "plan-lekcji-info"} <= classes:
            descendants = set(node.iter())
            if descendants.intersection(consumed):
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            consumed.update(descendants)
            if "text" in classes:
                lessons.append(_lesson(node))
            else:
                changes.append(_change(node))
            if (
                len(lessons) > TIMETABLE_MAX_LESSONS_PER_SLOT
                or len(changes) > TIMETABLE_MAX_CHANGES_PER_SLOT
            ):
                raise LibrusError(ErrorKind.LIMIT)
    for node in cell.iter():
        if not isinstance(node.tag, str):
            continue
        if node not in consumed and (
            (node.text or "").strip() or (node.tag == "a" and node.get("title"))
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if (node.tail or "").strip() and node.getparent() not in consumed:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return tuple(lessons), tuple(changes)


def _slot(
    cell: html.HtmlElement, number: int, monday: date
) -> tuple[int, TimetablePeriod]:
    if cell.get("colspan", "1") != "1" or cell.get("rowspan", "1") != "1":
        raise LibrusError(ErrorKind.PARSE)
    value = cell.get(TIMETABLE_DATE_ATTRIBUTE, "")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise LibrusError(ErrorKind.PARSE)
    failed = False
    day = None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        failed = True
    if failed or day is None or not 0 <= (day - monday).days < 7:
        raise LibrusError(ErrorKind.PARSE)
    interval = _interval(
        cell.get(TIMETABLE_START_ATTRIBUTE), cell.get(TIMETABLE_END_ATTRIBUTE)
    )
    lessons, changes = _content(cell)
    return (day - monday).days, TimetablePeriod(
        number, interval, lessons, changes, None
    )


def _period(row: html.HtmlElement, monday: date) -> tuple[TimetablePeriod, ...]:
    cells = _cells(row)
    slots = [cell for cell in cells if cell.get("id") == "timetableEntryBox"]
    numbers = [
        cell
        for cell in cells
        if cell.tag == "td"
        and cell not in slots
        and "center" in cell.get("class", "").split()
        and re.fullmatch(r"[0-9]{1,2}", _text(cell))
    ]
    if len(slots) != 7 or not 1 <= len(numbers) <= 2:
        raise LibrusError(ErrorKind.PARSE)
    values = {_text(cell) for cell in numbers}
    if len(values) != 1:
        raise LibrusError(ErrorKind.PARSE)
    raw_number = values.pop()
    selected: dict[int, TimetablePeriod] = {}
    for cell in slots:
        offset, period = _slot(cell, int(raw_number), monday)
        if offset in selected:
            raise LibrusError(ErrorKind.PARSE)
        selected[offset] = period
    return tuple(selected[index] for index in range(7))


def _recess(
    row: html.HtmlElement, previous: tuple[TimetablePeriod, ...]
) -> tuple[TimetablePeriod, ...]:
    cells = [
        cell
        for cell in _cells(row)
        if "center" in cell.get("class", "").split()
        and re.fullmatch(r"[0-9]{2}:[0-9]{2}\s*-\s*[0-9]{2}:[0-9]{2}", _text(cell))
    ]
    if (
        len(cells) != 1
        or not previous
        or any(p.next_recess is not None for p in previous)
    ):
        raise LibrusError(ErrorKind.PARSE)
    start, separator, end = _text(cells[0]).partition("-")
    if not separator:
        raise LibrusError(ErrorKind.PARSE)
    # Upstream recess clocks are reported values, not guaranteed positive gaps.
    # Preserve valid clocks without inventing a duration or rejecting a week.
    interval = TimetableInterval(_clock(start.strip()), _clock(end.strip()))
    return tuple(replace(period, next_recess=interval) for period in previous)


def _grid(document: html.HtmlElement) -> html.HtmlElement:
    tables = [
        t
        for t in document.iter("table")
        if {"decorated", "plan-lekcji"} <= set(t.get("class", "").split())
    ]
    if len(tables) != 1:
        raise LibrusError(ErrorKind.PARSE)
    table = tables[0]
    for node in document.iter():
        if not isinstance(node.tag, str):
            continue
        known = node.get("id") == "timetableEntryBox" or (
            node.tag == "div" and "plan-lekcji-info" in node.get("class", "").split()
        )
        if known and next(node.iterancestors("table"), None) is not table:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return table


def parse_timetable(body: bytes, monday: date) -> tuple[TimetableDay, ...]:
    timetable_form(monday)
    # The upstream repeats this particular slot ID. Other duplicate IDs and
    # parser repairs remain errors; semantic slot uniqueness is checked below.
    table = _grid(parse_html_document(body, repeatable_id="timetableEntryBox"))
    periods: list[tuple[TimetablePeriod, ...]] = []
    for row in _rows(table):
        classes = set(row.get("class", "").split())
        if "line1" in classes:
            current = _period(row, monday)
            if periods:
                for previous, following in zip(periods[-1], current, strict=True):
                    earliest = previous.interval.ends_at
                    if (
                        following.number <= previous.number
                        or following.interval.starts_at < earliest
                    ):
                        raise LibrusError(ErrorKind.PARSE)
            periods.append(current)
            if len(periods) > TIMETABLE_MAX_PERIODS:
                raise LibrusError(ErrorKind.LIMIT)
        elif "line0" in classes:
            if not periods:
                raise LibrusError(ErrorKind.PARSE)
            periods[-1] = _recess(row, periods[-1])
        elif any(cell.get("id") == "timetableEntryBox" for cell in _cells(row)):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if not periods:
        raise LibrusError(ErrorKind.PARSE)
    return tuple(
        TimetableDay(
            monday + timedelta(days=index), tuple(row[index] for row in periods)
        )
        for index in range(7)
    )
