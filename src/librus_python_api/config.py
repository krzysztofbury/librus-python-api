"""Central network route catalogue and transport configuration.

Add fixed upstream paths here, never in parsers or account methods. The catalogue
is empty until the first independently evidenced network operation is enabled.
There is intentionally no public arbitrary authenticated URL interface.
"""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

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


@dataclass(frozen=True, slots=True)
class TransportLimits:
    """Per-request bounds used by the local transport evaluation.

    These do not implement service-wide scheduling or operation budgets. Those
    are required before enabling any supported upstream operation.
    """

    response_max_bytes: int = 4 * 1024 * 1024
    request_timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if type(self.response_max_bytes) is not int or self.response_max_bytes < 1:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        for value in (self.request_timeout_seconds, self.connect_timeout_seconds):
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
        if self.connect_timeout_seconds > self.request_timeout_seconds:
            raise LibrusError(ErrorKind.INVALID_INPUT)
