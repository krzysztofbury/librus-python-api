"""Shared transport, wire-validation, domain, and diagnostic data models.

Fields are validated at the parser boundary. Explicit serialization is the
consumer's responsibility. Domain result reprs omit personal data, including aliases.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from librus_python_api.exceptions import ErrorKind

type OperationName = Literal["identity", "student_information", "final_grades"]


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    body: bytes = field(repr=False)
    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class SchedulerSnapshot:
    active: int
    queued: int
    requests_dispatched: int


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    operation: OperationName
    outcome: ErrorKind | Literal["ok", "cancelled"]
    elapsed_seconds: float
    budget_requests_dispatched: int
    budget_response_bytes: int


@dataclass(frozen=True, slots=True)
class LoginSubmission:
    login: SecretStr = field(repr=False)
    password: SecretStr = field(repr=False)


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Person:
    id: str = field(repr=False)
    first_name: str | None = field(default=None, repr=False)
    last_name: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class Observation:
    account: str = field(repr=False)
    observed_at: datetime
    session_generation: int
    source: str


@dataclass(frozen=True, slots=True)
class Identity:
    owner: Person
    student: Person
    observation: Observation


@dataclass(frozen=True, slots=True)
class LuckyNumber:
    availability: Availability
    number: int | None = field(default=None, repr=False)
    day: date | None = None


@dataclass(frozen=True, slots=True)
class StudentInformation:
    identity: Identity
    name: str = field(repr=False)
    class_name: str = field(repr=False)
    register_number: int = field(repr=False)
    tutor: str = field(repr=False)
    school: str = field(repr=False)
    lucky_number: LuckyNumber
    observation: Observation


@dataclass(frozen=True, slots=True)
class GradeSummaryValue:
    """Column presence, separate from its raw school-provided value.

    Unavailable columns have raw=None. Available columns preserve empty strings,
    unassigned markers such as '-', symbols, and descriptive values without
    inventing numeric conversions or dates.
    """

    availability: Availability
    raw: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class SubjectGradeSummary:
    subject: str = field(repr=False)
    midterm: GradeSummaryValue
    predicted_annual: GradeSummaryValue
    annual: GradeSummaryValue


@dataclass(frozen=True, slots=True)
class FinalGrades:
    identity: Identity
    items: tuple[SubjectGradeSummary, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class ProfileFields:
    name: str = field(repr=False)
    class_name: str = field(repr=False)
    register_number: int = field(repr=False)
    tutor: str = field(repr=False)
    school: str = field(repr=False)
    lucky_number: LuckyNumber


class _PersonWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    FirstName: Annotated[str | None, Field(max_length=256)] = None
    LastName: Annotated[str | None, Field(max_length=256)] = None

    @field_validator("Id", mode="before")
    @classmethod
    def normalize_id(cls, value: Any) -> Any:
        if type(value) is int and 0 <= value < 10**64:
            return str(value)
        return value


class _AccountWire(_PersonWire):
    UserId: Annotated[str | None, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")] = None

    @field_validator("UserId", mode="before")
    @classmethod
    def normalize_user_id(cls, value: Any) -> Any:
        return cls.normalize_id(value)


class _UserWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Id: Annotated[str | None, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")] = None
    FirstName: Annotated[str | None, Field(max_length=256)] = None
    LastName: Annotated[str | None, Field(max_length=256)] = None

    @field_validator("Id", mode="before")
    @classmethod
    def normalize_id(cls, value: Any) -> Any:
        return _PersonWire.normalize_id(value)


class _MeWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Account: _AccountWire
    User: _UserWire


class _EnvelopeWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Me: _MeWire
