"""Original bounded parsers for new-schema descriptive grades from the gateway.

The grades page of a school on the new descriptive grading schema renders a
subject table whose semester cells are empty; the page script then loads the
grades from gateway JSON routes. Routes and field names come from public client
code and the official page script, not from an observed populated response,
so every unexpected shape fails instead of producing a partial collection.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import Annotated, Any, Literal

from lxml import html
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from librus_python_api import markup
from librus_python_api.config import (
    DESCRIPTIVE_IDENTIFIER,
    DESCRIPTIVE_MAX_NAME_LENGTH,
    DESCRIPTIVE_MAX_SUBJECTS,
    DESCRIPTIVE_MAX_USERS,
    DESCRIPTIVE_ROW_CLASS,
    DESCRIPTIVE_TABLE_CLASS,
    GRADE_MAX_METADATA_LENGTH,
    GRADE_MAX_RECORDS,
    GRADE_MAX_SUBJECTS,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.grade_records import read_grade_records
from librus_python_api.models import DescriptiveGrade, GradeKind, GradeRecords
from librus_python_api.parsers import decode_json, parse_page

_WIRE = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
# Identifiers placed in a request path use the strict transport pattern.
_PathIdentifier = Annotated[
    str, Field(pattern="^" + DESCRIPTIVE_IDENTIFIER.pattern + "$")
]
# Identifiers only used for lookups stay opaque, bounded strings.
_Reference = Annotated[str, Field(min_length=1, max_length=128)]
_Name = Annotated[str, Field(max_length=DESCRIPTIVE_MAX_NAME_LENGTH)]
_Text = Annotated[str, Field(max_length=GRADE_MAX_METADATA_LENGTH)]
_DATE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,9})?)?"
    r"(?:Z|[+-][0-9]{2}:?[0-9]{2})?)?"
)
# Keys (lower case, without separators) that, in any object beside `data`,
# show that the collection continues on another page.
_TOTAL_KEYS = frozenset(
    {
        "total",
        "totalcount",
        "totalitems",
        "totalrecords",
        "totalresults",
        "count",
        "itemcount",
        "itemscount",
        "recordcount",
    }
)
_PAGE_COUNT_KEYS = frozenset(
    {"pages", "totalpages", "pagecount", "pagescount", "lastpage", "numberofpages"}
)
_NEXT_KEYS = frozenset({"next", "nextpage", "nexturl", "nextpageurl", "nextlink"})
_MORE_KEYS = frozenset({"hasmore", "hasnext", "hasnextpage", "more"})
_PAGE_SIZE_KEYS = frozenset(
    {"limit", "perpage", "pagesize", "itemsperpage", "pagelimit"}
)


class _TokenInfoWire(BaseModel):
    model_config = _WIRE
    UserIdentifier: _PathIdentifier
    UserType: int | None = None


class _UserInfoWire(BaseModel):
    model_config = _WIRE
    IdentifierOfStudentAssignedWithUser: _PathIdentifier | None = None

    @field_validator("IdentifierOfStudentAssignedWithUser", mode="before")
    @classmethod
    def empty_is_absent(cls, value: Any) -> Any:
        # The page script treats an empty assignment as the user's own grades.
        return None if value == "" else value


class _AreaWire(BaseModel):
    model_config = _WIRE
    name: _Text | None = None


class _ScaleValueWire(BaseModel):
    model_config = _WIRE
    value: _Text | None = None


class _PartialGradeWire(BaseModel):
    model_config = _WIRE
    subjectId: _Reference
    teacherId: _Reference | None = None
    addedBy: _Reference | None = None
    area: _AreaWire | None = None
    scaleValue: _ScaleValueWire | None = None
    content: _Text | None = None
    comments: _Text | None = None
    date: Annotated[str, Field(max_length=64)]
    semester: Literal[1, 2]

    @field_validator("semester", mode="before")
    @classmethod
    def reject_boolean_semester(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Invalid semester type")
        return value


class _PartialGradesWire(BaseModel):
    model_config = _WIRE
    data: list[_PartialGradeWire]


class _SubjectWire(BaseModel):
    model_config = _WIRE
    identifier: _Reference
    numericIdentifier: Annotated[int, Field(ge=0, lt=10**18)] | None = None
    name: _Name | None = None


class _SubjectsWire(BaseModel):
    model_config = _WIRE
    data: list[_SubjectWire]


class _UserWire(BaseModel):
    model_config = _WIRE
    AccountId: _Reference
    FirstName: _Name | None = None
    LastName: _Name | None = None


class _UsersWire(BaseModel):
    model_config = _WIRE
    Users: list[_UserWire]


@dataclass(frozen=True, slots=True)
class PartialGrade:
    """One validated gateway record before subject and person resolution."""

    subject_id: str = field(repr=False)
    teacher_id: str | None = field(repr=False)
    author_id: str | None = field(repr=False)
    area: str | None = field(repr=False)
    scale_value: str | None = field(repr=False)
    content: str | None = field(repr=False)
    comments: str | None = field(repr=False)
    day: date = field(repr=False)
    semester: Literal[1, 2]


@dataclass(frozen=True, slots=True)
class GatewaySubject:
    numeric_id: int | None
    name: str | None = field(repr=False)


def _validate[M: BaseModel](wire: type[M], data: object) -> M:
    failed: ErrorKind | None = None
    result = None
    try:
        result = wire.model_validate(data)
    except ValidationError as error:
        too_long = any(item["type"] == "string_too_long" for item in error.errors())
        failed = ErrorKind.LIMIT if too_long else ErrorKind.PARSE
    if failed is not None or result is None:
        raise LibrusError(failed or ErrorKind.PARSE)
    return result


def _decode_collection(body: bytes, key: str, maximum: int) -> dict[str, Any]:
    data = decode_json(body)
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise LibrusError(ErrorKind.PARSE)
    if len(data[key]) > maximum:
        raise LibrusError(ErrorKind.LIMIT)
    return data


def _count(value: Any) -> int | None:
    if type(value) is int:
        return value
    if type(value) is str and re.fullmatch(r"[0-9]{1,18}", value):
        return int(value)
    return None


def _continues(envelope: dict[str, Any], received: int) -> bool:
    """Whether a pagination member shows more items than this response holds.

    No paginated response was observed, so its field names are unknown. Every
    object beside `data`, to depth three, is checked for obvious signals: a
    total above the items received, more than one page, a next link or page,
    a true has-more flag, or a full page of a stated size with no total.
    """
    totals: list[int] = []
    sizes: list[int] = []
    more = False
    pending: list[tuple[dict[str, Any], int]] = [
        ({k: v for k, v in envelope.items() if k != "data"}, 0)
    ]
    while pending:
        item, depth = pending.pop()
        for key, value in item.items():
            name = re.sub(r"[^a-z]", "", str(key).lower())
            if name in _NEXT_KEYS:
                more = more or value not in (None, "", False, {}, [])
                continue
            if isinstance(value, dict):
                if depth < 3:
                    pending.append((value, depth + 1))
                continue
            number = _count(value)
            if name in _TOTAL_KEYS and number is not None:
                totals.append(number)
            elif name in _PAGE_COUNT_KEYS and number is not None:
                more = more or number > 1
            elif name in _MORE_KEYS:
                more = more or value is True
            elif name in _PAGE_SIZE_KEYS and number is not None:
                sizes.append(number)
    if any(total > received for total in totals):
        return True
    full_page = any(0 < size <= received for size in sizes)
    return more or (full_page and not totals)


def parse_token_info(body: bytes) -> str:
    """The session's gateway user identifier."""
    return _validate(_TokenInfoWire, decode_json(body)).UserIdentifier


