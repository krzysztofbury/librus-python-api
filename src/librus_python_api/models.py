"""Shared transport, wire-validation, domain, and diagnostic data models.

Fields are validated at the parser boundary. Explicit serialization is the
consumer's responsibility. Domain result reprs omit personal data, including aliases.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from librus_python_api.exceptions import ErrorKind

type OperationName = Literal[
    "identity",
    "student_information",
    "final_grades",
    "grades",
    "attendance",
    "attendance_detail",
    "gateway_attendance",
    "subject_frequency",
    "timetable",
    "announcements",
    "agenda",
    "agenda_detail",
    "homework",
    "homework_detail",
    "completed_lessons",
    "messages_received",
    "messages_sent",
    "message_content_received",
    "message_content_sent",
    "attachment_resolve",
    "attachment_download",
    "recipient_groups",
    "recipients",
    "school_year_archive",
    "notification_counts",
    "consume_schedule_events",
    "decode_schedule_events",
    "send_message",
    "modern_identity",
    "modern_recipient_types",
    "modern_recipients",
    "modern_send_message",
    "modern_school_recipients",
    "modern_class_parents",
    "modern_archive_messages_received",
    "modern_archive_messages_sent",
    "modern_unread_counts",
    "modern_senders",
    "modern_receivers",
    "modern_teacher_subjects",
    "modern_messages_received",
    "modern_messages_sent",
    "modern_content_received",
    "modern_content_sent",
    "modern_attachment_resolve",
    "modern_archive_attachment_resolve",
    "modern_attachment_download",
]


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


class GradeView(StrEnum):
    ALL = "all"
    WEEK = "week"
    LAST_LOGIN = "last_login"


class AttendanceView(StrEnum):
    ALL = "all"
    WEEK = "week"
    LAST_LOGIN = "last_login"


class MessageFolder(StrEnum):
    RECEIVED = "received"
    SENT = "sent"


class SendStatus(StrEnum):
    NOT_DISPATCHED = "not_dispatched"
    UNKNOWN = "unknown"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MessagingBackend(StrEnum):
    LEGACY = "legacy"
    MODERN = "modern"


@dataclass(frozen=True, slots=True)
class SendSubmission:
    recipients: tuple["RecipientReference", ...] = field(repr=False)
    subject: str = field(repr=False)
    body: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SendResult:
    status: SendStatus
    reason: ErrorKind | Literal["cancelled"] | None = None
    identity: "Identity | None" = field(default=None, repr=False)
    observation: "Observation | None" = field(default=None, repr=False)
    backend: MessagingBackend = MessagingBackend.LEGACY


class NotificationCategory(StrEnum):
    GRADES = "grades"
    ATTENDANCE = "attendance"
    MESSAGES = "messages"
    ANNOUNCEMENTS = "announcements"
    AGENDA = "agenda"
    HOMEWORK = "homework"


@dataclass(frozen=True, slots=True)
class MessageReference:
    folder: MessageFolder
    identifier: str = field(repr=False)
    account: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MessageTimestamp:
    """School wall time, not a guessed UTC instant or DST fold."""

    local: datetime = field(repr=False)
    raw: str = field(repr=False)
    timezone: Literal["Europe/Warsaw"] = "Europe/Warsaw"


@dataclass(frozen=True, slots=True)
class MessageSummary:
    reference: MessageReference = field(repr=False)
    correspondent: str = field(repr=False)
    subject: str = field(repr=False)
    timestamp: MessageTimestamp = field(repr=False)
    unread: bool | None
    has_attachment: bool
    recipient_read_status: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class MessageAttachmentReference:
    message: MessageReference = field(repr=False)
    identifier: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MessageAttachment:
    reference: MessageAttachmentReference = field(repr=False)
    filename: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class AttachmentHeaders:
    content_type: str | None = field(repr=False)
    content_length: int | None
    content_disposition: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class AttachmentMetadata:
    identity: "Identity" = field(repr=False)
    reference: "MessageAttachmentReference | ModernMessageAttachmentReference" = field(
        repr=False
    )
    headers: AttachmentHeaders = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class MessageRecipientReceipt:
    recipient: str = field(repr=False)
    raw_status: str = field(repr=False)
    read_timestamp: MessageTimestamp | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class MessageContentData:
    reference: MessageReference = field(repr=False)
    correspondent: str | None = field(repr=False)
    subject: str = field(repr=False)
    timestamp: MessageTimestamp = field(repr=False)
    read_timestamp: MessageTimestamp | None = field(repr=False)
    text: str = field(repr=False)
    attachments: tuple[MessageAttachment, ...] = field(repr=False)
    recipient_receipts: tuple[MessageRecipientReceipt, ...] = field(
        default=(), repr=False
    )


@dataclass(frozen=True, slots=True)
class MessageContent:
    identity: "Identity" = field(repr=False)
    content: MessageContentData = field(repr=False)
    may_mark_read: bool
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class MessagesCursor:
    account: str = field(repr=False)
    folder: MessageFolder
    page: int
    offset: int
    page_count: int
    fingerprint: str = field(repr=False)
    seen_ids: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class MessagesPage:
    identity: "Identity" = field(repr=False)
    folder: MessageFolder
    page: int
    page_count: int
    items: tuple[MessageSummary, ...] = field(repr=False)
    fingerprint: str = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class Messages:
    identity: "Identity" = field(repr=False)
    folder: MessageFolder
    items: tuple[MessageSummary, ...] = field(repr=False)
    pages_fetched: int
    duplicates_skipped: int
    next_cursor: MessagesCursor | None = field(repr=False)
    truncation_reason: Literal["item_limit", "page_limit"] | None
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class RecipientGroupReference:
    identifier: str = field(repr=False)
    account: str = field(repr=False)
    selection_id: str = field(default="0", repr=False)


@dataclass(frozen=True, slots=True)
class RecipientGroup:
    reference: RecipientGroupReference = field(repr=False)
    label: str = field(repr=False)
    available: bool
    lookup_supported: bool


@dataclass(frozen=True, slots=True)
class RecipientReference:
    identifier: str = field(repr=False)
    account: str = field(repr=False)
    group_type: str = field(repr=False)
    selection_id: str = field(default="0", repr=False)


@dataclass(frozen=True, slots=True)
class Recipient:
    reference: RecipientReference = field(repr=False)
    label: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class RecipientGroupChoice:
    reference: RecipientGroupReference = field(repr=False)
    label: str = field(repr=False)
    available: bool


@dataclass(frozen=True, slots=True)
class RecipientGroupChoices:
    identity: "Identity" = field(repr=False)
    group: RecipientGroupReference = field(repr=False)
    items: tuple[RecipientGroupChoice, ...] = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class RecipientGroups:
    identity: "Identity" = field(repr=False)
    groups: tuple[RecipientGroup, ...] = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class Recipients:
    identity: "Identity" = field(repr=False)
    group: RecipientGroupReference = field(repr=False)
    items: tuple[Recipient, ...] = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class ModernRecipientTypeReference:
    identifier: str = field(repr=False)
    account: str = field(repr=False)
    include_virtual: bool = False


@dataclass(frozen=True, slots=True)
class ModernRecipientType:
    reference: ModernRecipientTypeReference = field(repr=False)
    label: str = field(repr=False)
    lookup_supported: bool


@dataclass(frozen=True, slots=True)
class ModernRecipientReference:
    account_id: str = field(repr=False)
    user_id: str = field(repr=False)
    account: str = field(repr=False)
    recipient_type: str = field(repr=False)
    class_label: str = field(repr=False)
    include_virtual: bool = False


@dataclass(frozen=True, slots=True)
class ModernRecipient:
    reference: ModernRecipientReference = field(repr=False)
    label: str = field(repr=False)
    availability_status_json: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ModernAccountData:
    account_id: str = field(repr=False)
    group_id: str
    first_name: str = field(repr=False)
    last_name: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ModernIdentity:
    identity: "Identity" = field(repr=False)
    account: ModernAccountData = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class ModernRecipientTypes:
    identity: "Identity" = field(repr=False)
    items: tuple[ModernRecipientType, ...] = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class ModernRecipients:
    identity: "Identity" = field(repr=False)
    recipient_type: ModernRecipientTypeReference = field(repr=False)
    items: tuple[ModernRecipient, ...] = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class ModernSendSubmission:
    recipients: tuple[ModernRecipientReference, ...] = field(repr=False)
    subject: str = field(repr=False)
    body: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ModernMessageReference:
    folder: MessageFolder
    identifier: str = field(repr=False)
    account: str = field(repr=False)
    # Listed from the archive mailbox. Archived content opens are not supported.
    archived: bool = False


@dataclass(frozen=True, slots=True)
class ModernCorrespondentReference:
    """A sender (received folder) or receiver (sent folder) to filter a list by."""

    folder: MessageFolder
    identifier: str = field(repr=False)
    account: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ModernCorrespondent:
    reference: ModernCorrespondentReference = field(repr=False)
    first_name: str = field(repr=False)
    last_name: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ModernCorrespondents:
    identity: "Identity" = field(repr=False)
    folder: MessageFolder
    items: tuple[ModernCorrespondent, ...] = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class ModernTeacherSubject:
    # The teacher's modern account ID, as a decimal string.
    teacher_identifier: str = field(repr=False)
    subject: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ModernTeacherSubjects:
    identity: "Identity" = field(repr=False)
    items: tuple[ModernTeacherSubject, ...] = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class ModernMessageSummary:
    reference: ModernMessageReference = field(repr=False)
    correspondent: str = field(repr=False)
    subject: str = field(repr=False)
    sent_at: datetime = field(repr=False)
    raw_sent_at: str = field(repr=False)
    read_at: datetime | None = field(repr=False)
    unread: bool | None
    has_attachment: bool


@dataclass(frozen=True, slots=True)
class ModernMessagesPage:
    identity: "Identity" = field(repr=False)
    folder: MessageFolder
    page: int
    page_size: int
    total_count: int
    items: tuple[ModernMessageSummary, ...] = field(repr=False)
    fingerprint: str = field(repr=False)
    observation: "Observation"
    archived: bool = False
    correspondent: ModernCorrespondentReference | None = field(default=None, repr=False)
    unread_only: bool = False
    # Archive listings only: the upstream archivingInProgress status flag.
    archiving_in_progress: bool | None = None


@dataclass(frozen=True, slots=True)
class ModernMessagesCursor:
    account: str = field(repr=False)
    folder: MessageFolder
    page: int
    offset: int
    page_size: int
    total_count: int
    fingerprint: str = field(repr=False)
    seen_ids: tuple[str, ...] = field(repr=False)
    archived: bool = False
    correspondent: str | None = field(default=None, repr=False)
    unread_only: bool = False


@dataclass(frozen=True, slots=True)
class ModernMessages:
    identity: "Identity" = field(repr=False)
    folder: MessageFolder
    items: tuple[ModernMessageSummary, ...] = field(repr=False)
    pages_fetched: int
    duplicates_skipped: int
    next_cursor: ModernMessagesCursor | None = field(repr=False)
    truncation_reason: Literal["item_limit", "page_limit"] | None
    observation: "Observation"
    archived: bool = False
    correspondent: ModernCorrespondentReference | None = field(default=None, repr=False)
    unread_only: bool = False
    # Archive listings only: the upstream archivingInProgress status flag.
    archiving_in_progress: bool | None = None


@dataclass(frozen=True, slots=True)
class ModernUnreadFolders:
    """Unread counters the modern mailbox shows for one mailbox section."""

    inbox: int
    notes: int
    alerts: int
    substitutions: int
    absences: int
    justifications: int
    trash: int


@dataclass(frozen=True, slots=True)
class ModernUnreadCounts:
    identity: "Identity" = field(repr=False)
    current: ModernUnreadFolders
    archive: ModernUnreadFolders
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class ModernMessageAttachmentReference:
    message: ModernMessageReference = field(repr=False)
    identifier: str = field(repr=False)
    archived: bool = False


@dataclass(frozen=True, slots=True)
class ModernMessageAttachment:
    reference: ModernMessageAttachmentReference = field(repr=False)
    filename: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ModernMessageRecipientReceipt:
    recipient_id: str = field(repr=False)
    name: str = field(repr=False)
    channel: Literal["to", "cc", "bcc"]
    read: bool | None
    read_at: datetime | None = field(repr=False)
    # The observed readed field is not an independent delivery acknowledgement.
    delivered: None = None


@dataclass(frozen=True, slots=True)
class ModernMessageContent:
    identity: "Identity" = field(repr=False)
    summary: ModernMessageSummary = field(repr=False)
    text: str = field(repr=False)
    attachments: tuple[ModernMessageAttachment, ...] = field(repr=False)
    may_mark_read: bool
    observation: "Observation"
    recipient_receipts: tuple[ModernMessageRecipientReceipt, ...] = field(
        default=(), repr=False
    )
    recipient_count: int | None = None
    read_count: int | None = None
    receipt_source: Literal["receivers", "individualRecipients"] | None = None
    archived: bool = False
    withdrawn: bool = False
    original_subject: str | None = field(default=None, repr=False)
    original_text: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CompletedLessonsCursor:
    account: str = field(repr=False)
    start: date = field(repr=False)
    end: date = field(repr=False)
    page: int
    offset: int
    page_count: int
    fingerprint: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SchoolReference:
    kind: Literal["agenda", "homework"]
    identifier: str = field(repr=False)
    account: str = field(repr=False)


# A credential submission keeps secrets out of reprs; other POST forms are
# built only by the fixed form functions in config.
type RequestForm = LoginSubmission | Mapping[str, str] | None


@dataclass(frozen=True, slots=True)
class CompletedLesson:
    day: date = field(repr=False)
    raw_day: str = field(repr=False)
    weekday: str = field(repr=False)
    lesson_number: int | None
    raw_lesson_number: str = field(repr=False)
    subject: str = field(repr=False)
    teacher: str | None = field(repr=False)
    subject_teacher_text: str = field(repr=False)
    topic: str = field(repr=False)
    z_value: str = field(repr=False)
    attendance_symbol: str = field(repr=False)
    attendance_detail_id: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class CompletedLessonsPage:
    identity: "Identity" = field(repr=False)
    start: date = field(repr=False)
    end: date = field(repr=False)
    page: int
    page_count: int
    items: tuple[CompletedLesson, ...] = field(repr=False)
    fingerprint: str = field(repr=False)
    observation: "Observation"


@dataclass(frozen=True, slots=True)
class CompletedLessons:
    identity: "Identity" = field(repr=False)
    start: date = field(repr=False)
    end: date = field(repr=False)
    items: tuple[CompletedLesson, ...] = field(repr=False)
    pages_fetched: int
    next_cursor: CompletedLessonsCursor | None = field(repr=False)
    observation: "Observation"


class GradeKind(StrEnum):
    CURRENT = "current"
    PERIOD = "period"
    PREDICTED_PERIOD = "predicted_period"
    ANNUAL = "annual"
    PREDICTED_ANNUAL = "predicted_annual"
    PUBLICATION = "publication"


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
class AccountContext:
    """Application-keyed login pseudonym, not credentials or an authority token."""

    alias: str = field(repr=False)
    identifier: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class NotificationCount:
    category: NotificationCategory
    label: str = field(repr=False)
    count: int


@dataclass(frozen=True, slots=True)
class NotificationCounts:
    identity: Identity = field(repr=False)
    items: tuple[NotificationCount, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class ScheduleEventWire:
    """HTTP payload bytes with transfer framing removed, before content decoding."""

    body: bytes = field(repr=False)
    content_type: str | None = field(repr=False)
    content_codings: tuple[str, ...] = field(repr=False)
    transfer_codings: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ScheduleEventResponse:
    version: int
    identity: Identity = field(repr=False)
    wire: ScheduleEventWire = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class RecentScheduleEvent:
    date_added: str = field(repr=False)
    type: str = field(repr=False)
    data: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ScheduleEvents:
    identity: Identity = field(repr=False)
    items: tuple[RecentScheduleEvent, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class TimetableInterval:
    starts_at: time
    ends_at: time


@dataclass(frozen=True, slots=True)
class TimetableLesson:
    subject: str = field(repr=False)
    teacher_and_classroom: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class TimetableChange:
    label: str = field(repr=False)
    metadata: tuple[tuple[str, str], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class TimetablePeriod:
    number: int
    interval: TimetableInterval
    lessons: tuple[TimetableLesson, ...] = field(repr=False)
    changes: tuple[TimetableChange, ...] = field(repr=False)
    next_recess: TimetableInterval | None


@dataclass(frozen=True, slots=True)
class TimetableDay:
    day: date = field(repr=False)
    periods: tuple[TimetablePeriod, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class Timetable:
    identity: Identity
    monday: date = field(repr=False)
    days: tuple[TimetableDay, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class Announcement:
    # A content-addressed account-scoped reference, never an upstream resource ID.
    reference: str = field(repr=False)
    title: str = field(repr=False)
    author: str = field(repr=False)
    date_text: str = field(repr=False)
    published_on: date = field(repr=False)
    content: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Announcements:
    identity: Identity
    items: tuple[Announcement, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class ArchiveCounts:
    """Counts per period as rendered; the year-end value is not checked as a sum."""

    first_semester: int
    second_semester: int
    year_end: int


@dataclass(frozen=True, slots=True)
class ArchiveAbsences:
    unexcused: ArchiveCounts
    excused: ArchiveCounts
    late: ArchiveCounts


@dataclass(frozen=True, slots=True)
class ArchiveMarks:
    """Rendered marks; "-" and empty text are preserved, never invented.

    `year_end` is the archive's year-end column, not asserted to equal the
    published annual grade of `SubjectGradeSummary`.
    """

    first_semester: str = field(repr=False)
    second_semester: str = field(repr=False)
    year_end: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ArchiveSubject:
    subject: str = field(repr=False)
    marks: ArchiveMarks = field(repr=False)


@dataclass(frozen=True, slots=True)
class ArchiveDescriptive:
    label: str = field(repr=False)
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ArchiveYear:
    """One earlier school year. Behaviour cells are raw positional text: the
    first-semester column and the cell spanning second semester and year end;
    their populated meaning is not established."""

    class_name: str = field(repr=False)
    school_year: str = field(repr=False)
    first_year: int = field(repr=False)
    subjects: tuple[ArchiveSubject, ...] = field(repr=False)
    descriptive: tuple[ArchiveDescriptive, ...] = field(repr=False)
    behaviour_first_semester: str = field(repr=False)
    behaviour_second_semester_and_year_end: str = field(repr=False)
    absences: ArchiveAbsences = field(repr=False)


@dataclass(frozen=True, slots=True)
class ArchiveAchievement:
    day: date = field(repr=False)
    class_name: str = field(repr=False)
    category: str = field(repr=False)
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SchoolYearArchive:
    identity: Identity
    years: tuple[ArchiveYear, ...] = field(repr=False)
    achievements: tuple[ArchiveAchievement, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class AgendaEvent:
    day: date = field(repr=False)
    title: str = field(repr=False)
    subject: str | None = field(repr=False)
    text: str = field(repr=False)
    lesson_number: int | None
    at_time: time | None
    metadata_text: str = field(repr=False)
    metadata: tuple[tuple[str, str], ...] = field(repr=False)
    metadata_notes: tuple[str, ...] = field(repr=False)
    reference: SchoolReference | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class AgendaDay:
    day: date = field(repr=False)
    events: tuple[AgendaEvent, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class Agenda:
    identity: Identity
    year: int
    month: int
    days: tuple[AgendaDay, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class HomeworkItem:
    subject: str = field(repr=False)
    teacher: str = field(repr=False)
    topic: str = field(repr=False)
    category: str = field(repr=False)
    assigned_on: date = field(repr=False)
    due_on: date = field(repr=False)
    # Raw solution-upload status; None when the school layout has no column.
    submission_status: str | None = field(repr=False)
    marked_done_at: datetime | None = field(repr=False)
    reference: SchoolReference | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class HomeworkRangeRequest:
    """Explicit bounded selection, validated by AccountClient before any I/O."""

    start: date
    end: date
    max_windows: int = 13
    max_items: int = 4096


@dataclass(frozen=True, slots=True)
class Homework:
    identity: Identity
    start: date = field(repr=False)
    end: date = field(repr=False)
    items: tuple[HomeworkItem, ...] = field(repr=False)
    observation: Observation


type DetailFieldKey = Literal[
    "date",
    "lesson_number",
    "teacher",
    "category",
    "subject",
    "room",
    "description",
    "published_at",
    "topic",
    "due_at",
    "content",
]


@dataclass(frozen=True, slots=True)
class DetailField:
    """Stable semantic key with bounded displayed text, not a parsed scalar."""

    key: DetailFieldKey | None
    raw_label: str = field(repr=False)
    value: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SchoolDetail:
    identity: Identity
    reference: SchoolReference = field(repr=False)
    title: str | None = field(repr=False)
    fields: tuple[tuple[str, str], ...] = field(repr=False)
    notes: tuple[str, ...] = field(repr=False)
    observation: Observation
    normalized_fields: tuple[DetailField, ...] = field(
        default=(), repr=False, compare=False
    )


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
class NumericGrade:
    """A school grade symbol, not an invented numeric conversion.

    Missing count/weight metadata is unknown, not False or zero. Links are inert
    upstream strings, never an authorized transport destination.
    """

    subject: str = field(repr=False)
    raw: str = field(repr=False)
    day: date = field(repr=False)
    semester: Literal[0, 1, 2]
    counts_toward_average: bool | None = field(repr=False)
    weight: int | None = field(repr=False)
    category: str | None = field(repr=False)
    teacher: str | None = field(repr=False)
    comment: str | None = field(repr=False)
    href: str | None = field(repr=False)
    metadata: tuple[tuple[str, str], ...] = field(repr=False)
    kind: GradeKind = GradeKind.CURRENT

    @property
    def formative_id(self) -> str | None:
        """The formative-assessment ID when `href` is a formative detail link.

        Computed, not a field: canonical notification IDs hash the record's
        fields, so stored identities stay unchanged.
        """
        # Lazy import: config imports this module.
        from librus_python_api.config import FORMATIVE_DETAIL_PATH_PREFIX
        from librus_python_api.markup import detail_id

        return detail_id(self.href, FORMATIVE_DETAIL_PATH_PREFIX)


@dataclass(frozen=True, slots=True)
class DescriptiveGrade:
    subject: str = field(repr=False)
    raw: str = field(repr=False)
    day: date = field(repr=False)
    semester: Literal[0, 1, 2] | None
    teacher: str | None = field(repr=False)
    comment: str | None = field(repr=False)
    metadata: tuple[tuple[str, str], ...] = field(repr=False)
    kind: GradeKind = GradeKind.CURRENT
    href: str | None = field(default=None, repr=False)

    @property
    def formative_id(self) -> str | None:
        """The formative-assessment ID when `href` is a formative detail link.

        Computed, not a field: canonical notification IDs hash the record's
        fields, so stored identities stay unchanged.
        """
        # Lazy import: config imports this module.
        from librus_python_api.config import FORMATIVE_DETAIL_PATH_PREFIX
        from librus_python_api.markup import detail_id

        return detail_id(self.href, FORMATIVE_DETAIL_PATH_PREFIX)


@dataclass(frozen=True, slots=True)
class SchoolAverage:
    """School-provided text only; semester zero means the annual column."""

    subject: str = field(repr=False)
    semester: Literal[0, 1, 2]
    value: GradeSummaryValue


@dataclass(frozen=True, slots=True)
class DescriptiveGradeSummary:
    """Undated semester text, never eligible for a dated grade window."""

    subject: str = field(repr=False)
    semester: Literal[1, 2]
    raw: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class FormativeGrade:
    """One row of the grades page's formative-assessment ("Oceny kształtujące")
    table. "KARTA SPOSTRZEŻEŃ" (observation card) appears as a subject value.
    The same item may also appear in the grid with a matching `formative_id`.
    """

    subject: str = field(repr=False)
    text: str = field(repr=False)
    category: str = field(repr=False)
    semester: Literal[1, 2]
    day: date = field(repr=False)
    assessment_type: str = field(repr=False)
    detail_id: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class GradeRecords:
    numeric: tuple[NumericGrade, ...] = field(repr=False)
    descriptive: tuple[DescriptiveGrade, ...] = field(repr=False)
    averages: tuple[SchoolAverage, ...] = field(repr=False)
    descriptive_summaries: tuple[DescriptiveGradeSummary, ...] = field(
        default=(), repr=False
    )
    formative: tuple[FormativeGrade, ...] = field(default=(), repr=False)


@dataclass(frozen=True, slots=True)
class Grades:
    identity: Identity
    records: GradeRecords
    observation: Observation
    view: GradeView = GradeView.ALL


@dataclass(frozen=True, slots=True)
class GradeWindow:
    identity: Identity
    start: date | None
    end: date | None
    numeric: tuple[NumericGrade, ...] = field(repr=False)
    descriptive: tuple[DescriptiveGrade, ...] = field(repr=False)
    observation: Observation
    view: GradeView = GradeView.ALL
    formative: tuple[FormativeGrade, ...] = field(default=(), repr=False)


@dataclass(frozen=True, slots=True)
class AttendanceRecord:
    symbol: str = field(repr=False)
    day: date = field(repr=False)
    semester: Literal[1, 2]
    attendance_type: str | None = field(repr=False)
    teacher: str | None = field(repr=False)
    period: int | None = field(repr=False)
    excursion: bool | None = field(repr=False)
    topic: str | None = field(repr=False)
    subject: str | None = field(repr=False)
    detail_id: str | None = field(repr=False)
    metadata: tuple[tuple[str, str], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class AttendanceRecords:
    items: tuple[AttendanceRecord, ...] = field(repr=False)
    semesters: tuple[Literal[1, 2], ...]


@dataclass(frozen=True, slots=True)
class Attendance:
    identity: Identity
    items: tuple[AttendanceRecord, ...] = field(repr=False)
    semesters: tuple[Literal[1, 2], ...]
    observation: Observation
    view: AttendanceView = AttendanceView.ALL


@dataclass(frozen=True, slots=True)
class AttendanceWindow:
    identity: Identity
    start: date | None
    end: date | None
    items: tuple[AttendanceRecord, ...] = field(repr=False)
    observation: Observation
    view: AttendanceView = AttendanceView.ALL


@dataclass(frozen=True, slots=True)
class AttendanceDetailContent:
    fields: tuple[tuple[str, str], ...] = field(repr=False)
    notes: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class AttendanceDetail:
    identity: Identity
    detail_id: str = field(repr=False)
    fields: tuple[tuple[str, str], ...] = field(repr=False)
    notes: tuple[str, ...] = field(repr=False)
    observation: Observation
    normalized_fields: tuple[DetailField, ...] = field(
        default=(), repr=False, compare=False
    )


class AttendanceKind(StrEnum):
    ABSENCE = "absence"
    LATE = "late"
    EXCUSED = "excused"
    EXEMPTION = "exemption"
    PRESENT = "present"
    EXCURSION = "excursion"
    CONTEST = "contest"
    TRAINING = "training"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GatewayAttendanceRecord:
    identifier: str | None = field(repr=False)
    day: date = field(repr=False)
    semester: Literal[1, 2]
    type_id: str = field(repr=False)
    kind: AttendanceKind
    lesson_id: str = field(repr=False)
    period: int | None


@dataclass(frozen=True, slots=True)
class GatewayAttendance:
    identity: Identity
    items: tuple[GatewayAttendanceRecord, ...] = field(repr=False)
    observation: Observation


@dataclass(frozen=True, slots=True)
class FrequencyMeasure:
    attended_count: int
    total_count: int
    excluded_count: int
    unknown_count: int
    ratio: float | None
    policy: Literal["overall", "subject"]


@dataclass(frozen=True, slots=True)
class AttendanceFrequency:
    identity: Identity
    first_semester: FrequencyMeasure
    second_semester: FrequencyMeasure
    overall: FrequencyMeasure
    observation: Observation


@dataclass(frozen=True, slots=True)
class SubjectFrequency:
    subject_id: str = field(repr=False)
    subject: str = field(repr=False)
    frequency: FrequencyMeasure


@dataclass(frozen=True, slots=True)
class SubjectFrequencies:
    identity: Identity
    items: tuple[SubjectFrequency, ...] = field(repr=False)
    start: date | None
    end: date | None
    observation: Observation


class _NumericReferenceWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Id: Annotated[str, Field(pattern=r"^[0-9]{1,64}$")]

    @field_validator("Id", mode="before")
    @classmethod
    def normalize_id(cls, value: Any) -> Any:
        return str(value) if type(value) is int and 0 <= value < 10**64 else value


class _AttendanceWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Id: Annotated[str | None, Field(pattern=r"^[0-9]{1,64}$")] = None
    Date: Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
    Semester: Literal[1, 2]
    Type: _NumericReferenceWire
    Lesson: _NumericReferenceWire
    LessonNo: Annotated[int | None, Field(ge=0, le=99)] = None

    @field_validator("Semester", mode="before")
    @classmethod
    def reject_boolean_semester(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Invalid semester type")
        return value

    @field_validator("Id", mode="before")
    @classmethod
    def normalize_id(cls, value: Any) -> Any:
        return _NumericReferenceWire.normalize_id(value)


class _AttendanceEnvelopeWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Attendances: Annotated[list[_AttendanceWire], Field(max_length=2048)]


class _LessonWire(_NumericReferenceWire):
    Subject: _NumericReferenceWire


class _LessonEnvelopeWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Lesson: _LessonWire


class _SubjectWire(_NumericReferenceWire):
    Name: Annotated[str, Field(min_length=1, max_length=1024)]


class _SubjectEnvelopeWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Subject: _SubjectWire


class _CollectionLessonWire(_NumericReferenceWire):
    # Collection rows may omit a subject; such lessons resolve individually.
    Subject: _NumericReferenceWire | None = None


class _LessonsEnvelopeWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Lessons: list[_CollectionLessonWire]


class _CollectionSubjectWire(_NumericReferenceWire):
    # Blank names resolve individually, where the strict subject contract applies.
    Name: Annotated[str | None, Field(max_length=1024)] = None


class _SubjectsEnvelopeWire(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    Subjects: list[_CollectionSubjectWire]


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
