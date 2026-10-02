"""Original bounded count/event parsers; no seen state, hashing or persistence."""

import re
import zlib

from librus_python_api import markup
from librus_python_api.config import (
    NOTIFICATION_DESTINATIONS,
    NOTIFICATION_MAX_COUNT,
    NOTIFICATION_MAX_MENU_ITEMS,
    SCHEDULE_EMPTY_LABEL,
    SCHEDULE_EVENT_HEADERS,
    SCHEDULE_MAX_EVENTS,
    SCHEDULE_RESPONSE_VERSION,
    SCHOOL_MAX_CONTENT_LENGTH,
    SCHOOL_MAX_FIELD_LENGTH,
    SCHOOL_MAX_TOTAL_TEXT_LENGTH,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    Identity,
    NotificationCategory,
    NotificationCount,
    Observation,
    Person,
    RecentScheduleEvent,
    ScheduleEventResponse,
    ScheduleEventWire,
)
from librus_python_api.parsers import parse_page


def parse_notification_counts(body: bytes) -> tuple[NotificationCount, ...]:
    root = parse_page(body)
    menus = root.xpath("//div[@id='graphic-menu']/ul")
    if len(menus) != 1:
        raise LibrusError(ErrorKind.PARSE)
    rows = menus[0].xpath("./li")
    if len(rows) > NOTIFICATION_MAX_MENU_ITEMS:
        raise LibrusError(ErrorKind.LIMIT)
    items = []
    seen = set()
    for row in rows:
        links = row.xpath("./a")
        if len(links) > 4:
            raise LibrusError(ErrorKind.LIMIT)
        known = [
            a
            for a in links
            if a.get("href") in NOTIFICATION_DESTINATIONS
            and "counter" not in a.get("class", "").split()
        ]
        if not known:
            continue
        if len(known) != 1:
            raise LibrusError(ErrorKind.PARSE)
        category = NotificationCategory(NOTIFICATION_DESTINATIONS[known[0].get("href")])
        if category in seen:
            raise LibrusError(ErrorKind.PARSE)
        seen.add(category)
        counters = [a for a in links if "counter" in a.get("class", "").split()]
        marked = [
            e
            for e in row.iterdescendants()
            if isinstance(e.tag, str) and "counter" in e.get("class", "").split()
        ]
        if len(marked) != len(counters):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if len(counters) > 1:
            raise LibrusError(ErrorKind.PARSE)
        count = 0
        if counters:
            value = markup.text(counters[0], 16)
            if re.fullmatch(r"[0-9]{1,7}", value) is None:
                raise LibrusError(ErrorKind.PARSE)
            count = int(value)
            if count > NOTIFICATION_MAX_COUNT:
                raise LibrusError(ErrorKind.LIMIT)
        label = markup.text(known[0], SCHOOL_MAX_FIELD_LENGTH)
        if not label:
            raise LibrusError(ErrorKind.PARSE)
        items.append(NotificationCount(category, label, count))
    if not items:
        raise LibrusError(ErrorKind.PARSE)
    return tuple(items)


def parse_schedule_events(body: bytes) -> tuple[RecentScheduleEvent, ...]:
    root = parse_page(body)
    containers = root.xpath(
        "//div[contains(concat(' ',normalize-space(@class),' '),"
        "' container-background ')]"
    )
    if len(containers) != 1:
        raise LibrusError(ErrorKind.PARSE)
    tables = containers[0].xpath(".//table")
    empty = containers[0].xpath(".//p[@class='msgEmptyTable']")
    if tables and empty:
        raise LibrusError(ErrorKind.PARSE)
    if len(tables) != 1:
        empty = containers[0].xpath("./p[@class='msgEmptyTable']")
        if (
            not tables
            and len(empty) == 1
            and markup.text(empty[0]) == SCHEDULE_EMPTY_LABEL
        ):
            return ()
        raise LibrusError(ErrorKind.PARSE)
    rows = list(markup.rows(tables[0]))
    if len(rows) > SCHEDULE_MAX_EVENTS + 1:
        raise LibrusError(ErrorKind.LIMIT)
    header = markup.cells(rows[0]) if rows else []
    if (
        not rows
        or any(markup.colspan(c) != 1 for c in header)
        or tuple(markup.text(c).casefold() for c in header) != SCHEDULE_EVENT_HEADERS
    ):
        raise LibrusError(ErrorKind.PARSE)
    items = []
    total = 0
    for row in rows[1:]:
        cells = markup.cells(row)
        if (
            len(cells) != 4
            or any(c.tag != "td" or markup.colspan(c) != 1 for c in cells)
            or markup.in_header(row)
        ):
            raise LibrusError(ErrorKind.PARSE)
        # Display row numbers are not durable identities.
        values = [markup.text(c, SCHOOL_MAX_FIELD_LENGTH) for c in cells[:3]]
        if tuple(value.casefold() for value in values) == SCHEDULE_EVENT_HEADERS[:3]:
            raise LibrusError(ErrorKind.PARSE)
        data = markup.text(cells[3], SCHOOL_MAX_CONTENT_LENGTH, multiline=True)
        if not values[1] or not values[2]:
            raise LibrusError(ErrorKind.PARSE)
        total += sum(map(len, values)) + len(data)
        if total > SCHOOL_MAX_TOTAL_TEXT_LENGTH:
            raise LibrusError(ErrorKind.LIMIT)
        items.append(RecentScheduleEvent(values[1], values[2], data))
    return tuple(items)


def validate_response(
    response: ScheduleEventResponse, account: str, wire_limit: int
) -> None:
    if (
        not isinstance(response, ScheduleEventResponse)
        or type(response.version) is not int
        or response.version != SCHEDULE_RESPONSE_VERSION
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    wire = response.wire
    if (
        not isinstance(wire, ScheduleEventWire)
        or type(wire.body) is not bytes
        or len(wire.body) > wire_limit
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if (
        not isinstance(response.identity, Identity)
        or not isinstance(response.identity.observation, Observation)
        or not isinstance(response.identity.owner, Person)
        or not isinstance(response.identity.student, Person)
        or not isinstance(response.observation, Observation)
        or response.observation.account != account
        or response.identity.observation.account != account
        or response.observation.source != "consume_schedule_events"
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    for values in (wire.content_codings, wire.transfer_codings):
        if (
            type(values) is not tuple
            or len(values) > 128
            or any(type(v) is not str or len(v) > 8192 for v in values)
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
    if wire.content_type is not None and (
        type(wire.content_type) is not str or len(wire.content_type) > 8192
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)


def decode_payload(body: bytes, wire: ScheduleEventWire, limit: int) -> bytes:
    if (wire.content_type or "").split(";", 1)[0].strip().casefold() != "text/html":
        raise LibrusError(ErrorKind.PARSE)
    if (
        len(wire.content_codings) > 1
        or any(
            v.strip().casefold() not in ("identity", "gzip")
            for v in wire.content_codings
        )
        or len(wire.transfer_codings) > 1
        or any(v.strip().casefold() != "chunked" for v in wire.transfer_codings)
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if (
        not wire.content_codings
        or wire.content_codings[0].strip().casefold() == "identity"
    ):
        if len(body) > limit:
            raise LibrusError(ErrorKind.LIMIT)
        return body
    failed = False
    decoded = b""
    try:
        inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoded = inflater.decompress(body, limit + 1)
        if len(decoded) > limit:
            raise LibrusError(ErrorKind.LIMIT)
        if not inflater.eof or inflater.unused_data:
            failed = True
    except zlib.error:
        failed = True
    if failed:
        raise LibrusError(ErrorKind.PARSE)
    return decoded
