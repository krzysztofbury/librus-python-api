"""Neutral optional notification delivery and recovery values, never MCP DTOs."""

from dataclasses import dataclass, field
from enum import StrEnum

from librus_python_api.models import (
    AccountContext,
    Announcement,
    AttendanceRecord,
    DescriptiveGrade,
    HomeworkItem,
    Identity,
    MessageSummary,
    MessagingBackend,
    ModernMessageSummary,
    NotificationCategory,
    NumericGrade,
    Observation,
    RecentScheduleEvent,
)

type NotificationValue = (
    NumericGrade
    | DescriptiveGrade
    | AttendanceRecord
    | MessageSummary
    | ModernMessageSummary
    | Announcement
    | HomeworkItem
    | RecentScheduleEvent
)


class NotificationProvenance(StrEnum):
    OBSERVED = "observed"
    IMPORTED_HISTORY = "imported_history"


@dataclass(frozen=True, slots=True)
class NotificationItem:
    category: NotificationCategory
    identifier: str = field(repr=False)
    value: NotificationValue = field(repr=False)
    identity: Identity | None = field(repr=False)
    observation: Observation | None = field(repr=False)
    provenance: NotificationProvenance = NotificationProvenance.OBSERVED


@dataclass(frozen=True, slots=True)
class NotificationBatch:
    receipt: str = field(repr=False)
    context: AccountContext = field(repr=False)
    first_run: bool
    categories: tuple[NotificationCategory, ...]
    items: tuple[NotificationItem, ...] = field(repr=False)
    has_more_schedule: bool
    messages_backend: MessagingBackend = MessagingBackend.LEGACY


@dataclass(frozen=True, slots=True)
class NotificationSeen:
    category: NotificationCategory
    identifiers: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class NotificationState:
    initialized: bool
    seen: tuple[NotificationSeen, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class NotificationArchive:
    """Versioned neutral bytes; includes private raw envelopes and pending delivery."""

    version: int
    context: AccountContext = field(repr=False)
    payload: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class NotificationBaselineMapping:
    """Caller-established mapping; None means explicitly unmappable."""

    category: NotificationCategory
    source_identifier: str = field(repr=False)
    native_identifier: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class NotificationBootstrap:
    """Neutral offline inputs, never a consumer's files or fabricated raw pages."""

    context: AccountContext = field(repr=False)
    mappings: tuple[NotificationBaselineMapping, ...] = field(repr=False)
    pending_events: tuple[RecentScheduleEvent, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class NotificationBootstrapResult:
    """Unmapped inputs prevent every write; successful history has a durable receipt."""

    imported: bool
    unmapped: tuple[NotificationBaselineMapping, ...] = field(repr=False)
    pending: NotificationBatch | None = field(repr=False)
