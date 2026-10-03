"""Central network route catalogue and transport configuration.

Add fixed upstream paths here, never in parsers or account methods. The catalogue
records source-informed routes with explicit offline/live evidence separation.
There is intentionally no public arbitrary authenticated URL interface.
"""

import base64
import calendar
import json
import re
import ssl
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from html import escape
from types import MappingProxyType
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlencode, urlsplit

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
from librus_python_api.models import (
    AttendanceView,
    GradeView,
    MessageFolder,
    ModernRecipientReference,
    ModernSendSubmission,
    RecipientReference,
    SendSubmission,
)

HttpMethod = Literal["GET", "POST"]


class SideEffect(StrEnum):
    NONE = "none"
    AUTHENTICATION = "authentication"
    MARK_READ = "mark_read"
    CONSUME_EVENTS = "consume_events"
    SEND_MESSAGE = "send_message"
    SELECT_VIEW = "select_view"


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
    origin: Literal["synergia", "api", "download", "messages"] = "synergia"

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
        if self.origin not in ("synergia", "api", "download", "messages"):
            raise LibrusError(ErrorKind.INVALID_INPUT)


# Future login, JSON, messaging, and HTML routes all belong in this catalogue.
# Contract checks compare every method/path against the versioned OpenAPI YAML.
UPSTREAM_ORIGINS = MappingProxyType(
    {
        "synergia": "https://synergia.librus.pl",
        "api": "https://api.librus.pl",
        "download": "https://sandbox.librus.pl",
        "messages": "https://wiadomosci.librus.pl",
    }
)
OAUTH_QUERY = (("client_id", "46"),)
SESSION_COOKIE = "oauth_token"
AUTH_COOKIES = frozenset({SESSION_COOKIE, "DZIENNIKSID", "SDZIENNIKSID"})
USER_AGENT = "librus-python-api/0.4 (independent client)"
ENDPOINTS: Mapping[str, Endpoint] = MappingProxyType(
    {
        item.operation_id: item
        for item in (
            Endpoint(
                "modern_launch",
                "GET",
                "/wiadomosci3",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "modern_handoff",
                "GET",
                "/pobierz28/MultiDomainLogon/token/{token}/login/{login}/target/{target}/from/{source}",
                SideEffect.AUTHENTICATION,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "messages",
            ),
            Endpoint(
                "modern_identity",
                "GET",
                "/api/me",
                SideEffect.NONE,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "messages",
            ),
            Endpoint(
                "modern_recipient_types",
                "GET",
                "/api/receivers/types",
                SideEffect.NONE,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "messages",
            ),
            Endpoint(
                "modern_recipients",
                "GET",
                "/api/receivers/groups/students-and-attendants",
                SideEffect.NONE,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
                "messages",
            ),
            Endpoint(
                "modern_send_message",
                "POST",
                "/api/messages",
                SideEffect.SEND_MESSAGE,
                False,
                Evidence.SOURCE_INFORMED,
                "messages",
            ),
            Endpoint(
                "consume_schedule_events",
                "GET",
                "/terminarz/dodane_od_ostatniego_logowania",
                SideEffect.CONSUME_EVENTS,
                False,
                Evidence.SOURCE_INFORMED,
            ),
            Endpoint(
                "attachment_resolve",
                "GET",
                "/wiadomosci/pobierz_zalacznik/{message_id}/{file_id}",
                SideEffect.NONE,
                False,
                Evidence.SOURCE_INFORMED,
            ),
            Endpoint(
                "attachment_download",
                "GET",
                "/GetFile/{key}/get",
                SideEffect.NONE,
                False,
                Evidence.SOURCE_INFORMED,
                "download",
            ),
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
                "notification_counts",
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
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "final_grades",
                "GET",
                "/przegladaj_oceny/uczen",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "grades",
                "POST",
                "/przegladaj_oceny/uczen",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "attendance",
                "POST",
                "/przegladaj_nb/uczen",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "attendance_detail",
                "GET",
                "/przegladaj_nb/szczegoly/{id}",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "gateway_attendance",
                "GET",
                "/gateway/api/2.0/Attendances",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "attendance_lesson",
                "GET",
                "/gateway/api/2.0/Lessons/{id}",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "attendance_subject",
                "GET",
                "/gateway/api/2.0/Subjects/{id}",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "timetable",
                "POST",
                "/przegladaj_plan_lekcji",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "announcements",
                "GET",
                "/ogloszenia",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "agenda",
                "POST",
                "/terminarz/",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "agenda_detail",
                "GET",
                "/terminarz/szczegoly/{id}",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "homework",
                "POST",
                "/moje_zadania",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "completed_lessons",
                "POST",
                "/zrealizowane_lekcje",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.SOURCE_INFORMED,
            ),
            # Internal ordinary-read discovery only. No public note capability is
            # enabled until independently observed populated semantics exist.
            Endpoint(
                "behaviour_notes_probe",
                "GET",
                "/uwagi",
                SideEffect.NONE,
                False,
                Evidence.SOURCE_INFORMED,
            ),
            Endpoint(
                "homework_detail",
                "GET",
                "/moje_zadania/podglad/{id}",
                SideEffect.NONE,
                True,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "messages_received",
                "POST",
                "/wiadomosci/1/5",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "messages_sent",
                "POST",
                "/wiadomosci/1/6",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "send_message",
                "POST",
                "/wiadomosci/1/6",
                SideEffect.SEND_MESSAGE,
                False,
                Evidence.SOURCE_INFORMED,
            ),
            Endpoint(
                "recipient_groups",
                "GET",
                "/wiadomosci/2/6",
                SideEffect.SELECT_VIEW,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "message_content_received",
                "GET",
                "/wiadomosci/1/5/{id}",
                SideEffect.MARK_READ,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "message_content_sent",
                "GET",
                "/wiadomosci/1/6/{id}",
                SideEffect.NONE,
                False,
                Evidence.INDEPENDENTLY_OBSERVED,
            ),
            Endpoint(
                "recipients",
                "POST",
                "/getRecipients",
                SideEffect.SELECT_VIEW,
                False,
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
        "Imię i nazwisko ucznia": "name",
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
GRADE_VIEW_FIELDS = MappingProxyType(
    {
        "all": "zmiany_logowanie_wszystkie",
        "week": "zmiany_logowanie_tydzien",
        "last_login": "zmiany_logowanie",
    }
)
GRADE_CURRENT_HEADER = "Oceny bieżące"
GRADE_EMPTY_MARKERS = frozenset({"", "-", "Brak ocen"})
GRADE_AVERAGE_HEADERS = MappingProxyType(
    {"Średnia ocen": 1, "Średnia ocen z drugiego okresu": 2, "Średnia roczna": 0}
)
GRADE_MAX_RECORDS = 2048
GRADE_MAX_METADATA_LENGTH = 8192
GRADE_MAX_METADATA_FIELDS = 32
GRADE_MAX_WINDOW_DAYS = 366
GRADE_PERIOD_HEADERS = MappingProxyType(
    {
        "Ocena śródroczna z pierwszego okresu": 1,
        "Ocena śródroczna z drugiego okresu": 2,
        "Ocena roczna": 0,
    }
)
GRADE_PREDICTED_ANNUAL_HEADER = "Przewidywana ocena roczna"
GRADE_PREDICTED_PERIOD_HEADERS = MappingProxyType(
    {
        "Przewidywana ocena śródroczna z pierwszego okresu": 1,
        "Przewidywana ocena śródroczna z drugiego okresu": 2,
    }
)
GRADE_PUBLICATION_DATE_LABEL = "opublikowano:"
GRADE_PUBLICATION_TEACHER_LABEL = "nauczyciel:"
GRADE_PUBLICATION_PERIOD_LABELS = MappingProxyType(
    {
        "pierwszy okres": 1,
        "pierwszego okresu": 1,
        "I okres": 1,
        "drugi okres": 2,
        "drugiego okresu": 2,
        "II okres": 2,
    }
)

ATTENDANCE_VIEW_FORMS = MappingProxyType(
    {
        "all": ("zmiany_logowanie_wszystkie", ""),
        "week": ("zmiany_logowanie_tydzien", "zmiany_logowanie_tydzien"),
        "last_login": ("zmiany_logowanie", "zmiany_logowanie"),
    }
)
ATTENDANCE_SEMESTER_LABELS = MappingProxyType(
    {
        "i okres": 1,
        "ii okres": 2,
        "pierwszy okres": 1,
        "drugi okres": 2,
        "i semestr": 1,
        "ii semestr": 2,
        "okres 1": 1,
        "okres 2": 2,
    }
)
ATTENDANCE_EMPTY_MARKERS = frozenset({"", "-", "Brak nieobecności"})
ATTENDANCE_MAX_RECORDS = 2048
ATTENDANCE_MAX_WINDOW_DAYS = 366
# Collection recognition and detail retrieval share this central path family.
ATTENDANCE_DETAIL_PATH_PREFIX = "/przegladaj_nb/szczegoly/"
ATTENDANCE_DETAIL_MAX_FIELDS = 32
ATTENDANCE_METADATA_CACHE_SIZE = 256
ATTENDANCE_RESULT_CACHE_SIZE = 64
ATTENDANCE_METADATA_TTL_SECONDS = 3600

ANNOUNCEMENT_MAX_ITEMS = 256
ANNOUNCEMENT_MAX_FIELD_LENGTH = 1024
ANNOUNCEMENT_MAX_CONTENT_LENGTH = 65536
ANNOUNCEMENT_MAX_TOTAL_TEXT_LENGTH = 262144
ANNOUNCEMENT_TABLE_CLASSES = frozenset(
    {"decorated", "big", "center", "printable", "margin-top"}
)
ANNOUNCEMENT_LABELS = MappingProxyType(
    {
        "dodał": "author",
        "autor": "author",
        "data publikacji": "date_text",
        "data": "date_text",
        "treść": "content",
    }
)
ANNOUNCEMENT_EMPTY_CLASSES = frozenset(
    {"container", "border-red", "resizeable", "center"}
)
ANNOUNCEMENT_EMPTY_MARKERS = frozenset({"brak ogłoszeń", "nie ma ogłoszeń"})
TIMETABLE_MAX_PERIODS = 32
TIMETABLE_MAX_LESSONS_PER_SLOT = 16
TIMETABLE_MAX_CHANGES_PER_SLOT = 16
TIMETABLE_WEEK_FIELD = "tydzien"
TIMETABLE_DATE_ATTRIBUTE = "data-date"
TIMETABLE_START_ATTRIBUTE = "data-time_from"
TIMETABLE_END_ATTRIBUTE = "data-time_to"

SCHOOL_MAX_ITEMS = 2048
CHECKPOINT_TIMEOUT_SECONDS = 5.0
CHECKPOINT_MAX_TIMEOUT_SECONDS = 30.0
SCHEDULE_RESPONSE_VERSION = 1
SCHEDULE_MAX_EVENTS = 1024
NOTIFICATION_MAX_MENU_ITEMS = 64
NOTIFICATION_MAX_COUNT = 1000000
NOTIFICATION_DESTINATIONS = MappingProxyType(
    {
        "/przegladaj_oceny/uczen": "grades",
        "/przegladaj_nb/uczen": "attendance",
        "/wiadomosci": "messages",
        "/ogloszenia": "announcements",
        "/terminarz": "agenda",
        "/moje_zadania": "homework",
    }
)
SCHEDULE_EVENT_HEADERS = ("lp.", "czas dodania", "rodzaj zdarzenia", "dane")
SCHEDULE_EMPTY_LABEL = "Brak zdarzeń"
SCHOOL_MAX_CONTENT_LENGTH = 65536
SCHOOL_MAX_TOTAL_TEXT_LENGTH = 262144
SCHOOL_MAX_DETAIL_FIELDS = 64
SCHOOL_MAX_FIELD_LENGTH = 1024
SCHOOL_MAX_TOOLTIP_LENGTH = 8192
# Tooltips carry one line per <br>; a long description can span dozens.
SCHOOL_MAX_TOOLTIP_LINES = 256
# Observed agenda tooltip labels. Lines after "Opis" continue the description
# until the next label, so numbered description lines never become fields.
AGENDA_TOOLTIP_LABELS = frozenset({"Nauczyciel", "Opis", "Data dodania"})
AGENDA_DESCRIPTION_LABEL = "Opis"
HOMEWORK_MAX_COLUMNS = 32
# Observed header labels. Date columns span two cells: a date and its weekday.
HOMEWORK_COLUMNS = MappingProxyType(
    {
        "Przedmiot": "subject",
        "Nauczyciel": "teacher",
        "Temat": "topic",
        "Kategoria": "category",
        "Data zadania": "assigned",
        "Termin wykonania": "due",
        "Status przesyłania rozwiązania": "submission_status",
        "Opcje": "options",
    }
)
HOMEWORK_DONE_PATTERN = (
    r"Zadanie oznaczono jako wykonane \(([0-9]{4}-[0-9]{2}-[0-9]{2}), "
    r"([0-9]{2}:[0-9]{2})\)"
)
HOMEWORK_MARK_DONE_HANDLER = (
    r"\s*showConfirmQuestion\(\s*[0-9]{1,64}\s*,\s*[0-9]{1,64}\s*\);?\s*"
)
WEEKDAY_LABELS = ("pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "ndz.")
# Observed page-level notices shown instead of the requested content.
PAGE_NOTICES = MappingProxyType(
    {
        "Ten widok został wyłączony przez administratora szkoły.": (
            ErrorKind.VIEW_DISABLED
        ),
        "Wybrano nieprawidłowy zakres daty.": ErrorKind.INVALID_INPUT,
    }
)
COMPLETED_LESSONS_MAX_WINDOW_DAYS = 371
COMPLETED_LESSONS_MAX_PAGE_COUNT = 1000
COMPLETED_LESSONS_MAX_PAGE_ITEMS = 256
COMPLETED_LESSONS_MAX_BATCH_PAGES = 8
COMPLETED_LESSONS_MAX_BATCH_ITEMS = 256
AGENDA_DETAIL_PATH_PREFIX = "/terminarz/szczegoly/"
HOMEWORK_DETAIL_PATH_PREFIX = "/moje_zadania/podglad/"
MESSAGE_MAX_PAGE_COUNT = 1000
MESSAGE_MAX_PAGE_ITEMS = 50
MESSAGE_MAX_BATCH_PAGES = 8
MESSAGE_MAX_BATCH_ITEMS = 256
MESSAGE_MAX_CURSOR_IDS = 2000
MESSAGE_MAX_FIELD_LENGTH = 4096
MESSAGE_MAX_TOTAL_TEXT_LENGTH = 262144
MESSAGE_EMPTY_TEXT = "Brak wiadomości"
MESSAGE_INFORMATION_NOTICES = frozenset(
    {
        "Korzystasz ze starej wersji modułu Wiadomości, która nie jest już rozwijana "
        "i nie zawiera wszystkich dostępnych funkcji. Przejdź do ustawień i włącz "
        "opcję: Używaj nowego systemu wiadomości."
    }
)
MESSAGE_HEADER_LABELS = MappingProxyType(
    {MessageFolder.RECEIVED: "Nadawca", MessageFolder.SENT: "Adresat"}
)
MESSAGE_PAGE_FIELDS = frozenset({"numer_strony105", "porcjowanie_pojemnik105"})
# Reference and attachment paths are inert data, never arbitrary fetched URLs.
MESSAGE_REFERENCE_PREFIXES = MappingProxyType(
    {MessageFolder.RECEIVED: "/wiadomosci/1/5/", MessageFolder.SENT: "/wiadomosci/1/6/"}
)
MESSAGE_ATTACHMENT_PATH_PREFIX = "/wiadomosci/pobierz_zalacznik/"
MESSAGE_MAX_CONTENT_LENGTH = 65536
MESSAGE_MAX_ATTACHMENTS = 20
MESSAGE_MAX_RECIPIENT_RECEIPTS = 256
MESSAGE_MAX_RECEIPT_TEXT_LENGTH = 131072
SEND_MAX_RECIPIENTS = 50
SEND_MAX_SUBJECT_CHARACTERS = 200
SEND_MAX_BODY_CHARACTERS = 15000
SEND_MAX_REQUEST_BYTES = 64 * 1024
SEND_ACCEPTED_TEXT = "Wiadomość została wysłana."
SEND_REJECTED_TEXT = "Wiadomość nie została wysłana."
MODERN_DIRECTORY_TYPE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]{0,63}")
MODERN_HANDOFF_PATTERN = re.compile(
    r"/pobierz28/MultiDomainLogon/token/([A-Za-z0-9]{32,256})/login/([A-Za-z0-9_=+-]{1,512})/target/L25vd3k/from/c3luZXJnaWE"
)
MODERN_TERMINAL_PATHS = frozenset({"/nowy", "/nowy/"})
MODERN_DIRECTORY_QUERIES = MappingProxyType(
    {
        "modern_recipient_types": (("includeClass", "true"),),
        "modern_recipients": (("receiverType", "parentsCouncil"),),
    }
)
MODERN_SUPPORTED_RECIPIENT_TYPE = "parentsCouncil"
MODERN_SUPPORTED_ACCOUNT_GROUPS = frozenset({"5", "8", "9"})
MODERN_MAX_CLASSES = 128
MODERN_MAX_RECIPIENTS = 2048
MODERN_MAX_TYPES = 32
MODERN_MAX_LABEL = 1024
MODERN_MAX_TOTAL_TEXT = 128 * 1024
MODERN_REJECTION_CODES = frozenset(
    {"DUPLICATED_RECEIVERS", "THE_RECEIVER_CANNOT_RECEIVE_A_NOTE_COPY"}
)
ATTACHMENT_MAX_BYTES = 50 * 1024 * 1024
ATTACHMENT_CHUNK_BYTES = 64 * 1024
ATTACHMENT_MAX_LOCATION_LENGTH = 2048
ATTACHMENT_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.~-]{1,512}\Z")
ATTACHMENT_REDIRECT_PATH = "/GetFile/{key}"

RECIPIENT_FORM_FIELDS = frozenset(
    {"typAdresata", "poprzednia", "tabZaznaczonych", "czyWirtualneKlasy", "idGrupy"}
)
RECIPIENT_GROUP_TYPE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
RECIPIENT_MAX_GROUPS = 32
RECIPIENT_MAX_ITEMS = 2048
RECIPIENT_MAX_LABEL_LENGTH = 1024
RECIPIENT_MAX_TOTAL_TEXT_LENGTH = 131072
RECIPIENT_UNSUPPORTED_TYPES = frozenset({"grupa"})
RECIPIENT_SELECTION_PROMPT = "Wybierz grupę"
RECIPIENT_CLASS_UNAVAILABLE_NOTICE = (
    "Uczeń nie jest przydzielony do klasy. W celu wyjaśnienia sytuacji prosimy "
    "o kontakt ze szkołą"
)


def recipient_form(group_type: str, *, selection_id: str = "0") -> dict[str, str]:
    if (
        type(group_type) is not str
        or RECIPIENT_GROUP_TYPE_PATTERN.fullmatch(group_type) is None
        or type(selection_id) is not str
        or re.fullmatch(r"0|[1-9][0-9]{0,63}", selection_id) is None
        or (selection_id != "0" and group_type != "grupa")
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return {
        "typAdresata": group_type,
        "poprzednia": "5",
        "tabZaznaczonych": "",
        "czyWirtualneKlasy": "false",
        "idGrupy": selection_id,
    }


def encode_send_form(submission: SendSubmission, account: str) -> bytes:
    """Exact bounded legacy send variant; text is never silently transformed."""
    if (
        not isinstance(submission, SendSubmission)
        or type(submission.recipients) is not tuple
        or not 1 <= len(submission.recipients) <= SEND_MAX_RECIPIENTS
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    for value, limit, whitespace in (
        (submission.subject, SEND_MAX_SUBJECT_CHARACTERS, ""),
        (submission.body, SEND_MAX_BODY_CHARACTERS, "\r\n\t"),
    ):
        if (
            type(value) is not str
            or not 1 <= len(value) <= limit
            or not value.strip()
            or any(
                unicodedata.category(c) in {"Cc", "Cs"} and c not in whitespace
                for c in value
            )
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
    seen: set[str] = set()
    fields = [("filtrUzytkownikow", "0"), ("idPojemnika", "")]
    for reference in submission.recipients:
        if (
            not isinstance(reference, RecipientReference)
            or reference.account != account
            or type(reference.identifier) is not str
            or re.fullmatch(r"[0-9]{1,64}", reference.identifier) is None
            or reference.identifier in seen
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        recipient_form(reference.group_type, selection_id=reference.selection_id)
        seen.add(reference.identifier)
        fields.append(("DoKogo", reference.identifier))
    fields.extend(
        (
            ("Rodzaj", "0"),
            ("temat", submission.subject),
            ("tresc", submission.body),
            ("poprzednia", "5"),
            ("fileStorageIdentifier", ""),
            ("wyslij", "Wyślij"),
        )
    )
    payload = urlencode(fields, encoding="utf-8", errors="strict").encode("ascii")
    if len(payload) > SEND_MAX_REQUEST_BYTES:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return payload


def encode_modern_send(submission: ModernSendSubmission, account: str) -> bytes:
    """Source-informed ordinary school JSON, never OSIN/group/CC/BCC sending."""
    if (
        not isinstance(submission, ModernSendSubmission)
        or type(submission.recipients) is not tuple
        or not 1 <= len(submission.recipients) <= SEND_MAX_RECIPIENTS
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    for value, limit, whitespace in (
        (submission.subject, SEND_MAX_SUBJECT_CHARACTERS, ""),
        (submission.body, SEND_MAX_BODY_CHARACTERS, "\r\n\t"),
    ):
        if (
            type(value) is not str
            or not 1 <= len(value) <= limit
            or not value.strip()
            or any(
                unicodedata.category(c) in {"Cc", "Cs"} and c not in whitespace
                for c in value
            )
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
    seen: set[str] = set()
    recipients = []
    for reference in submission.recipients:
        if (
            not isinstance(reference, ModernRecipientReference)
            or reference.account != account
            or reference.recipient_type != MODERN_SUPPORTED_RECIPIENT_TYPE
            or type(reference.class_label) is not str
            or not reference.class_label.strip()
            or len(reference.class_label) > MODERN_MAX_LABEL
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if (
            any(
                type(v) is not str or re.fullmatch(r"[0-9]{1,64}", v) is None
                for v in (reference.account_id, reference.user_id)
            )
            or reference.account_id in seen
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        seen.add(reference.account_id)
        recipients.append({"accountId": reference.account_id})
    payload = json.dumps(
        {
            "receivers": {"schoolReceivers": recipients},
            "topic": base64.b64encode(submission.subject.encode()).decode("ascii"),
            # The modern reader inserts decoded content as sanitized HTML.
            # Preserve plain-text literals instead of letting tags disappear.
            "content": base64.b64encode(
                escape(submission.body, quote=False).encode()
            ).decode("ascii"),
            "storageId": None,
            "category": "normal",
        },
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    if len(payload) > SEND_MAX_REQUEST_BYTES:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return payload


def message_page_form(folder: MessageFolder, page: int) -> dict[str, str]:
    if (
        not isinstance(folder, MessageFolder)
        or type(page) is not int
        or not 0 <= page < MESSAGE_MAX_PAGE_COUNT
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return {"numer_strony105": str(page), "porcjowanie_pojemnik105": "105"}


def grade_view_form(view: GradeView) -> dict[str, str]:
    """The grade page's view selector; selecting a view changes upstream state."""
    if not isinstance(view, GradeView):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return {GRADE_VIEW_FIELDS[view.value]: "1"}


def attendance_view_form(view: AttendanceView) -> dict[str, str]:
    if not isinstance(view, AttendanceView):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    key, value = ATTENDANCE_VIEW_FORMS[view.value]
    return {key: value}


def agenda_form(year: int, month: int) -> dict[str, str]:
    if (
        type(year) is not int
        or type(month) is not int
        or not (2001 <= year <= 2100 and 1 <= month <= 12)
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return {"rok": str(year), "miesiac": f"{month:02d}"}


def _one_month_after(day: date) -> date:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def homework_form(start: date, end: date) -> dict[str, str]:
    """The upstream form accepts at most one calendar month per selection."""
    if (
        type(start) is not date
        or type(end) is not date
        or start.year > 9998
        or not start <= end <= _one_month_after(start)
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return {
        "dataOd": start.isoformat(),
        "dataDo": end.isoformat(),
        "przedmiot": "-1",
        "status": "-1",
    }


def timetable_form(monday: date) -> dict[str, str]:
    """Central fixed week-selection wire form; no arbitrary date/form input."""
    if type(monday) is not date or monday.weekday() != 0 or monday > date(9999, 12, 25):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    sunday = monday + timedelta(days=6)
    return {TIMETABLE_WEEK_FIELD: f"{monday.isoformat()}_{sunday.isoformat()}"}


def completed_lessons_form(start: date, end: date, page: int) -> dict[str, str]:
    if (
        type(start) is not date
        or type(end) is not date
        or not 0 <= (end - start).days < COMPLETED_LESSONS_MAX_WINDOW_DAYS
        or type(page) is not int
        or not 0 <= page < COMPLETED_LESSONS_MAX_PAGE_COUNT
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return {
        "data1": start.isoformat(),
        "data2": end.isoformat(),
        "filtruj_id_przedmiotu": "-1",
        "numer_strony1001": str(page),
        "porcjowanie_pojemnik1001": "1001",
    }


# Field names each view-selection POST may carry; the transport rejects others.
FORM_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "grades": frozenset(GRADE_VIEW_FIELDS.values()),
        "attendance": frozenset(key for key, _ in ATTENDANCE_VIEW_FORMS.values()),
        "timetable": frozenset({TIMETABLE_WEEK_FIELD}),
        "agenda": frozenset({"rok", "miesiac"}),
        "homework": frozenset({"dataOd", "dataDo", "przedmiot", "status"}),
        "completed_lessons": frozenset(
            {
                "data1",
                "data2",
                "filtruj_id_przedmiotu",
                "numer_strony1001",
                "porcjowanie_pojemnik1001",
            }
        ),
        "messages_received": MESSAGE_PAGE_FIELDS,
        "messages_sent": MESSAGE_PAGE_FIELDS,
        "recipients": RECIPIENT_FORM_FIELDS,
    }
)
FORM_MAX_VALUE_LENGTH = 64


# Source-informed stable type-ID policy, never inferred from names or symbols.
ATTENDANCE_TYPE_KINDS = MappingProxyType(
    {
        "1": "absence",
        "2": "late",
        "3": "excused",
        "4": "exemption",
        "100": "present",
        "1266": "excursion",
        "2022": "contest",
        "2829": "training",
    }
)


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
    """Bounded service-local traffic policy, not Librus-approved quotas.

    Queue limits count waiting requests, separately from active requests. Rate
    tokens count every admitted attempt, including future auth/redirect/retry
    requests. Parent and student logins each occupy their own account slot.
    A shared ten-token burst accommodates sequential cold-login hops; refill at
    five tokens/second bounds sustained traffic without one-second hop delays.
    """

    requests_per_second: PositiveFinite = 5.0
    burst: PositiveCount = 10
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
    download_origin: str = UPSTREAM_ORIGINS["download"]
    messages_origin: str = UPSTREAM_ORIGINS["messages"]
    proxy_url: SecretStr | None = Field(default=None, repr=False)
    ssl_context: ssl.SSLContext | None = Field(default=None, repr=False)

    @field_validator(
        "synergia_origin", "api_origin", "download_origin", "messages_origin"
    )
    @classmethod
    def validate_origin(cls, value: str, info: ValidationInfo) -> str:
        assert info.field_name is not None
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
        expected = urlsplit(
            UPSTREAM_ORIGINS[info.field_name.removesuffix("_origin")]
        ).hostname
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
        return {
            "api": self.api_origin,
            "synergia": self.synergia_origin,
            "download": self.download_origin,
            "messages": self.messages_origin,
        }[endpoint.origin]
