"""Opt-in allowlisted structured diagnostics; no global logging configuration."""

import logging
from typing import Protocol

from librus_python_api.models import DiagnosticEvent


class DiagnosticSink(Protocol):
    def __call__(self, event: DiagnosticEvent, /) -> None: ...


def logging_sink(event: DiagnosticEvent) -> None:
    """Emit allowlisted fields via stdlib logging; the application owns handlers."""
    logging.getLogger("librus_python_api").info(
        "Librus operation completed",
        extra={
            "component": "librus_python_api",
            "operation": event.operation,
            "outcome": event.outcome,
            "elapsed_seconds": event.elapsed_seconds,
            "budget_requests_dispatched": event.budget_requests_dispatched,
            "budget_response_bytes": event.budget_response_bytes,
        },
    )
