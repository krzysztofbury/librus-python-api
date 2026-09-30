"""Closed, redacted failure categories for library-owned diagnostics."""

from enum import StrEnum


class ErrorKind(StrEnum):
    INVALID_INPUT = "invalid_input"
    CREDENTIALS_REJECTED = "credentials_rejected"
    ACCOUNT_ACTION_REQUIRED = "account_action_required"
    SESSION_EXPIRED = "session_expired"
    ACCESS_DENIED = "access_denied"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    THROTTLED = "throttled"
    MAINTENANCE = "maintenance"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    LIMIT = "limit"
    PARSE = "parse"
    UNKNOWN_DELIVERY = "unknown_delivery"


class LibrusError(Exception):
    """A failure with no arbitrary upstream message, URL, or response attachment.

    Future transport adapters must suppress raw causes at the public boundary.
    This type does not sanitize caller-added exception notes or chained errors.
    """

    def __init__(self, kind: ErrorKind) -> None:
        if not isinstance(kind, ErrorKind):
            raise TypeError("kind must be an ErrorKind")
        self.kind = kind
        super().__init__(kind.value)
