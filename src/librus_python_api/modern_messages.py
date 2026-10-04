"""Original bounded modern directory parsers; no scripts or backend fallback."""

import re
from typing import Any

from librus_python_api.config import (
    MODERN_DIRECTORY_TYPE_PATTERN,
    MODERN_MAX_CLASSES,
    MODERN_MAX_LABEL,
    MODERN_MAX_RECIPIENTS,
    MODERN_MAX_TOTAL_TEXT,
    MODERN_MAX_TYPES,
    MODERN_REJECTION_CODES,
    MODERN_SUPPORTED_ACCOUNT_GROUPS,
    MODERN_SUPPORTED_RECIPIENT_TYPE,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    ModernAccountData,
    ModernRecipient,
    ModernRecipientReference,
    ModernRecipientType,
    ModernRecipientTypeReference,
    SendStatus,
)
from librus_python_api.parsers import decode_json


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LibrusError(ErrorKind.PARSE)
    return value


def _label(value: Any) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > MODERN_MAX_LABEL
        or any(ord(c) < 32 for c in value)
    ):
        raise LibrusError(ErrorKind.PARSE)
    return value


def _identifier(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9]{1,64}", value) is None:
        raise LibrusError(ErrorKind.PARSE)
    return value


def parse_modern_identity(body: bytes) -> ModernAccountData:
    data = _object(decode_json(body))
    raw_identifier = data.get("accountId")
    # Identity alone independently returned a JSON integer. Keep recipient IDs
    # strict and reject bool/float/negative/oversized values before normalization.
    if type(raw_identifier) is int and 0 <= raw_identifier < 10**64:
        raw_identifier = str(raw_identifier)
    identifier = _identifier(raw_identifier)
    if (
        data.get("originSystem") != "synergia"
        or type(data.get("groupId")) is not str
        or data.get("groupId") not in MODERN_SUPPORTED_ACCOUNT_GROUPS
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return ModernAccountData(
        identifier,
        data["groupId"],
        _label(data.get("firstName")),
        _label(data.get("lastName")),
    )


def parse_modern_types(body: bytes, account: str) -> tuple[ModernRecipientType, ...]:
    data = _object(_object(decode_json(body)).get("data"))
    entries = data.get("list")
    if not isinstance(entries, list) or len(entries) > MODERN_MAX_TYPES:
        raise LibrusError(ErrorKind.PARSE)
    result = []
    seen = set()
    for item in entries:
        value = _object(item)
        identifier = value.get("id")
        if (
            type(identifier) is not str
            or MODERN_DIRECTORY_TYPE_PATTERN.fullmatch(identifier) is None
            or identifier in seen
        ):
            raise LibrusError(ErrorKind.PARSE)
        seen.add(identifier)
        result.append(
            ModernRecipientType(
                ModernRecipientTypeReference(identifier, account),
                _label(value.get("name")),
                identifier == MODERN_SUPPORTED_RECIPIENT_TYPE,
            )
        )
    if "defaultGroup" in data and (
        type(data["defaultGroup"]) is not str or data["defaultGroup"] not in seen
    ):
        raise LibrusError(ErrorKind.PARSE)
    return tuple(result)


def validate_modern_type(reference: ModernRecipientTypeReference, account: str) -> None:
    if (
        not isinstance(reference, ModernRecipientTypeReference)
        or reference.account != account
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if reference.identifier != MODERN_SUPPORTED_RECIPIENT_TYPE:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def parse_modern_recipients(
    body: bytes, reference: ModernRecipientTypeReference
) -> tuple[ModernRecipient, ...]:
    validate_modern_type(reference, reference.account)
    data = _object(decode_json(body))
    classes = data.get("classes")
    if (
        set(data) != {"classes"}
        or not isinstance(classes, list)
        or len(classes) > MODERN_MAX_CLASSES
    ):
        raise LibrusError(ErrorKind.PARSE)
    result: list[ModernRecipient] = []
    labels: set[str] = set()
    seen: set[str] = set()
    total = 0
    for raw_class in classes:
        klass = _object(raw_class)
        label = _label(klass.get("label"))
        groups = klass.get("receivers")
        if (
            set(klass) != {"label", "receivers"}
            or label in labels
            or not isinstance(groups, list)
            or len(groups) != 1
            or not isinstance(groups[0], list)
        ):
            raise LibrusError(ErrorKind.PARSE)
        labels.add(label)
        total += len(label)
        if total > MODERN_MAX_TOTAL_TEXT:
            raise LibrusError(ErrorKind.LIMIT)
        if len(result) + len(groups[0]) > MODERN_MAX_RECIPIENTS:
            raise LibrusError(ErrorKind.LIMIT)
        for raw in groups[0]:
            leaf = _object(raw)
            if set(leaf) != {"accountId", "userId", "name"}:
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            identifier, user = (
                _identifier(leaf.get("accountId")),
                _identifier(leaf.get("userId")),
            )
            name = _label(leaf.get("name"))
            if identifier in seen:
                raise LibrusError(ErrorKind.PARSE)
            seen.add(identifier)
            total += len(name)
            if total > MODERN_MAX_TOTAL_TEXT:
                raise LibrusError(ErrorKind.LIMIT)
            result.append(
                ModernRecipient(
                    ModernRecipientReference(
                        identifier, user, reference.account, reference.identifier, label
                    ),
                    name,
                )
            )
    return tuple(result)


def parse_modern_send_response(body: bytes, status: int) -> SendStatus:
    """Accept only the observed created/sent envelope, never HTTP success alone."""
    data = _object(decode_json(body))
    if status == 201 and set(data) == {"data"}:
        receipt = data["data"]
        if (
            type(receipt) is dict
            and set(receipt) == {"messageId", "status"}
            and receipt["status"] == "sent"
            and type(receipt["messageId"]) is int
            and 0 < receipt["messageId"] < 10**64
        ):
            return SendStatus.ACCEPTED
    if status in (400, 422) and set(data) <= {"code", "errors", "message"}:
        codes = []
        if "code" in data:
            codes.append(data["code"])
        errors = data.get("errors", [])
        if not isinstance(errors, list) or len(errors) > 50:
            raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
        for error in errors:
            entry = _object(error)
            if set(entry) - {"code", "message", "field"}:
                raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
            codes.append(entry.get("code"))
        if codes and all(
            type(code) is str and code in MODERN_REJECTION_CODES for code in codes
        ):
            return SendStatus.REJECTED
    raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