def parse_user_info(body: bytes) -> str | None:
    """The student assigned to a parent login, or None for a student login."""
    wire = _validate(_UserInfoWire, decode_json(body))
    return wire.IdentifierOfStudentAssignedWithUser


def _present(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _day(value: str) -> date:
    result = None
    if _DATE.fullmatch(value):
        try:
            if len(value) > 10:
                datetime.fromisoformat(value)
            result = date.fromisoformat(value[:10])
        except ValueError:
            pass
    if result is None:
        raise LibrusError(ErrorKind.PARSE)
    return result


def parse_partial_grades(body: bytes) -> tuple[PartialGrade, ...]:
    data = _decode_collection(body, "data", GRADE_MAX_RECORDS)
    wire = _validate(_PartialGradesWire, data)
    if _continues(data, len(wire.data)):
        # Returning the first page alone would be a silently partial result.
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return tuple(
        PartialGrade(
            item.subjectId,
            item.teacherId,
            item.addedBy,
            _present(item.area.name) if item.area else None,
            _present(item.scaleValue.value) if item.scaleValue else None,
            _present(item.content),
            _present(item.comments),
            _day(item.date),
            item.semester,
        )
        for item in wire.data
    )


def parse_gateway_subjects(body: bytes) -> Mapping[str, GatewaySubject]:
    data = _decode_collection(body, "data", DESCRIPTIVE_MAX_SUBJECTS)
    wire = _validate(_SubjectsWire, data)
    if _continues(data, len(wire.data)):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    result: dict[str, GatewaySubject] = {}
    numeric: set[int] = set()
    for item in wire.data:
        if item.identifier in result or item.numericIdentifier in numeric:
            # Two rows for one subject are never resolved by choosing one.
            raise LibrusError(ErrorKind.PARSE)
        if item.numericIdentifier is not None:
            numeric.add(item.numericIdentifier)
        result[item.identifier] = GatewaySubject(
            item.numericIdentifier, _present(item.name)
        )
    return MappingProxyType(result)


def parse_gateway_users(body: bytes) -> Mapping[str, str]:
    """Account IDs to "LastName FirstName"; a user with neither is omitted."""
    data = _decode_collection(body, "Users", DESCRIPTIVE_MAX_USERS)
    wire = _validate(_UsersWire, data)
    result: dict[str, str] = {}
    seen: dict[str, tuple[str | None, str | None]] = {}
    for user in wire.Users:
        names = (_present(user.LastName), _present(user.FirstName))
        if seen.setdefault(user.AccountId, names) != names:
            raise LibrusError(ErrorKind.PARSE)
        full = " ".join(part for part in names if part)
        if full:
            result[user.AccountId] = full
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class DescriptiveTable:
    """Numeric subject ID to the subject name the grades page shows."""

    subjects: Mapping[int, str] = field(repr=False)


def _classes(element: html.HtmlElement) -> set[str]:
    return set(element.get("class", "").split())


def read_descriptive_table(document: html.HtmlElement) -> DescriptiveTable | None:
    """The new-schema subject table, or None when the page has none.

    Its rows hold an expander, the subject and two empty semester cells that
    the page script fills from the gateway. A cell the page already filled
    would duplicate the gateway records, so it is an unsupported layout.
    """
    tables = [
        table
        for table in document.iter("table")
        if DESCRIPTIVE_TABLE_CLASS in _classes(table)
    ]
    if not tables:
        return None
    # Observed live (2026-10-28): an unclosed, row-less table of the same class
    # precedes the real one, so HTML parsing nests the rest of the page in it.
    # Only a table with subject rows of its own counts.
    populated = [
        table
        for table in tables
        if any(DESCRIPTIVE_ROW_CLASS in _classes(row) for row in markup.rows(table))
    ]
    if len(populated) > 1:
        raise LibrusError(ErrorKind.PARSE)
    if not populated:
        return None
    tables = populated
    subjects: dict[int, str] = {}
    students: set[str | None] = set()
    for row in markup.rows(tables[0]):
        if DESCRIPTIVE_ROW_CLASS not in _classes(row):
            continue
        cells = markup.cells(row)
        if (
            len(cells) != 4
            or not {"micro", "center", "screen-only"} <= _classes(cells[0])
            or [cell.get("data-semester") for cell in cells[2:]] != ["1", "2"]
            or not all("gradesCell" in _classes(cell) for cell in cells[2:])
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if any(
            markup.text(cell) or any(isinstance(node.tag, str) for node in cell)
            for cell in cells[2:]
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        identifier = row.get("data-subject_id", "")
        name = markup.text(cells[1])
        if not re.fullmatch(r"[0-9]{1,18}", identifier) or not name:
            raise LibrusError(ErrorKind.PARSE)
        if int(identifier) in subjects:
            raise LibrusError(ErrorKind.PARSE)
        subjects[int(identifier)] = name
        if len(subjects) > GRADE_MAX_SUBJECTS:
            raise LibrusError(ErrorKind.LIMIT)
        students.add(row.get("data-user_id"))
    if len(students) > 1:
        # One page shows one student; rows of several students are unknown.
        raise LibrusError(ErrorKind.PARSE)
    return DescriptiveTable(MappingProxyType(subjects))


def parse_grade_page(body: bytes) -> tuple[GradeRecords, DescriptiveTable | None]:
    """The page's grade collection and its new-schema subject table, if any."""
    document = parse_page(body)
    return read_grade_records(document), read_descriptive_table(document)


def descriptive_grades(
    items: tuple[PartialGrade, ...],
    subjects: Mapping[str, GatewaySubject],
    users: Mapping[str, str],
    table: DescriptiveTable,
) -> tuple[DescriptiveGrade, ...]:
    """Map gateway records to descriptive grades without inventing values.

    The subject is the page's name for its numeric ID, else the gateway name.
    The grade is the scale value, else the content. Metadata pairs exist only
    for present fields; an unlisted teacher or author stays unknown.
    """
    result: list[DescriptiveGrade] = []
    for item in items:
        subject = subjects.get(item.subject_id)
        if subject is None:
            raise LibrusError(ErrorKind.PARSE)
        name = (
            table.subjects.get(subject.numeric_id)
            if subject.numeric_id is not None
            else None
        ) or subject.name
        raw = item.scale_value or item.content
        if name is None or raw is None:
            raise LibrusError(ErrorKind.PARSE)
        author = users.get(item.author_id) if item.author_id is not None else None
        metadata = tuple(
            (label, value)
            for label, value in (
                ("Obszar", item.area),
                ("Treść", item.content),
                ("Dodał", author),
                ("Komentarz", item.comments),
                ("Skala", item.scale_value),
            )
            if value is not None
        )
        result.append(
            DescriptiveGrade(
                name,
                raw,
                item.day,
                item.semester,
                users.get(item.teacher_id) if item.teacher_id is not None else None,
                item.comments,
                metadata,
                GradeKind.CURRENT,
            )
        )
    return tuple(result)
