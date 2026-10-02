"""Ordinary agenda/homework parsing; no script execution or read-once routes."""

import calendar
import re
from datetime import date, datetime, time
from typing import Literal

from lxml import html

from librus_python_api import markup
from librus_python_api.config import (
    AGENDA_DESCRIPTION_LABEL,
    AGENDA_DETAIL_PATH_PREFIX,
    AGENDA_TOOLTIP_LABELS,
    HOMEWORK_COLUMNS,
    HOMEWORK_DETAIL_PATH_PREFIX,
    HOMEWORK_DONE_PATTERN,
    HOMEWORK_MAX_COLUMNS,
    SCHOOL_MAX_CONTENT_LENGTH,
    SCHOOL_MAX_DETAIL_FIELDS,
    SCHOOL_MAX_FIELD_LENGTH,
    SCHOOL_MAX_ITEMS,
    SCHOOL_MAX_TOOLTIP_LENGTH,
    SCHOOL_MAX_TOOLTIP_LINES,
    SCHOOL_MAX_TOTAL_TEXT_LENGTH,
    WEEKDAY_LABELS,
    agenda_form,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    AgendaDay,
    AgendaEvent,
    HomeworkItem,
    SchoolReference,
)
from librus_python_api.parsers import page_notices, parse_html_document, parse_page


def school_reference(
    nodes: list[html.HtmlElement], kind: Literal["agenda", "homework"], account: str
) -> SchoolReference | None:
    """Find the single detail link.

    Agenda cells must not carry any other handler. Homework rows also carry a
    mark-done button; the library never follows handlers, so it is inert here.
    """
    prefix = (
        AGENDA_DETAIL_PATH_PREFIX if kind == "agenda" else HOMEWORK_DETAIL_PATH_PREFIX
    )
    found: set[str] = set()
    for node in nodes:
        if not isinstance(node.tag, str):
            continue
        action = node.get("onclick", "")
        if len(action) > 4096:
            raise LibrusError(ErrorKind.LIMIT)
        if not action or (kind == "homework" and prefix not in action):
            continue
        paths = re.findall(r"['\"](" + re.escape(prefix) + r"[0-9]{1,64})['\"]", action)
        if len(paths) != 1:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        found.add(paths[0].removeprefix(prefix))
    if len(found) > 1:
        raise LibrusError(ErrorKind.PARSE)
    return SchoolReference(kind, next(iter(found)), account) if found else None


def _metadata(
    cell: html.HtmlElement,
) -> tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]]:
    raw = cell.get("title", "")
    if len(raw) > SCHOOL_MAX_TOOLTIP_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    parts = re.split(r"<br\s*/?>|\n", raw, flags=re.I)
    if len(parts) > SCHOOL_MAX_TOOLTIP_LINES:
        raise LibrusError(ErrorKind.LIMIT)
    fields: dict[str, str] = {}
    notes = []
    describing = False
    for part in parts:
        if not part.strip():
            continue
        rendered = (
            markup.text(parse_html_document(part.encode()), SCHOOL_MAX_FIELD_LENGTH)
            if "<" in part
            else " ".join(part.split())
        )
        if len(rendered) > SCHOOL_MAX_FIELD_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        label, separator, value = rendered.partition(":")
        label, value = label.strip(), value.strip()
        if describing and not (separator and label in AGENDA_TOOLTIP_LABELS):
            fields[AGENDA_DESCRIPTION_LABEL] += "\n" + rendered
            continue
        describing = separator != "" and label == AGENDA_DESCRIPTION_LABEL
        if not separator:
            notes.append(rendered)
        elif not label or label in fields:
            raise LibrusError(ErrorKind.PARSE)
        else:
            fields[label] = value
    text = (
        markup.text(
            parse_html_document(raw.encode()), SCHOOL_MAX_TOOLTIP_LENGTH, multiline=True
        )
        if raw
        else ""
    )
    return text, tuple(fields.items()), tuple(notes)


