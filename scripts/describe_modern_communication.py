"""Value-free bounded shape reporting for owner-approved communication captures.

This module never performs network I/O or retains raw pages. Unknown field names
are not emitted: directory and message labels can otherwise leak through keys.
"""

from typing import Any

KNOWN_FIELDS = frozenset(
    "data total list defaultGroup id name classes label receivers accountId userId "
    "availabilityStatus groupId groups messageId topic content Message senderName "
    "receiverName senderId senderGroupId sendDate readDate receiver myMessage spam "
    "state tags isAnyFileAttached attachments filename isCc isBcc isSender receiverId "
    "receiverFirstName receiverLastName receiverGroupId userFirstName userLastName "
    "userClass category archive archivingInProgress isMessageWithdrawn originalMessage "
    "type title schools schoolUuid schoolName".split()
)


def describe(value: Any, depth: int = 0) -> dict[str, Any]:
    if depth > 5:
        return {"type": type(value).__name__}
    if isinstance(value, dict):
        return {
            "type": "object",
            "known_fields": {
                key: describe(item, depth + 1)
                for key, item in value.items()
                if key in KNOWN_FIELDS
            },
            "unknown_field_count": sum(key not in KNOWN_FIELDS for key in value),
        }
    if isinstance(value, list):
        result: dict[str, Any] = {"type": "array", "count": len(value)}
        if value:
            result["first_item"] = describe(value[0], depth + 1)
        return result
    return {"type": type(value).__name__}


def flag_representations(row: dict[str, Any]) -> dict[str, bool | int | str | None]:
    """Only present, explicitly bounded JSON flag values; no truthy coercion."""
    return {
        key: row[key]
        for key in ("receiver", "myMessage", "isAnyFileAttached")
        if key in row
        and (
            row[key] is None
            or type(row[key]) is bool
            or type(row[key]) is int
            and row[key] in (0, 1)
            or type(row[key]) is str
            and row[key] in ("0", "1")
        )
    }
