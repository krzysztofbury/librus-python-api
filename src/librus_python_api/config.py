"""Central network route catalogue and transport configuration.

Add fixed upstream paths here, never in parsers or account methods. The catalogue
is empty until the first independently evidenced network operation is enabled.
There is intentionally no public arbitrary authenticated URL interface.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from librus_python_api.errors import ErrorKind, LibrusError

HttpMethod = Literal["GET", "POST"]


class SideEffect(StrEnum):
    NONE = "none"
    AUTHENTICATION = "authentication"
    MARK_READ = "mark_read"
    CONSUME_EVENTS = "consume_events"
    SEND_MESSAGE = "send_message"


class Evidence(StrEnum):
    SYNTHETIC_ONLY = "synthetic_only"
    INDEPENDENTLY_OBSERVED = "independently_observed"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Fixed route metadata, not a claim that an HTTP verb is retry-safe.

    Evidence describes the source of the wire contract, not live compatibility
    at any later date. Every future endpoint also needs a contract evidence note.
    """

    operation_id: str
    method: HttpMethod
    path: str
    side_effect: SideEffect
    retry_safe: bool
    evidence: Evidence

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", self.operation_id):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if self.method not in ("GET", "POST"):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if not re.fullmatch(r"/(?:[A-Za-z0-9_{}-]+/)*[A-Za-z0-9_{}-]*", self.path):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if len(self.path) > 256:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if not isinstance(self.side_effect, SideEffect):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if not isinstance(self.evidence, Evidence):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if type(self.retry_safe) is not bool:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if self.side_effect != SideEffect.NONE and self.retry_safe:
            raise LibrusError(ErrorKind.INVALID_INPUT)


# Future login, JSON, messaging, and HTML routes all belong in this catalogue.
# Contract checks compare every method/path against the versioned OpenAPI YAML.
ENDPOINTS: Mapping[str, Endpoint] = MappingProxyType({})


class _ValidatedConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", hide_input_in_errors=True
    )

    def __init__(self, **data: Any) -> None:
        failed = False
        try:
            super().__init__(**data)
        except ValidationError:
            failed = True
        # Raise outside the handler so the raw validation error is not chained.
        if failed:
            raise LibrusError(ErrorKind.INVALID_INPUT)


PositiveCount = Annotated[int, Field(gt=0)]
QueueCount = Annotated[int, Field(ge=0)]
PositiveFinite = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class TransportLimits(_ValidatedConfig):
    """Per-request bounds used by the local transport evaluation.

    These do not implement service-wide scheduling or operation budgets. Those
    are required before enabling any supported upstream operation.
    """

    response_max_bytes: PositiveCount = 4 * 1024 * 1024
    request_timeout_seconds: PositiveFinite = 30.0
    connect_timeout_seconds: PositiveFinite = 10.0

    @model_validator(mode="after")
    def validate_deadlines(self) -> Self:
        if self.connect_timeout_seconds > self.request_timeout_seconds:
            raise ValueError("Connect timeout exceeds request timeout")
        return self


class SchedulerLimits(_ValidatedConfig):
    """Conservative service-local admission bounds, not Librus-approved quotas.

    Queue limits count waiting requests, separately from active requests. Rate
    tokens count every admitted attempt, including future auth/redirect/retry
    requests. Parent and student logins each occupy their own account slot.
    """

    requests_per_second: PositiveFinite = 1.0
    burst: PositiveCount = 1
    active_requests: PositiveCount = 2
    active_requests_per_account: PositiveCount = 1
    queued_requests: QueueCount = 32
    queued_requests_per_account: QueueCount = 8
    accounts: PositiveCount = 16

    @model_validator(mode="after")
    def validate_account_limits(self) -> Self:
        if self.active_requests_per_account > self.active_requests:
            raise ValueError("Account concurrency exceeds global concurrency")
        if self.queued_requests_per_account > self.queued_requests:
            raise ValueError("Account queue exceeds global queue")
        return self


class OperationLimits(_ValidatedConfig):
    """Whole-operation request/deadline bounds, including scheduler queue wait."""

    max_requests: PositiveCount = 32
    timeout_seconds: PositiveFinite = 120.0


DEFAULT_OPERATION_LIMITS = OperationLimits()
