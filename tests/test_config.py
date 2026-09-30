from dataclasses import FrozenInstanceError

import pytest

from librus_python_api.config import Endpoint, Evidence, SideEffect, TransportLimits
from librus_python_api.errors import ErrorKind, LibrusError


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_invalid_byte_budget_is_rejected(size: int) -> None:
    with pytest.raises(LibrusError, match="^invalid_input$"):
        TransportLimits(response_max_bytes=size)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_timeouts_are_rejected(timeout: float) -> None:
    with pytest.raises(LibrusError, match="^invalid_input$"):
        TransportLimits(request_timeout_seconds=timeout)


def test_connect_timeout_cannot_exceed_total_deadline() -> None:
    with pytest.raises(LibrusError, match="^invalid_input$"):
        TransportLimits(connect_timeout_seconds=31)


def test_limits_are_immutable() -> None:
    limits = TransportLimits()
    with pytest.raises(FrozenInstanceError):
        limits.response_max_bytes = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    "path",
    [
        "https://example.invalid/private",
        "//foreign/path",
        "/../private",
        "/%2f",
        "/a?b",
    ],
)
def test_endpoint_rejects_url_and_path_injection(path: str) -> None:
    with pytest.raises(LibrusError, match="^invalid_input$"):
        Endpoint("fixture", "GET", path, SideEffect.NONE, True, Evidence.SYNTHETIC_ONLY)


@pytest.mark.parametrize(
    "effect", [SideEffect.CONSUME_EVENTS, SideEffect.SEND_MESSAGE, SideEffect.MARK_READ]
)
def test_side_effecting_get_is_not_retry_safe(effect: SideEffect) -> None:
    with pytest.raises(LibrusError, match="^invalid_input$"):
        Endpoint("fixture", "GET", "/fixture", effect, True, Evidence.SYNTHETIC_ONLY)


def test_error_does_not_accept_arbitrary_upstream_messages() -> None:
    with pytest.raises(TypeError, match="^kind must be an ErrorKind$"):
        LibrusError("untrusted fixture response")  # type: ignore[arg-type]
    error = LibrusError(ErrorKind.PARSE)
    assert str(error) == "parse"
    assert repr(error) == "LibrusError('parse')"
