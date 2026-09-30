"""Central network route catalogue and transport configuration.

Add fixed upstream paths here, never in parsers or account methods. The catalogue
records source-informed routes with explicit offline/live evidence separation.
There is intentionally no public arbitrary authenticated URL interface.
"""

import re
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from librus_python_api.exceptions import ErrorKind, LibrusError

HttpMethod = Literal["GET", "POST"]


class SideEffect(StrEnum):
    NONE = "none"
    AUTHENTICATION = "authentication"
    MARK_READ = "mark_read"
    CONSUME_EVENTS = "consume_events"
    SEND_MESSAGE = "send_message"


class Evidence(StrEnum):
    SYNTHETIC_ONLY = "synthetic_only"
    SOURCE_INFORMED = "source_informed"
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
    origin: Literal["synergia", "api"] = "synergia"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", self.operation_id):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if self.method not in ("GET", "POST"):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if not re.fullmatch(r"/(?:[A-Za-z0-9_{}.-]+/)*[A-Za-z0-9_{}.-]*", self.path):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if any(segment in (".", "..") for segment in self.path.split("/")):
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
        if self.origin not in ("synergia", "api"):
            raise LibrusError(ErrorKind.INVALID_INPUT)


# Future login, JSON, messaging, and HTML routes all belong in this catalogue.
# Contract checks compare every method/path against the versioned OpenAPI YAML.
UPSTREAM_ORIGINS = MappingProxyType(
    {"synergia": "https://synergia.librus.pl", "api": "https://api.librus.pl"}
)
OAUTH_QUERY = (("client_id", "46"),)
SESSION_COOKIE = "oauth_token"
AUTH_COOKIES = frozenset({SESSION_COOKIE, "DZIENNIKSID", "SDZIENNIKSID"})
USER_AGENT = "librus-python-api/0.2 (independent client)"
ENDPOINTS: Mapping[str, Endpoint] = MappingProxyType(
    {
        item.operation_id: item
        for item in (
            Endpoint(
                "login_portal",
                "GET",
                "/loguj/portalRodzina",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "login_authorization",
                "GET",
                "/OAuth/Authorization",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "api",
            ),
            Endpoint(
                "login_submit",
                "POST",
                "/OAuth/Authorization",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "api",
            ),
            Endpoint(
                "login_continue",
                "GET",
                "/OAuth/Authorization/2FA",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "api",
            ),
            Endpoint(
                "login_callback",
                "GET",
                "/loguj",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.SYNTHETIC_ONLY,
            ),
            Endpoint(
                "login_perform",
                "GET",
                "/OAuth/Authorization/PerformLogin",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "api",
            ),
            Endpoint(
                "login_grant",
                "GET",
                "/OAuth/Authorization/Grant",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "api",
            ),
            Endpoint(
                "login_landing",
                "GET",
                "/",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.SYNTHETIC_ONLY,
            ),
            Endpoint(
                "login_student_landing",
                "GET",
                "/uczen/index",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.SOURCE_INFORMED,
            ),
            Endpoint(
                "identity",
                "GET",
                "/gateway/api/2.0/Me",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "student_information",
                "GET",
                "/informacja",
                SideEffect.NONE,
                True,
                Evidence.SOURCE_INFORMED,
            ),
            Endpoint(
                "final_grades",
                "GET",
                "/przegladaj_oceny/uczen",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
        )
    }
)
# Semantic HTML labels are configuration, not positional parser assumptions.
PROFILE_LABELS = MappingProxyType(
    {
        "Uczeń": "name",
        "Imię i nazwisko": "name",
        "Klasa": "class_name",
        "Numer w dzienniku": "register_number",
        "Nr w dzienniku": "register_number",
        "Wychowawca": "tutor",
        "Szkoła": "school",
    }
)

# HTML summary headers omit the two leading body cells: expander and subject.
# These labels/layout rules are source-informed requirements, not live evidence.
GRADE_SUMMARY_HEADERS = MappingProxyType(
    {
        "Ocena śródroczna z pierwszego okresu": "midterm",
        "Przewidywana ocena roczna": "predicted_annual",
        "Ocena roczna": "annual",
    }
)
GRADE_BODY_PREFIX_COLUMNS = 2
GRADE_MAX_COLUMNS = 64
GRADE_MAX_SUBJECTS = 128
GRADE_MAX_VALUE_LENGTH = 1024
GRADE_MERGED_SUBJECTS = frozenset({"Zachowanie"})
GRADE_INLINE_DETAIL_LABEL = "Ocena"


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
    max_redirects: PositiveCount = 10
    max_cookies: PositiveCount = 128
    parse_max_bytes: PositiveCount = 256 * 1024
    cooldown_seconds: PositiveFinite = 60.0

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
    operations: PositiveCount = 32
    operations_per_account: PositiveCount = 8

    @model_validator(mode="after")
    def validate_account_limits(self) -> Self:
        if self.active_requests_per_account > self.active_requests:
            raise ValueError("Account concurrency exceeds global concurrency")
        if self.queued_requests_per_account > self.queued_requests:
            raise ValueError("Account queue exceeds global queue")
        if self.operations_per_account > self.operations:
            raise ValueError("Account operation bound exceeds global bound")
        return self


class OperationLimits(_ValidatedConfig):
    """Whole-operation request/deadline bounds, including scheduler queue wait."""

    max_requests: PositiveCount = 32
    timeout_seconds: PositiveFinite = 120.0
    max_response_bytes: PositiveCount = 4 * 1024 * 1024


class AccountCredentials(_ValidatedConfig):
    """Explicit login secrets and optional independent identity expectations."""

    login: SecretStr = Field(repr=False)
    password: SecretStr = Field(repr=False)
    expected_owner_id: str | None = Field(default=None, repr=False)
    expected_student_id: str | None = Field(default=None, repr=False)

    def __init__(
        self,
        *,
        login: str | SecretStr,
        password: str | SecretStr,
        expected_owner_id: str | None = None,
        expected_student_id: str | None = None,
    ) -> None:
        super().__init__(
            login=login,
            password=password,
            expected_owner_id=expected_owner_id,
            expected_student_id=expected_student_id,
        )

    @model_validator(mode="after")
    def validate_account(self) -> Self:
        if not 1 <= len(self.login.get_secret_value()) <= 256:
            raise ValueError("Invalid login length")
        if not 1 <= len(self.password.get_secret_value()) <= 1024:
            raise ValueError("Invalid password length")
        for value in (self.expected_owner_id, self.expected_student_id):
            if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
                raise ValueError("Invalid expected identity")
        return self


DEFAULT_OPERATION_LIMITS = OperationLimits()


class ConnectionSettings(_ValidatedConfig):
    """Explicit verified TLS/proxy settings; HTTP is allowed only on loopback.

    Origin overrides support local fixture servers, not arbitrary authenticated
    destinations. Redirects must additionally match the fixed route catalogue.
    """

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        hide_input_in_errors=True,
        arbitrary_types_allowed=True,
    )
    synergia_origin: str = UPSTREAM_ORIGINS["synergia"]
    api_origin: str = UPSTREAM_ORIGINS["api"]
    proxy_url: SecretStr | None = Field(default=None, repr=False)
    ssl_context: ssl.SSLContext | None = Field(default=None, repr=False)

    @field_validator("synergia_origin", "api_origin")
    @classmethod
    def validate_origin(cls, value: str, info: ValidationInfo) -> str:
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Only origin URLs are allowed")
        local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        expected = (
            "api.librus.pl" if info.field_name == "api_origin" else "synergia.librus.pl"
        )
        official = parsed.hostname == expected
        if not local and not (
            official and parsed.scheme == "https" and port in (None, 443)
        ):
            raise ValueError("Destination is not an approved origin")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Unsupported URL scheme")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_security(self) -> Self:
        context = self.ssl_context
        if context is not None and (
            context.verify_mode != ssl.CERT_REQUIRED
            or not context.check_hostname
            or context.minimum_version < ssl.TLSVersion.TLSv1_2
        ):
            raise ValueError("TLS verification and TLS 1.2 or newer are required")
        if self.proxy_url is not None:
            parsed = urlsplit(self.proxy_url.get_secret_value())
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("Unsupported explicit proxy")
        return self

    def origin(self, endpoint: Endpoint) -> str:
        return self.api_origin if endpoint.origin == "api" else self.synergia_origin
