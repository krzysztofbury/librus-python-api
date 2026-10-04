"""Sanitized diagnostic output cannot leak unknown keys or field values."""

import json

import pytest

from scripts.describe_modern_communication import describe, flag_representations


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"receiver": "1"},
        {"myMessage": 0, "isAnyFileAttached": True},
        {"receiver": "private account label", "myMessage": 1.0},
    ],
)
def test_optional_flags_are_present_and_strictly_bounded(
    row: dict[str, object],
) -> None:
    result = flag_representations(row)
    assert all(key in row for key in result)
    assert result == (
        {"receiver": "1"}
        if row == {"receiver": "1"}
        else {"myMessage": 0, "isAnyFileAttached": True}
        if row.get("isAnyFileAttached") is True
        else {}
    )


def test_shape_hides_unknown_keys_all_values_and_bounds_recursion() -> None:
    value = {
        "data": [
            {
                "senderName": "private person",
                "private-key": "private value",
                "readDate": None,
            }
        ],
        "total": 123,
    }
    encoded = json.dumps(describe(value))
    assert "private" not in encoded and "123" not in encoded
    assert (
        describe(value)["known_fields"]["data"]["first_item"]["unknown_field_count"]
        == 1
    )
    nested = {"data": {"data": {"data": {"data": {"data": {"data": value}}}}}}
    assert "senderName" not in json.dumps(describe(nested))
