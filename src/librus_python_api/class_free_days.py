"""Bounded gateway class free days from independently observed JSON structure."""

import re
from datetime import date
from typing import Any

from librus_python_api.config import CLASS_FREE_DAYS_MAX_RECORDS
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import ClassFreeDay
from librus_python_api.parsers import decode_json


def _identifier(value: Any) -> str:
    if type(value) is not int or value < 0 or len(str(value)) > 64:
        raise LibrusError(ErrorKind.PARSE)
    return str(value)


def _reference(value: Any) -> str:
    if not isinstance(value, dict):
        raise LibrusError(ErrorKind.PARSE)
    return _identifier(value.get("Id"))


def _day(value: Any) -> date:
    result = None
    if type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            result = date.fromisoformat(value)
        except ValueError:
            pass
    if result is None:
        raise LibrusError(ErrorKind.PARSE)
    return result


def parse_class_free_days(body: bytes) -> tuple[ClassFreeDay, ...]:
    data = decode_json(body)
    if not isinstance(data, dict) or not isinstance(data.get("ClassFreeDays"), list):
        raise LibrusError(ErrorKind.PARSE)
    rows = data["ClassFreeDays"]
    if len(rows) > CLASS_FREE_DAYS_MAX_RECORDS:
        raise LibrusError(ErrorKind.LIMIT)
    items: list[ClassFreeDay] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise LibrusError(ErrorKind.PARSE)
        identifier = _identifier(row.get("Id"))
        start, end = _day(row.get("DateFrom")), _day(row.get("DateTo"))
        first, last = row.get("LessonNoFrom"), row.get("LessonNoTo")
        if "LessonNoFrom" in row or "LessonNoTo" in row:
            if (
                type(first) is not int
                or type(last) is not int
                or not 0 <= first <= last <= 99
            ):
                raise LibrusError(ErrorKind.PARSE)
        if identifier in seen or start > end:
            raise LibrusError(ErrorKind.PARSE)
        seen.add(identifier)
        items.append(
            ClassFreeDay(
                identifier,
                _reference(row.get("Class")),
                _reference(row.get("Type")),
                start,
                end,
                first,
                last,
            )
        )
    return tuple(items)
