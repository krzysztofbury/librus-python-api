"""Opt-in allowlisted structured diagnostics; no global logging configuration."""

from typing import Protocol

from librus_python_api.models import DiagnosticEvent


class DiagnosticSink(Protocol):
    def __call__(self, event: DiagnosticEvent, /) -> None: ...


def loguru_sink(event: DiagnosticEvent) -> None:
    """Uses the application's Loguru sinks without installing any.

    Configure serialize=True for JSON or your own pretty format in the caller.
    No account aliases, identities, URLs, exception objects, or body excerpts.
    """
    # Import only when enabled: ordinary reads must not initialize logging.
    from loguru import logger

    logger.bind(
        component="librus_python_api",
        operation=event.operation,
        outcome=event.outcome,
        elapsed_seconds=event.elapsed_seconds,
        budget_requests_dispatched=event.budget_requests_dispatched,
        budget_response_bytes=event.budget_response_bytes,
    ).info("Librus operation completed")