def _event(cell: html.HtmlElement, day: date, account: str) -> AgendaEvent:
    spans = list(cell.iter("span"))
    if (
        len(spans) > 1
        or next(cell.iter("table"), None) is not None
        or cell.get("rowspan", "1") != "1"
        or cell.get("colspan", "1") != "1"
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    text = markup.text(cell, SCHOOL_MAX_CONTENT_LENGTH, multiline=True)
    if not text:
        raise LibrusError(ErrorKind.PARSE)
    subject = markup.text(spans[0], SCHOOL_MAX_FIELD_LENGTH) if spans else None
    lines = text.splitlines()
    header = lines[0].removesuffix(subject).rstrip(" ,") if subject else lines[0]
    number = re.fullmatch(
        r"(?:Lekcja(?: nr)?|Nr(?: lekcji)?|Numer(?: lekcji)?):\s*([0-9]{1,2})[,]?",
        header,
        re.I,
    )
    clock = re.fullmatch(r"(?:Godzina:\s*)?([0-9]{2}:[0-9]{2})[,]?", header, re.I)
    title = lines[0]
    if subject and subject in lines:
        index = lines.index(subject)
        title = lines[index + 1] if index + 1 < len(lines) else subject
    elif len(lines) > 1 and (number or clock):
        title = lines[1]
    if len(title) > SCHOOL_MAX_FIELD_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    metadata_text, metadata, notes = _metadata(cell)
    return AgendaEvent(
        day,
        title,
        subject or None,
        text,
        int(number[1]) if number else None,
        _clock(clock[1]) if clock else None,
        metadata_text,
        metadata,
        notes,
        school_reference(list(cell.iter()), "agenda", account),
    )


def parse_agenda(
    body: bytes, year: int, month: int, account: str
) -> tuple[AgendaDay, ...]:
    agenda_form(year, month)
    document = parse_page(body)
    nodes = document.xpath(
        '//div[contains(concat(" ",normalize-space(@class)," ")," kalendarz-dzien ")]'
    )
    expected = calendar.monthrange(year, month)[1]
    if len(nodes) != expected:
        raise LibrusError(ErrorKind.PARSE)
    days: dict[int, AgendaDay] = {}
    count = total = 0
    for node in nodes:
        markers = node.xpath(
            './/div[contains(concat(" ",normalize-space(@class)," "),'
            '" kalendarz-numer-dnia ")]'
        )
        if len(markers) != 1 or not re.fullmatch(
            r"[0-9]{1,2}", markup.text(markers[0], 2)
        ):
            raise LibrusError(ErrorKind.PARSE)
        number = int(markup.text(markers[0], 2))
        if not 1 <= number <= expected or number in days:
            raise LibrusError(ErrorKind.PARSE)
        events = []
        for row in node.iter("tr"):
            cells = markup.cells(row)
            if len(cells) != 1 or cells[0].tag != "td":
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            item = _event(cells[0], date(year, month, number), account)
            count += 1
            total += (
                len(item.text)
                + len(item.metadata_text)
                + sum(len(k) + len(v) for k, v in item.metadata)
                + sum(map(len, item.metadata_notes))
            )
            if count > SCHOOL_MAX_ITEMS or total > SCHOOL_MAX_TOTAL_TEXT_LENGTH:
                raise LibrusError(ErrorKind.LIMIT)
            events.append(item)
        days[number] = AgendaDay(date(year, month, number), tuple(events))
    return tuple(days[number] for number in range(1, expected + 1))


def _clock(value: str) -> time:
    if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    try:
        return time.fromisoformat(value)
    except ValueError:
        pass
    raise LibrusError(ErrorKind.PARSE)


def _iso_date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise LibrusError(ErrorKind.PARSE)
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    raise LibrusError(ErrorKind.PARSE)


def _dated(value: str, weekday: str) -> date:
    day = _iso_date(value)
    # The adjacent weekday cell guards against silent column drift.
    if weekday != WEEKDAY_LABELS[day.weekday()]:
        raise LibrusError(ErrorKind.PARSE)
    return day


def _homework_columns(table: html.HtmlElement) -> list[str]:
    """Expand the header into one field name per body cell."""
    headers = [
        row
        for row in markup.rows(table)
        if next(row.iterancestors("thead"), None) is not None
    ]
    if len(headers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    columns: list[str] = []
    for cell in markup.cells(headers[0]):
        field = HOMEWORK_COLUMNS.get(markup.text(cell, SCHOOL_MAX_FIELD_LENGTH))
        if field is None:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        span = 2 if field in ("assigned", "due") else 1
        if cell.get("colspan", "1") != str(span) or field in columns:
            raise LibrusError(ErrorKind.PARSE)
        columns.extend([field] if span == 1 else [field, field + "_weekday"])
    required = {"subject", "teacher", "topic", "category", "assigned", "due"}
    if not required <= set(columns) or len(columns) > HOMEWORK_MAX_COLUMNS:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return columns


def _marked_done_at(options: html.HtmlElement | None) -> datetime | None:
    if options is None:
        return None
    found = []
    for image in options.iter("img"):
        title = image.get("title", "")
        if title.startswith("Zadanie oznaczono jako wykonane"):
            match = re.fullmatch(HOMEWORK_DONE_PATTERN, title)
            if match is None:
                raise LibrusError(ErrorKind.PARSE)
            found.append(datetime.combine(_iso_date(match[1]), _clock(match[2])))
    if len(found) > 1:
        raise LibrusError(ErrorKind.PARSE)
    return found[0] if found else None


def _homework_row(
    row: html.HtmlElement, columns: list[str], account: str
) -> HomeworkItem:
    cells = markup.cells(row)
    if len(cells) != len(columns) or any(
        c.tag != "td" or c.get("colspan", "1") != "1" or c.get("rowspan", "1") != "1"
        for c in cells
    ):
        raise LibrusError(ErrorKind.PARSE)
    by_field = dict(zip(columns, cells, strict=True))
    values = {
        field: markup.text(cell, SCHOOL_MAX_FIELD_LENGTH)
        for field, cell in by_field.items()
        if field != "options"
    }
    return HomeworkItem(
        values["subject"],
        values["teacher"],
        values["topic"],
        values["category"],
        _dated(values["assigned"], values["assigned_weekday"]),
        _dated(values["due"], values["due_weekday"]),
        values.get("submission_status"),
        _marked_done_at(by_field.get("options")),
        school_reference(list(row.iter()), "homework", account),
    )


def parse_homework(body: bytes, account: str) -> tuple[HomeworkItem, ...]:
    document = parse_page(body)
    tables = [
        t
        for t in document.iter("table")
        if {"decorated", "myHomeworkTable"} <= set(t.get("class", "").split())
    ]
    markers = document.xpath(
        '//p[contains(concat(" ",normalize-space(@class)," ")," msgEmptyTable ")]'
    )
    if len(tables) > 1 or len(markers) > 1 or (tables and markers):
        raise LibrusError(ErrorKind.PARSE)
    if not tables:
        # An unrecognized notice next to an empty marker is not a valid empty list.
        if len(markers) != 1 or page_notices(document):
            raise LibrusError(ErrorKind.PARSE)
        return ()
    table = tables[0]
    if len(list(table.iter("table"))) != 1:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    columns = _homework_columns(table)
    items: list[HomeworkItem] = []
    total = 0
    for row in markup.rows(table):
        if {"line0", "line1"}.intersection(row.get("class", "").split()):
            item = _homework_row(row, columns, account)
            total += sum(
                len(markup.text(c, SCHOOL_MAX_FIELD_LENGTH)) for c in markup.cells(row)
            )
            if len(items) >= SCHOOL_MAX_ITEMS or total > SCHOOL_MAX_TOTAL_TEXT_LENGTH:
                raise LibrusError(ErrorKind.LIMIT)
            items.append(item)
        elif next(row.iterancestors("thead"), None) is None and markup.text(
            row, SCHOOL_MAX_FIELD_LENGTH
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if not items:
        raise LibrusError(ErrorKind.PARSE)
    return tuple(items)


def parse_school_detail(
    body: bytes,
) -> tuple[str | None, tuple[tuple[str, str], ...], tuple[str, ...]]:
    document = parse_page(body)
    containers = document.xpath(
        '//div[contains(concat(" ",normalize-space(@class)," "),'
        '" container-background ")]'
    )
    if len(containers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    tables = list(containers[0].iter("table"))
    if len(tables) != 1:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    title = None
    fields: dict[str, str] = {}
    labels: set[str] = set()
    notes = []
    total = 0
    for row in markup.rows(tables[0]):
        cells = markup.cells(row)
        if (
            len(cells) == 1
            and cells[0].tag == "td"
            and cells[0].get("colspan", "1") == "2"
        ):
            value = markup.text(cells[0], SCHOOL_MAX_CONTENT_LENGTH, multiline=True)
            if next(row.iterancestors("thead"), None) is not None:
                if title is not None:
                    raise LibrusError(ErrorKind.PARSE)
                title = value or None
            elif value:
                notes.append(value)
            total += len(value)
        elif len(cells) == 2 and cells[0].tag in {"th", "td"} and cells[1].tag == "td":
            if any(
                c.get("colspan", "1") != "1" or c.get("rowspan", "1") != "1"
                for c in cells
            ):
                raise LibrusError(ErrorKind.PARSE)
            label = markup.text(cells[0], SCHOOL_MAX_FIELD_LENGTH)
            canonical = label.rstrip(":").strip().casefold()
            if not canonical or canonical in labels:
                raise LibrusError(ErrorKind.PARSE)
            labels.add(canonical)
            value = markup.text(cells[1], SCHOOL_MAX_CONTENT_LENGTH, multiline=True)
            fields[label] = value
            total += len(label) + len(value)
        elif markup.text(row, SCHOOL_MAX_FIELD_LENGTH):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if (
            len(fields) + len(notes) > SCHOOL_MAX_DETAIL_FIELDS
            or total > SCHOOL_MAX_TOTAL_TEXT_LENGTH
        ):
            raise LibrusError(ErrorKind.LIMIT)
    if not fields:
        raise LibrusError(ErrorKind.PARSE)
    return title, tuple(fields.items()), tuple(notes)
