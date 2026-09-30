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
    CLOSED = "closed"


class LibrusError(Exception):
    """A failure with no arbitrary upstream message, URL, or response attachment.

    Future transport adapters must suppress raw causes at the public boundary.
    This type does not sanitize caller-added exception notes or chained errors.
    """

    def __new__(cls, kind: ErrorKind) -> "LibrusError":
        if not isinstance(kind, ErrorKind):
            raise TypeError("kind must be an ErrorKind")
        # Preserve the foundation constructor while routing all failures through
        # the same closed factory registry. Callers can catch specific subclasses.
        concrete = _ERROR_TYPES[kind] if cls is LibrusError else cls
        if concrete is not _ERROR_TYPES[kind]:
            raise TypeError("Exception class and kind must agree")
        return super().__new__(concrete)

    def __init__(self, kind: ErrorKind) -> None:
        if not isinstance(kind, ErrorKind):
            raise TypeError("kind must be an ErrorKind")
        self.kind = kind
        super().__init__(kind.value)


class InvalidInputError(LibrusError):
    pass


class CredentialsRejectedError(LibrusError):
    pass


class AccountActionRequiredError(LibrusError):
    pass


class SessionExpiredError(LibrusError):
    pass


class AccessDeniedError(LibrusError):
    pass


class UnsupportedCapabilityError(LibrusError):
    pass


class ThrottledError(LibrusError):
    pass


class MaintenanceError(LibrusError):
    pass


class ConnectionError(LibrusError):
    pass


class OperationTimeoutError(LibrusError):
    pass


class LimitError(LibrusError):
    pass


class ParseError(LibrusError):
    pass


class UnknownDeliveryError(LibrusError):
    pass


class ClosedError(LibrusError):
    pass


_ERROR_TYPES: dict[ErrorKind, type[LibrusError]] = {
    ErrorKind.INVALID_INPUT: InvalidInputError,
    ErrorKind.CREDENTIALS_REJECTED: CredentialsRejectedError,
    ErrorKind.ACCOUNT_ACTION_REQUIRED: AccountActionRequiredError,
    ErrorKind.SESSION_EXPIRED: SessionExpiredError,
    ErrorKind.ACCESS_DENIED: AccessDeniedError,
    ErrorKind.UNSUPPORTED_CAPABILITY: UnsupportedCapabilityError,
    ErrorKind.THROTTLED: ThrottledError,
    ErrorKind.MAINTENANCE: MaintenanceError,
    ErrorKind.CONNECTION: ConnectionError,
    ErrorKind.TIMEOUT: OperationTimeoutError,
    ErrorKind.LIMIT: LimitError,
    ErrorKind.PARSE: ParseError,
    ErrorKind.UNKNOWN_DELIVERY: UnknownDeliveryError,
    ErrorKind.CLOSED: ClosedError,
}


def error_for(kind: ErrorKind) -> LibrusError:
    """Single redacted factory for every library-owned failure."""
    return _ERROR_TYPES[kind](kind)
