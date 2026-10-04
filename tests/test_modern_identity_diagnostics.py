"""Shape-only inspection is private, bounded and never verifies identity."""

import json

import pytest

from librus_python_api.models import Person, TransportResponse
from scripts.describe_modern_identity import describe_modern_identity

OWNER = Person("123456789", "PrivateFirst", "PrivateLast")


@pytest.mark.parametrize("identifier", [OWNER.id, int(OWNER.id), True, None])
def test_identity_field_types_and_comparisons_do_not_leak_values(
    identifier: object,
) -> None:
    data = {
        "accountId": identifier,
        "firstName": OWNER.first_name,
        "lastName": OWNER.last_name,
        "groupId": "5",
        "originSystem": "synergia",
        "private-field-name": "private-field-value",
    }
    response = TransportResponse(
        200,
        json.dumps(data).encode(),
        "private-response-url",
        {"content-type": "application/json; charset=UTF-8"},
    )
    result = describe_modern_identity(response, OWNER)
    assert result["identity_accepted"] is False
    fields = result["top_level"]
    assert isinstance(fields, dict)
    assert fields["account_id_exactly_matches_owner"] is (type(identifier) is str)
    assert fields["account_id_decimal_value_matches_owner"] is (
        type(identifier) in {str, int}
    )
    assert fields["first_name_matches_owner"] is True
    assert fields["unknown_field_count"] == 1
    serialized = json.dumps(result)
    for private in (
        OWNER.id,
        "PrivateFirst",
        "PrivateLast",
        "private-field-name",
        "private-field-value",
        "private-response-url",
    ):
        assert private not in serialized


@pytest.mark.parametrize(
    "body",
    [
        b"private-not-json",
        b'{"accountId":"private-id","accountId":"other-private-id"}',
        b" " * 262145,
    ],
)
def test_bad_or_oversized_identity_shapes_remain_unaccepted_without_echo(
    body: bytes,
) -> None:
    result = describe_modern_identity(
        TransportResponse(
            200, body, "private", {"content-type": "private-content-type"}
        ),
        OWNER,
    )
    assert result["identity_accepted"] is False
    assert "private" not in json.dumps(
        {
            key: value
            for key, value in result.items()
            if key != "private_response_retained"
        }
    )
