# Public API (0.3.0)

Everything public is exported from `librus_python_api`; exceptions live in
`librus_python_api.exceptions`. Results are frozen dataclasses. Their reprs omit
personal fields. Serializing them for MCP or anything else is the consumer's job.

## Service and accounts

```python
from librus_python_api import AccountCredentials, LibrusService

async with LibrusService(
    {"parent": AccountCredentials(login=..., password=...)}
) as service:
    identity = await service.account("parent").identity()
```

- Construction does no I/O and reads no environment variables. Transports are
  created lazily. A service belongs to one event loop.
- Use one service per process for all accounts, so every call shares one traffic
  budget. Separate processes need their own coordination.
- `AccountCredentials(login, password, expected_owner_id=None,
  expected_student_id=None)`. The optional IDs are checked after login; a
  mismatch, or an identity change inside a session, raises `AccessDeniedError`.
- `aclose()` is idempotent and joins all owned work. Calls after closing raise
  `ClosedError`.
- `service.snapshot()` reports active, queued and dispatched requests.

Every read accepts `budget: RequestBudget | None` and `max_age_seconds: float`
(default `0.0`, at most `3600`).

## Budgets, caching and coalescing

`RequestBudget(max_requests=32, timeout_seconds=120.0, max_response_bytes=4 MiB)`
spans everything an operation does: queue wait, every login hop, redirects,
recovery and every page. One budget may be shared by several calls, for example
one summary across four logins. Requests are counted at dispatch and never
refunded. Exhaustion raises `LimitError`; deadlines raise `OperationTimeoutError`.

- Fresh reads are the default. `max_age_seconds > 0` allows reuse from a
  64-entry per-account result cache. A new login clears it.
- Identical in-flight reads on one account share one request. Calls with
  explicit budgets share only when they pass the same budget object. Cancelling
  one waiter leaves others running; cancelling the last waiter cancels and joins
  the work.
- Window helpers (`grades_window`, `attendance_window`) filter the cached full
  collection and add no requests.

## Configuration

- `SchedulerLimits`: 5 requests/second, burst 10, 2 active requests, 1 per
  account, 32 queued (8 per account), 16 accounts, 32 concurrent operations
  (8 per account). These are engineering defaults, not a published Librus quota.
- `TransportLimits`: 30 s request and 10 s connect timeouts, 4 MiB bodies, 10
  redirects, 128 cookies, 256 KiB parser input, 60 s cooldown (see Errors).
- `OperationLimits`: the budget used when a call passes none.
- `ConnectionSettings`: verified TLS context and explicit proxy only. Origins can
  be overridden only with loopback addresses, for fixture servers.
- `transport_factory`: an `AccountTransport` per login, owned and closed by the
  service. It must honour the scheduler, budgets and destination checks.
- `diagnostic_sink`: receives `DiagnosticEvent(operation, outcome,
  elapsed_seconds, budget_requests_dispatched, budget_response_bytes)`.
  `librus_python_api.diagnostics.loguru_sink` forwards it to Loguru. Sink errors
  never affect results.

All upstream routes and forms are fixed in `config.py` and documented in
[contracts/upstream.openapi.yaml](contracts/upstream.openapi.yaml). There is no
arbitrary-URL method.

## Identity and profile

- `identity()` returns `Identity(owner, student, observation)`. `owner` is the
  login's own person; `student` is the represented student. The login already
  reads it, so the first call costs no extra request.
- `student_information()` returns `StudentInformation` with name, class, register
  number, tutor, school and `lucky_number`. `LuckyNumber.availability` is
  `UNAVAILABLE` when the page has none; no date is invented.

Each result carries an `Observation(account, observed_at, session_generation,
source)` with an aware UTC timestamp.

## Grades

- `final_grades()` returns `FinalGrades` with one `SubjectGradeSummary` per
  subject: `midterm`, `predicted_annual` and `annual`, each a
  `GradeSummaryValue(availability, raw)`. Raw school text is kept as is.
  `UNAVAILABLE` means the column is absent.
- `grades(view=GradeView.ALL)` returns `Grades(identity, records, observation,
  view)`. Selecting a view (`ALL`, `WEEK`, `LAST_LOGIN`) is one POST that changes
  the filter shown in that login's session; it is never replayed. `records` has:
  - `numeric`: `NumericGrade` with subject, raw symbol, civil `day`, semester,
    `kind` (`GradeKind`), and the optional count flag, weight, category, teacher,
    comment and tooltip `metadata`. Unknown weight or count is `None`, not zero.
  - `descriptive`: `DescriptiveGrade`, including publications (`PUBLICATION`).
  - `descriptive_summaries`: undated semester text, never in date windows.
  - `averages`: `SchoolAverage` as school-provided text. Nothing is computed.
- `grades_window(start, end)` filters the `ALL` collection to an inclusive window
  of at most 366 days.

The observation card ("Karta spostrzeżeń") shown on some grades pages is not
read yet.

## Attendance

