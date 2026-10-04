"""Diagnostic route facts must never retain dynamic values or enable live access."""

import json
from base64 import b64encode

import pytest

from librus_python_api import ConnectionSettings
from librus_python_api.models import TransportResponse
from scripts.describe_modern_launch import describe_modern_launch

LOGIN = "invented-login"
TOKEN = "abc123" * 20


def response(location: str) -> TransportResponse:
    return TransportResponse(
        302, b"Private fixture response", "private-source-url", {"location": location}
    )


@pytest.mark.parametrize("namespace", ["pobierz12", "pobierz28", "pobierz17"])
def test_known_field_structure_retains_only_redacted_namespace(namespace: str) -> None:
    login64 = b64encode(LOGIN.encode()).decode().rstrip("=")
    location = (
        f"https://wiadomosci.librus.pl/{namespace}/MultiDomainLogon/token/{TOKEN}"
        f"/login/{login64}/target/L25vd3k/from/c3luZXJnaWE"
    )
    result = describe_modern_launch(response(location), ConnectionSettings(), LOGIN)
    assert result["redacted_template"] == (
        f"/{namespace}/MultiDomainLogon/token/<redacted>/login/<redacted>"
        "/target/<redacted>/from/<redacted>"
    )
    assert result["installed_handoff_pattern_matches"] is True
    assert result["token_length"] == 120 and result["token_hex"] is True
    assert result["login_matches_unpadded_base64"] is True
    assert "/nowy:unpadded" in result["target_matches"]  # type: ignore[operator]
    serialized = json.dumps(result)
    for secret in (
        LOGIN,
        login64,
        TOKEN,
        location,
        "Private fixture",
        "private-source-url",
    ):
        assert secret not in serialized


@pytest.mark.parametrize(
    "location",
    [
        "",
        "https://wiadomosci.librus.pl/opaque-private-value",
        "https://[invalid",
        "https://wiadomosci.librus.pl/new/private",
        "https://wiadomosci.librus.pl/\nprivate",
    ],
)
def test_unknown_or_malformed_paths_do_not_echo_any_location(location: str) -> None:
    result = describe_modern_launch(response(location), ConnectionSettings(), LOGIN)
    assert "redacted_template" not in result
    assert "private" not in json.dumps(result)
    assert "invalid" not in json.dumps(result)


def test_foreign_userinfo_query_and_fragment_are_facts_not_retained_data() -> None:
    location = (
        "https://private-user:private-password@evil.invalid/"
        f"pobierz28/MultiDomainLogon/token/{TOKEN}/login/private-login"
        "/target/private-target/from/private-source?private-query#private-fragment"
    )
    result = describe_modern_launch(response(location), ConnectionSettings(), LOGIN)
    assert result["modern_origin_matches"] is False
    assert (
        result["userinfo_present"]
        is result["query_present"]
        is result["fragment_present"]
        is True
    )
    assert "private" not in json.dumps(result)
    assert "evil.invalid" not in json.dumps(result)
    assert TOKEN not in json.dumps(result)
