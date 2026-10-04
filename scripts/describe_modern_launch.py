"""Offline, redacted launch diagnostics, not permission to follow a redirect.

Preserve only a narrowly recognized non-secret route namespace and field labels.
Opaque values, credentials, raw URLs, query values and token digests never appear
in the result. Unknown shapes remain unknown; this does not enable any new route.
"""

import re
from base64 import b64encode
from urllib.parse import urlsplit

from librus_python_api.config import (
    ENDPOINTS,
    MODERN_HANDOFF_PATTERN,
    MODERN_TERMINAL_PATHS,
    ConnectionSettings,
)
from librus_python_api.models import TransportResponse


def describe_modern_launch(
    response: TransportResponse,
    connection: ConnectionSettings,
    expected_login: str,
) -> dict[str, object]:
    """Describe headers locally without copying private response data to output."""
    report: dict[str, object] = {
        "status": response.status,
        "raw_url_or_token_retained": False,
    }
    location = response.headers.get("location", "")
    if not 1 <= len(location) <= 4096 or any(
        ord(value) <= 32 or ord(value) >= 127 for value in location
    ):
        return {**report, "location_shape": "unsupported"}
    try:
        parsed = urlsplit(location)
        official = urlsplit(connection.messages_origin)
        has_userinfo = parsed.username is not None or parsed.password is not None
    except ValueError:
        return {**report, "location_shape": "malformed"}
    report.update(
        absolute_https=parsed.scheme == "https",
        modern_origin_matches=parsed.scheme == official.scheme
        and parsed.netloc == official.netloc
        and not has_userinfo,
        userinfo_present=has_userinfo,
        query_present=bool(parsed.query),
        fragment_present=bool(parsed.fragment),
        installed_handoff_pattern_matches=MODERN_HANDOFF_PATTERN.fullmatch(parsed.path)
        is not None,
    )
    # Namespace observations are diagnostic facts, not an origin/path allowlist.
    parts = parsed.path.strip("/").split("/")
    report["path_field_count"] = len(parts)
    if len(parts) != 10 or re.fullmatch(r"pobierz[0-9]{1,3}", parts[0]) is None:
        return report
    if parts[1] != "MultiDomainLogon" or parts[2::2] != [
        "token",
        "login",
        "target",
        "from",
    ]:
        return report
    report["redacted_template"] = (
        f"/{parts[0]}/MultiDomainLogon/token/<redacted>/login/<redacted>"
        "/target/<redacted>/from/<redacted>"
    )
    report.update(_field_facts(parts[3::2], expected_login))
    return report


def _field_facts(values: list[str], login: str) -> dict[str, object]:
    token, encoded_login, target, source = values
    login64 = b64encode(login.encode()).decode("ascii")
    terminal_paths = MODERN_TERMINAL_PATHS | {
        path.lstrip("/") for path in MODERN_TERMINAL_PATHS
    }
    # Candidate texts are fixed public route/origin facts, never decoded secrets.
    source_texts = {
        ENDPOINTS["modern_launch"].origin,
        ENDPOINTS["modern_launch"].path,
    }
    return {
        "token_length": len(token),
        "token_alphanumeric": re.fullmatch(r"[A-Za-z0-9]+", token) is not None,
        "token_hex": re.fullmatch(r"[A-Fa-f0-9]+", token) is not None,
        "login_matches_unpadded_base64": encoded_login == login64.rstrip("="),
        "login_matches_padded_base64": encoded_login == login64,
        "target_matches": _known_encodings(target, terminal_paths),
        "source_matches": _known_encodings(source, source_texts),
    }


def _known_encodings(value: str, candidates: set[str] | frozenset[str]) -> list[str]:
    return [
        f"{candidate}:{'padded' if padded else 'unpadded'}"
        for candidate in sorted(candidates)
        for padded in (False, True)
        if value
        == (
            b64encode(candidate.encode()).decode("ascii")
            if padded
            else b64encode(candidate.encode()).decode("ascii").rstrip("=")
        )
    ]
