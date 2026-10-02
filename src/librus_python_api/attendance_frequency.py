"""Original validated gateway parsing and explicit attendance ratio policies."""

from pydantic import ValidationError

from librus_python_api import markup
from librus_python_api.config import ATTENDANCE_MAX_RECORDS, ATTENDANCE_TYPE_KINDS
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    AttendanceKind,
    FrequencyMeasure,
    GatewayAttendanceRecord,
    _AttendanceEnvelopeWire,
    _LessonEnvelopeWire,
    _SubjectEnvelopeWire,
)
from librus_python_api.parsers import decode_json


def parse_gateway_attendance(body: bytes) -> tuple[GatewayAttendanceRecord, ...]:
    data = decode_json(body)
    if (
        isinstance(data, dict)
        and isinstance(data.get("Attendances"), list)
        and len(data["Attendances"]) > ATTENDANCE_MAX_RECORDS
    ):
        raise LibrusError(ErrorKind.LIMIT)
    failed = False
    envelope = None
    try:
        envelope = _AttendanceEnvelopeWire.model_validate(data)
    except ValidationError:
        failed = True
    if failed or envelope is None:
        raise LibrusError(ErrorKind.PARSE)
    seen: set[str] = set()
    records: list[GatewayAttendanceRecord] = []
    for row in envelope.Attendances:
        if row.Id is not None:
            if row.Id in seen:
                raise LibrusError(ErrorKind.PARSE)
            seen.add(row.Id)
        records.append(
            GatewayAttendanceRecord(
                row.Id,
                markup.civil_date(row.Date),
                row.Semester,
                row.Type.Id,
                AttendanceKind(ATTENDANCE_TYPE_KINDS.get(row.Type.Id, "unknown")),
                row.Lesson.Id,
                row.LessonNo,
            )
        )
    return tuple(records)


def parse_lesson_subject(body: bytes, identifier: str) -> str:
    data = decode_json(body)
    failed = False
    lesson = None
    try:
        lesson = _LessonEnvelopeWire.model_validate(data).Lesson
    except ValidationError:
        failed = True
    if failed or lesson is None or lesson.Id != identifier:
        raise LibrusError(ErrorKind.PARSE)
    return lesson.Subject.Id


def parse_subject_name(body: bytes, identifier: str) -> str:
    data = decode_json(body)
    failed = False
    subject = None
    try:
        subject = _SubjectEnvelopeWire.model_validate(data).Subject
    except ValidationError:
        failed = True
    if (
        failed
        or subject is None
        or subject.Id != identifier
        or not subject.Name.strip()
    ):
        raise LibrusError(ErrorKind.PARSE)
    return subject.Name.strip()


def summarize_frequency(
    rows: tuple[GatewayAttendanceRecord, ...],
    *,
    subject_policy: bool,
) -> FrequencyMeasure:
    attended = total = unknown = excluded = 0
    for row in rows:
        if row.kind == "unknown":
            unknown += 1
        if not subject_policy:
            total += 1
            attended += row.kind in ("present", "late", "excursion")
        elif row.kind in ("present", "late", "absence", "excused", "exemption"):
            total += 1
            attended += row.kind in ("present", "late")
        elif row.kind != "unknown":
            excluded += 1
    ratio = attended / total if total and not unknown else None
    return FrequencyMeasure(
        attended,
        total,
        excluded,
        unknown,
        ratio,
        "subject" if subject_policy else "overall",
    )
