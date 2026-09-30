"""Opt-in allowlisted structured diagnostics; no global logging configuration."""

from dataclasses import dataclass
from typing import Literal, Protocol

from loguru import logger

from librus_python_api.errors import ErrorKind


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    operation: Literal["identity", "student_information"]
    outcome: ErrorKind | Literal["ok", "cancelled"]
    elapsed_seconds: float
    budget_requests_dispatched: int
    budget_response_bytes: int


class DiagnosticSink(Protocol):
    def __call__(self, event: DiagnosticEvent, /) -> None: ...


def loguru_sink(event: DiagnosticEvent) -> None:
    """Uses the application's Loguru sinks without installing any.

    Configure serialize=True for JSON or your own pretty format in the caller.
    No account aliases, identities, URLs, exception objects, or body excerpts.
    """
    logger.bind(
        component="librus_python_api",
        operation=event.operation,
        outcome=event.outcome,
        elapsed_seconds=event.elapsed_seconds,
        budget_requests_dispatched=event.budget_requests_dispatched,
        budget_response_bytes=event.budget_response_bytes,
    ).info("Librus operation completed")