- `attendance(view=AttendanceView.ALL)` returns `Attendance` with
  `AttendanceRecord`s (symbol, day, semester, type, teacher, period, excursion
  flag, topic, subject, numeric `detail_id`, tooltip metadata) and the semesters
  shown. The view POST is never replayed.
- `attendance_window(start, end)` filters the `ALL` collection (at most 366 days).
- `attendance_detail(detail_id)` takes a numeric string and returns ordered
  `fields` and `notes`.
- `gateway_attendance()` returns the JSON records with a strict `AttendanceKind`
  per stable type ID; unknown IDs stay `UNKNOWN`.
- `attendance_frequency()` returns per-semester and overall `FrequencyMeasure`
  (attended, total, excluded and unknown counts, plus `ratio` in 0..1 or `None`).
  Unknown types or an empty denominator give `ratio=None`, never 100 %.
- `subject_frequency(start=None, end=None)` resolves lessons to subjects through
  a 256-entry, one-hour metadata cache and returns one measure per subject ID.

## Timetable

`timetable(monday)` takes a `date` that is a Monday and returns `Timetable` with
seven `TimetableDay`s. Each `TimetablePeriod` has a number, a local-time
`interval`, its `lessons` (subject and the combined teacher/classroom text),
`changes` and the reported `next_recess`. A `TimetableChange` keeps the notice
label (for example "zastępstwo") and its tooltip fields in order. The tooltip
anchor may wrap the notice or sit inside it. No status is inferred from the
label. The week selection is a POST that is never replayed.

## Announcements

`announcements()` returns `Announcement`s with title, author, raw `date_text`,
typed `published_on`, full plain-text `content` and a `reference`. The page has
no upstream ID, so `reference` is a SHA-256 fingerprint of the content scoped to
the login. It stays stable across reordering and changes when the text changes.
Nothing is marked as read.

## Agenda

- `agenda(year, month)` returns every civil day of the month with its
  `AgendaEvent`s: full `text`, `title`, optional `subject`, `lesson_number` or
  `at_time` when present, the complete tooltip as `metadata_text`, labelled
  `metadata` and unlabelled `metadata_notes`. A multi-line description continues
  the `Opis` field until the next known label.
- `agenda_detail(reference)` takes the `SchoolReference` from an event of the
  same login and returns `SchoolDetail(title, fields, notes)` with labels as
  shown.

## Homework

- `homework(start, end)` accepts an inclusive window of at most one calendar
  month (for example 1 Sep to 1 Oct, or 31 Jan to 28 Feb). Upstream rejects
  longer windows, so the library refuses them before any request. Each
  `HomeworkItem` has `subject`, `teacher`, `topic`, `category`, `assigned_on`,
  `due_on`, the raw `submission_status` (`None` when the school has no such
  column), `marked_done_at` and a `reference`. Columns are mapped by their
  header. Each date is checked against the weekday shown beside it.
- `homework_detail(reference)` returns `SchoolDetail`. The web page pairs
  opening a detail with a separate "mark as read" call; the library never makes
  that call.

## Completed lessons

- `completed_lessons_page(start, end, page=0)` returns one zero-based page with
  `page_count`, typed `CompletedLesson`s and a content `fingerprint`.
- `completed_lessons(start, end, cursor=None, max_pages=4, limit=128)` reads up to
  8 pages and 256 rows and returns a `next_cursor` (or `None` when finished).
  Resume with the cursor, the same login and the same dates. A resumed page must
  match its fingerprint; page-count drift or a repeated page raises `ParseError`.
  Cursors are not snapshots.

Windows span at most 371 days. Where the school has disabled the view, both
calls raise `ViewDisabledError`.

## Errors

All errors subclass `LibrusError`. Each carries a closed `kind` and no upstream
text. `error_for(kind)` builds one.

| Error | Meaning |
| --- | --- |
| `InvalidInputError` | Rejected before any request, or upstream rejected the selection |
| `CredentialsRejectedError` | Login and password refused |
| `AccountActionRequiredError` | CAPTCHA, 2FA or another interactive step is required |
| `SessionExpiredError` | Proven expiry that could not be recovered |
| `AccessDeniedError` | Denied, or an unexpected redirect or identity |
| `ViewDisabledError` | The school administrator disabled this view |
| `UnsupportedCapabilityError` | A recognized but unsupported layout or content |
| `ParseError` | The page or JSON does not match the expected structure |
| `ThrottledError`, `MaintenanceError` | HTTP 429 or 503; the shared scheduler pauses |
| `ConnectionError`, `OperationTimeoutError` | Transport failure or budget deadline |
| `LimitError` | A request, byte, item or queue bound was reached |
| `ClosedError` | The service is closed |

Recovery policy:

- Only a 401, or a redirect to an approved login route, proves expiry.
- Safe GET reads then log in once more and retry once, within the same budget.
- View-selection POSTs are never replayed.
- A denial or unrecovered expiry starts a 60-second cooldown for that operation
  on that login; a failed login starts one for the whole login.
- 429 and 503 pause the whole scheduler, honouring `Retry-After` up to 24 hours.
