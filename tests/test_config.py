import pytest
from pydantic import ValidationError

from librus_python_api.budget import RequestBudget
from librus_python_api.config import (
    Endpoint,
    Evidence,
    SchedulerLimits,
    SideEffect,
    TransportLimits,
)
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
    with pytest.raises(ValidationError, match="frozen_instance"):
        limits.response_max_bytes = 0


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


@pytest.mark.parametrize(
    "values",
    [
        {"requests_per_second": float("nan")},
        {"burst": True},
        {"burst": 0},
        {"active_requests": "2"},
        {"queued_requests": -1},
        {"active_requests_per_account": 3},
        {"queued_requests_per_account": 33},
        {"unexpected": "synthetic private value"},
    ],
)
def test_scheduler_config_is_strict_and_errors_are_redacted(
    values: dict[str, object],
) -> None:
    with pytest.raises(LibrusError, match="^invalid_input$") as caught:
        SchedulerLimits(**values)  # type: ignore[arg-type]
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "values",
    [
        {"max_requests": True},
        {"max_requests": 0},
        {"max_requests": 1.5},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 10**400},
        {"timeout_seconds": "synthetic private value"},
    ],
)
def test_operation_budget_rejects_invalid_or_overflowing_limits(
    values: dict[str, object],
) -> None:
    with pytest.raises(LibrusError, match="^invalid_input$") as caught:
        RequestBudget(**values)  # type: ignore[arg-type]
    assert caught.value.__context__ is None
