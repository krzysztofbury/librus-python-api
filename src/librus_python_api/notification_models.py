"""Neutral optional notification delivery and recovery values, never MCP DTOs."""

from dataclasses import dataclass, field

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


@dataclass(frozen=True, slots=True)
class NotificationItem:
    category: NotificationCategory
    identifier: str = field(repr=False)
    value: NotificationValue = field(repr=False)
    identity: Identity = field(repr=False)
    observation: Observation = field(repr=False)


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
