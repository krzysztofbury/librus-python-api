"""Bounded original serialization of typed native records and raw envelopes."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from functools import lru_cache
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    Announcement,
    AttendanceRecord,
    DescriptiveGrade,
    HomeworkItem,
    Identity,
    MessageSummary,
    NotificationCategory,
    NumericGrade,
    Observation,
    RecentScheduleEvent,
    ScheduleEventResponse,
    ScheduleEventWire,
)
from librus_python_api.notification_models import (
    NotificationBatch,
    NotificationItem,
    NotificationSeen,
    NotificationState,
    NotificationValue,
)
from librus_python_api.notifications import validate_response

HEX = re.compile(r"[0-9a-f]{64}")
WIRE_BYTES = 4 * 1024 * 1024
META_BYTES = 4 * 1024 * 1024
ARCHIVE_BYTES = 48 * 1024 * 1024
_VALUE_TYPES: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        NumericGrade,
        DescriptiveGrade,
        AttendanceRecord,
        MessageSummary,
        Announcement,
        HomeworkItem,
        RecentScheduleEvent,
    )
}
_CATEGORY_TYPES: dict[NotificationCategory, tuple[type[Any], ...]] = {
    NotificationCategory.GRADES: (NumericGrade, DescriptiveGrade),
    NotificationCategory.ATTENDANCE: (AttendanceRecord,),
    NotificationCategory.MESSAGES: (MessageSummary,),
    NotificationCategory.ANNOUNCEMENTS: (Announcement,),
    NotificationCategory.HOMEWORK: (HomeworkItem,),
    NotificationCategory.AGENDA: (RecentScheduleEvent,),
}


def _dates(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise ValueError("Unsupported value")


def dump(value: Any, maximum: int) -> bytes:
    failed = False
    payload = b""
    try:
        payload = json.dumps(
            value,
            default=_dates,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        failed = True
    if failed:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if len(payload) > maximum:
        raise LibrusError(ErrorKind.LIMIT)
    return payload


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def load(payload: bytes, maximum: int) -> Any:
    if type(payload) is not bytes or len(payload) > maximum:
        raise LibrusError(ErrorKind.LIMIT)
    failed = False
    result: Any = None
    try:
        result = json.loads(payload, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError):
        failed = True
    if failed:
        raise LibrusError(ErrorKind.PARSE)
    return result


@lru_cache(maxsize=16)
def _adapter(cls: type[Any]) -> TypeAdapter[Any]:
    return TypeAdapter(cls)


def typed[T](cls: type[T], value: Any, maximum: int = META_BYTES) -> T:
    if type(value) is not dict or set(value) != {
        f.name for f in fields(cast(Any, cls))
    }:
        raise LibrusError(ErrorKind.PARSE)
    adapter = _adapter(cast(Any, cls))
    failed = False
    result: T | None = None
    try:
        result = cast(T, adapter.validate_json(dump(value, maximum), strict=True))
    except (ValidationError, ValueError, RecursionError):
        failed = True
    if failed:
        raise LibrusError(ErrorKind.PARSE)
    assert result is not None
    return result


def canonical_notification_id(
    category: NotificationCategory, value: NotificationValue
) -> str:
    if (
        not isinstance(category, NotificationCategory)
        or type(value) not in _CATEGORY_TYPES[category]
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if isinstance(value, RecentScheduleEvent):
        # Independently specified three-field canonical identity, including data.
        canonical: Any = asdict(value)
    elif isinstance(value, MessageSummary):
        canonical = [
            1,
            category.value,
            value.reference.folder.value,
            value.reference.identifier,
        ]
    elif isinstance(value, Announcement):
        canonical = [1, category.value, value.reference]
    elif isinstance(value, HomeworkItem) and value.reference is not None:
        canonical = [1, category.value, value.reference.identifier]
    elif isinstance(value, AttendanceRecord) and value.detail_id is not None:
        canonical = [1, category.value, value.detail_id]
    else:
        canonical = [1, category.value, type(value).__name__, asdict(value)]
    return hashlib.sha256(dump(canonical, META_BYTES)).hexdigest()


def empty_state() -> NotificationState:
    return NotificationState(
        False,
        tuple(NotificationSeen(category, ()) for category in NotificationCategory),
    )


def state_bytes(state: NotificationState, per_category: int, maximum: int) -> bytes:
    restored = typed(NotificationState, asdict(state))
    if tuple(s.category for s in restored.seen) != tuple(NotificationCategory):
        raise LibrusError(ErrorKind.PARSE)
    for seen in restored.seen:
        if len(seen.identifiers) > per_category:
            raise LibrusError(ErrorKind.LIMIT)
        if len(set(seen.identifiers)) != len(seen.identifiers) or any(
            HEX.fullmatch(v) is None for v in seen.identifiers
        ):
            raise LibrusError(ErrorKind.PARSE)
    if not restored.initialized and any(seen.identifiers for seen in restored.seen):
        raise LibrusError(ErrorKind.PARSE)
    return dump(asdict(restored), maximum)


def restore_state(payload: bytes, per_category: int, maximum: int) -> NotificationState:
    state = typed(NotificationState, load(payload, maximum))
    state_bytes(state, per_category, maximum)
    return state


@dataclass(frozen=True, slots=True)
class _EnvelopeMetadata:
    version: int
    identity: Identity
    observation: Observation
    content_type: str | None
    content_codings: tuple[str, ...]
    transfer_codings: tuple[str, ...]


def encode_envelope(response: ScheduleEventResponse, alias: str) -> tuple[bytes, bytes]:
    validate_response(response, alias, WIRE_BYTES)
    wire = response.wire
    metadata = _EnvelopeMetadata(
        response.version,
        response.identity,
        response.observation,
        wire.content_type,
        wire.content_codings,
        wire.transfer_codings,
    )
    payload = dump(asdict(metadata), META_BYTES)
    restore_envelope(payload, wire.body, alias)
    return payload, wire.body


def restore_envelope(metadata: bytes, body: bytes, alias: str) -> ScheduleEventResponse:
    record = typed(_EnvelopeMetadata, load(metadata, META_BYTES))
    response = ScheduleEventResponse(
        record.version,
        record.identity,
        ScheduleEventWire(
            body, record.content_type, record.content_codings, record.transfer_codings
        ),
        record.observation,
    )
    validate_response(response, alias, WIRE_BYTES)
    for observation in (record.observation, record.identity.observation):
        if (
            observation.observed_at.tzinfo is None
            or not 0 <= observation.session_generation <= 10**12
        ):
            raise LibrusError(ErrorKind.PARSE)
    return response


def encode_batch(batch: NotificationBatch, maximum: int) -> bytes:
    payload = asdict(batch)
    payload["items"] = [
        {"kind": type(item.value).__name__, "item": asdict(item)}
        for item in batch.items
    ]
    return dump(payload, maximum)


def restore_batch(payload: bytes, maximum: int) -> NotificationBatch:
    record = load(payload, maximum)
    if (
        type(record) is not dict
        or set(record) != {f.name for f in fields(NotificationBatch)}
        or type(record["items"]) is not list
    ):
        raise LibrusError(ErrorKind.PARSE)
    items = []
    for entry in record["items"]:
        if (
            type(entry) is not dict
            or set(entry) != {"kind", "item"}
            or type(entry["kind"]) is not str
            or entry["kind"] not in _VALUE_TYPES
        ):
            raise LibrusError(ErrorKind.PARSE)
        item = entry["item"]
        if type(item) is not dict or set(item) != {
            f.name for f in fields(NotificationItem)
        }:
            raise LibrusError(ErrorKind.PARSE)
        value = typed(_VALUE_TYPES[entry["kind"]], item["value"])
        # Validate union contents separately, then reconstruct the original type.
        parsed = typed(NotificationItem, item)
        if type(value) not in _CATEGORY_TYPES[
            parsed.category
        ] or parsed.identifier != canonical_notification_id(parsed.category, value):
            raise LibrusError(ErrorKind.PARSE)
        items.append(
            NotificationItem(
                parsed.category,
                parsed.identifier,
                value,
                parsed.identity,
                parsed.observation,
            )
        )
    record["items"] = []
    batch = typed(NotificationBatch, record, maximum)
    if (
        HEX.fullmatch(batch.receipt) is None
        or HEX.fullmatch(batch.context.identifier) is None
        or not batch.categories
        or len(set(batch.categories)) != len(batch.categories)
    ):
        raise LibrusError(ErrorKind.PARSE)
    if any(
        item.category not in batch.categories
        or item.observation.account != batch.context.alias
        or item.identity.observation.account != batch.context.alias
        for item in items
    ):
        raise LibrusError(ErrorKind.PARSE)
    return NotificationBatch(
        batch.receipt,
        batch.context,
        batch.first_run,
        batch.categories,
        tuple(items),
        batch.has_more_schedule,
    )
