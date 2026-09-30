"""Immutable library domain results, independent of consumer wire schemas.

Fields are validated at the parser boundary. Explicit serialization is the
consumer's responsibility. Reprs omit personal data, including account aliases.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from pydantic import SecretStr


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
