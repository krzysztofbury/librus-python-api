"""Bounded offline identity-shape facts, never an identity acceptance adapter."""

from typing import Any

from librus_python_api.config import MODERN_SUPPORTED_ACCOUNT_GROUPS
from librus_python_api.exceptions import LibrusError
from librus_python_api.models import Person, TransportResponse
from librus_python_api.modern_messages import parse_modern_identity
from librus_python_api.parsers import decode_json

FIELDS = frozenset(
    {
        "accountId",
        "groupId",
        "firstName",
        "lastName",
        "originSystem",
        "id",
        "data",
        "account",
        "user",
    }
)


def describe_modern_identity(
    response: TransportResponse, owner: Person
) -> dict[str, object]:
    """Retain only known field names/types and comparisons, not private values."""
    content_type = (
        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    report: dict[str, object] = {
        "status": response.status,
        "content_type": content_type
        if content_type in {"application/json", "text/html", "text/plain"}
        else "other",
        "private_response_retained": False,
        "identity_accepted": False,
    }
    if len(response.body) > 262144:
        return {**report, "shape": "over_limit"}
    try:
        data = decode_json(response.body)
    except LibrusError as error:
        return {**report, "json_error_kind": error.kind.value}
    report["top_level_type"] = _kind(data)
    if type(data) is not dict or len(data) > 64:
        return report
    report["top_level"] = _fields(data, owner)
    # Only one known wrapper layer, never arbitrary keys or recursive traversal.
    for key in ("data", "account", "user"):
        value = data.get(key)
        if type(value) is dict and len(value) <= 64:
            report[key] = _fields(value, owner)
    try:
        parse_modern_identity(response.body)
    except LibrusError as error:
        report["native_parser_error_kind"] = error.kind.value
    else:
        report["native_parser_result"] = "parseable_not_identity_verified"
    return report


def _kind(value: Any) -> str:
    return {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        type(None): "null",
        dict: "object",
        list: "array",
    }.get(type(value), "other")


def _fields(data: dict[str, Any], owner: Person) -> dict[str, object]:
    account_id = data.get("accountId")
    normalized = (
        str(account_id)
        if type(account_id) is int and 0 <= account_id < 10**64
        else account_id
    )
    return {
        "recognized_fields": {
            key: _kind(data[key]) for key in sorted(FIELDS & data.keys())
        },
        "unknown_field_count": len(data.keys() - FIELDS),
        "account_id_exactly_matches_owner": type(account_id) is str
        and account_id == owner.id,
        "account_id_decimal_value_matches_owner": type(normalized) is str
        and normalized == owner.id,
        "first_name_matches_owner": owner.first_name is not None
        and data.get("firstName") == owner.first_name,
        "last_name_matches_owner": owner.last_name is not None
        and data.get("lastName") == owner.last_name,
        "origin_matches_synergia": data.get("originSystem") == "synergia",
        "group_is_supported_string": type(data.get("groupId")) is str
        and data.get("groupId") in MODERN_SUPPORTED_ACCOUNT_GROUPS,
    }
