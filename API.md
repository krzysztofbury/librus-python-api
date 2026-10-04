# Public API

Core public values are exported from `librus_python_api`; exceptions live in
`librus_python_api.exceptions`. Optional storage is explicitly imported from
`librus_python_api.persistence`. Results are frozen dataclasses. Their reprs omit
personal fields. Serializing them for MCP or anything else is the consumer's job.

## Optional local attachment files

```python
from pathlib import Path
from librus_python_api.files import publish_attachment

stream = client.stream_attachment(attachment.reference, budget=budget)
saved = await publish_attachment(
    stream,
    Path("/caller-selected/existing/directory"),
    filename=attachment.filename,
)
```

The optional file layer publishes complete owner-only files atomically without
overwriting an existing path. It returns the local path, byte size, SHA256 and
content type. It neither selects the destination nor opens message content.
See [the file contract](contracts/attachment-files.md) for filesystem requirements,
bounded naming and cancellation/commit semantics.

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
  Attachment downloads use the operation's remaining deadline rather than the
  ordinary 30 s request/HTML body cap; the connect timeout still applies.
- `OperationLimits`: the budget used when a call passes none.
- `ConnectionSettings`: verified TLS context and explicit proxy only. Origins can
  be overridden only with loopback addresses, for fixture servers.
- `transport_factory`: an `AccountTransport` per login, owned and closed by the
  service. It must honour the scheduler, budgets and destination checks.
  In 0.4.3 custom transports also implement `resolve_attachment` and
  `stream_download`. Download implementations must retain scheduler admission
  through EOF/cleanup, await demand before each chunk, and close before returning.
  In 0.4.4 they also implement `consume_schedule_events`: complete encoded
  payload receipt must initiate/await checkpoint ownership inside the scheduled
   worker before returning to the service, not after scheduler delivery.
  In 0.4.6 implement `send_message(submission, budget, dispatched)`: validate and
  encode the fixed send form before admission, invoke the library-owned synchronous
  `dispatched` callback once immediately before entering the HTTP send, never
  follow/retry, and join cancellation before returning. Missing methods are
  unsupported, never a fallback to the generic `request` method. Custom transports
  must uphold the callback boundary; the library cannot prove what a third-party
   transport actually sends. Generic `request("send_message", ...)` is prohibited.
  Modern support adds `authenticate_modern(expected_login, budget)`,
  `clear_modern_auth()` and `send_modern_message(submission, budget, dispatched)`.
  Use a separate account-owned modern cookie jar and the same shared scheduler;
  validate exact origin/login/target/source before the one handoff dispatch.
  The modern send callback, uncertainty and joined cleanup rules are identical.
  Generic modern launch/handoff/send requests are prohibited.
  `request` additionally accepts optional `query: Mapping[str, str]` for fixed
  allowlisted modern directory and mailbox selections only. Arbitrary query keys,
  routes and modern-to-legacy reference reuse are rejected before dispatch.
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
- `grades_window(start=None, end=None, view=GradeView.ALL)` filters the selected
  collection to inclusive civil dates. Either boundary may be omitted; two
  supplied dates may be at most 370 days apart. `GradeWindow.view` records the
  selection. It reuses only that view's cache; averages and undated summaries
  remain outside the window.

The observation card ("Karta spostrzeżeń") shown on some grades pages is not
read yet.

## Attendance

- `attendance(view=AttendanceView.ALL)` returns `Attendance` with
  `AttendanceRecord`s (symbol, day, semester, type, teacher, period, excursion
  flag, topic, subject, numeric `detail_id`, tooltip metadata) and the semesters
  shown. The view POST is never replayed.
- `attendance_window(start=None, end=None, view=AttendanceView.ALL)` filters the
  selected collection, with the same optional-date/370-day-difference rules.
  `AttendanceWindow.view` records the selection.
- `attendance_detail(detail_id)` takes a numeric string and returns ordered
  `fields`, `notes` and stable-key `normalized_fields` (see below).
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
  same login and returns `SchoolDetail` with a title, raw fields, notes and
  stable-key `normalized_fields`.

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

For longer selections use `homework_range(HomeworkRangeRequest(start, end,
max_windows=13, max_items=4096))`. The immutable request is validated before
login. Dates must be at most 370 days apart. The service plans disjoint inclusive
monthly windows, then fetches them sequentially under one account lock, shared
scheduler and original request/byte/deadline budget. The existing `Homework`
response contains the requested range and merged items. Equal reference-bearing
rows are deduplicated; conflicting versions fail with `ParseError`. Reference-free
rows remain separate. Aggregate text is capped at 262144 characters. Any failure
discards the aggregate without caching partial results. This helper preserves
upstream date-selection semantics and does not promise a transactional snapshot.

### Stable detail keys

School and attendance details expose ordered `DetailField(key, raw_label, value)`
records in `normalized_fields`. `key` uses a known family-specific English name
or `None` for unknown labels. Values remain full displayed strings, including
empty values; dates/numbers in detail text are not silently converted. Raw fields
and ancillary notes remain available. Ambiguous canonical labels fail before
caching. See [the key mapping and evidence](contracts/detail-fields.md).

## Completed lessons

- `completed_lessons_page(start, end, page=0)` returns one zero-based page with
  `page_count`, typed `CompletedLesson`s and a content `fingerprint`.
- `completed_lessons(start, end, cursor=None, max_pages=4, limit=128)` reads up to
  8 pages and 256 rows and returns a `next_cursor` (or `None` when finished).
  Resume with the cursor, the same login and the same dates. A resumed page must
  match its fingerprint; page-count drift or a repeated page raises `StaleCursorError`.
  Cursors are not snapshots.

Windows span at most 371 days. Where the school has disabled the view, both
calls raise `ViewDisabledError`.

## Message lists

`MessageFolder.RECEIVED` (default) and `MessageFolder.SENT` are distinct selections.
Pass the enum, not a string.

- `messages_page(folder=MessageFolder.RECEIVED, page=0)` returns `MessagesPage`
  with `identity`, `folder`, zero-based `page`, `page_count`, `items`, a page
  `fingerprint` and `observation`. Exactly one fixed pagination POST after login;
  no separate page-count request. Page indices are 0..999; at most 50 rows/page.
- `messages(folder=MessageFolder.RECEIVED, cursor=None, max_pages=4, limit=128)`
  returns `Messages` with `items`, `pages_fetched`, `duplicates_skipped`,
  `next_cursor`, `truncation_reason` and provenance. Limits are 1..8 pages and
  1..256 unique rows per call. A complete batch has no cursor/reason; bounded
  continuation records `item_limit` or `page_limit`. Errors on any later page
  discard the batch, never return an apparently complete partial list.
- Resume with the same account alias and folder. `MessagesCursor` also carries
  the page, offset, page count, fingerprint and up to 2,000 already returned IDs.
  Duplicate IDs across pages are skipped, not across accounts or folders.
  Duplicate IDs within one page fail. Changed mid-page content, changed page
   counts, repeated pages and pages containing only seen IDs fail with
   `StaleCursorError` (`kind=stale_cursor`). Malformed/clamped page metadata remains
   `ParseError`. History capacity exhaustion is `LimitError`. A cursor is not a
  mailbox snapshot: page-boundary changes with unchanged counts can still move
  records. Restart explicitly when drift is detected. It is not an authorization
  token and is not designed as a durable notification checkpoint.

Each `MessageSummary` carries:

- An inert `MessageReference(folder, identifier, account)`, extracted from
  matching numeric row links. No arbitrary URL is exposed or followed.
- `correspondent` (sender for received, addressee for sent), `subject`,
  `timestamp`, `has_attachment`, and `unread` for received mail. Sent `unread` is
  `None`, not a guess from recipient status. `recipient_read_status` keeps the
  sent column's text; received mail has `None`.
- `MessageTimestamp(local, raw, timezone="Europe/Warsaw")` keeps school civil
  time and the normalized displayed timestamp. `local` is intentionally naive:
  the page supplies no UTC offset or DST fold. Do not infer a UTC instant.

Each text field is bounded to 4,096 characters, total page text to 256 KiB,
in addition to shared body/parser/request limits. No body or attachment fetch,
mark-read, delete, send or read-once operation occurs. Pagination changes the
selected mailbox view, so its POST is never replayed, including after expiry.
Page and batch caches are separate and fresh by default.

In 0.4.11 a full 50-row page without pagination metadata is unsupported, not
apparently complete. Empty and shorter pager-less page-zero layouts remain supported.

Live scope, apix coverage and remaining gates: [contracts/messages.md](contracts/messages.md).

## Modern messaging (explicit backend, partial live qualification)

0.4.11 revalidates bound modern identity with one fresh GET before each send.
The initial handoff already includes that GET; subsequent sends cost one GET plus
one POST. Expiry before dispatch raises `SessionExpiredError` and leaves
NOT_DISPATCHED. An exact launch-to-native-login redirect is expiry, not denial.
Messages-origin failures clear only modern binding/cookies/cache; valid legacy
sessions stay usable. A later explicit modern call can rebind, but no modern
read/send is automatically retried. A race after preflight can still yield UNKNOWN.

- `modern_identity(*, budget=None, max_age_seconds=0)` returns `ModernIdentity`:
  native `identity`, modern `account` metadata and an `observation`. Modern owner
  ID and available names must match the native owner. Only ordinary school roles
  are enabled, conservatively; unrelated origins and OSIN remain unsupported.
  Modern identity `accountId` accepts a decimal string or a non-negative JSON
  integer of at most 64 digits, normalized to a string before owner comparison.
  Booleans, floats, negatives and larger integers are rejected. This does not
  change recipient-ID validation or allow cross-backend ID substitution.
- `modern_recipient_types(*, budget=None, max_age_seconds=0)` returns
  `ModernRecipientTypes`. Each item has a backend/account-bound `reference`,
  a `label` and `lookup_supported`. Unsupported types are metadata, not permission
  to look up another route.
- `modern_recipients(recipient_type, *, budget=None, max_age_seconds=0)` returns
  `ModernRecipients`. Allowlisted class and ordinary school-employee branches
  are supported; availability and live coverage are account-specific. Each item preserves
  `label` and `ModernRecipientReference(account_id, user_id, account,
  recipient_type, class_label, include_virtual=False)`. Duplicate account IDs/classes and unrecognized
  layouts raise errors; IDs must never be substituted or passed to legacy APIs.
- `prepare_modern_send(*, recipients: tuple[ModernRecipientReference, ...],
  subject: str, body: str) -> SendAttempt` is local, immutable and single-use.
  It does not perform recipient lookup. Caller-owned preview/confirmation must
  bind the exact backend, sender, recipient(s) and input text before execution.
  `attempt.submission` is `ModernSendSubmission` rather than `SendSubmission`;
  `attempt.outcome.backend` is `MessagingBackend.MODERN`. Legacy outcomes default
  to `MessagingBackend.LEGACY` without changing legacy wire behavior.

Modern authentication uses one exact native launch and modern token handoff,
then verifies `/api/me`, all under the same request/byte/deadline budgets.
Its cookies are isolated from legacy cookies even for the same login. Fresh
identity reads re-check modern metadata; other calls reuse only that login's
already-verified session. Expiry invalidates authentication, never replays a send.
Reads are also non-retryable in this initial scope.

The send JSON carries `receivers.schoolReceivers[].accountId`, Base64 UTF-8
`topic` and HTML-escaped plain-text `content`, `storageId=null`, `category="normal"`.
HTML escaping preserves literal markup in the modern reader; input line endings
are retained in the encoded payload and displayed as line breaks. The existing
50-recipient/200-subject/15,000-body-character and 64 KiB encoded-request policy
limits apply after escaping/Base64 expansion. No attachments, CC/BCC, groups,
drafts, signatures or settings changes are supported.

Modern ACCEPTED requires HTTP 201, `application/json`, and exactly
`{"data":{"messageId":<positive integer>,"status":"sent"}}`. The ID must be an
actual JSON integer of at most 64 decimal digits, not a bool, float or string.
This establishes upstream acceptance, not recipient reading. Other 2xx responses
remain UNKNOWN; HTTP success alone is insufficient. An explicit allowlisted validation denial on HTTP 400/422
can establish source-informed REJECTED. Unknown, malformed, contradictory or
failed responses remain UNKNOWN after potential dispatch, with no retries,
redirects, fallback, post-send lookup or implicit reauthentication. Cancel/shutdown
propagate normally with an inspectable outcome after joined cleanup, as below.
Modern list/content reads do not reconcile durable UNKNOWN send history.

- `modern_messages_page(folder=RECEIVED, *, page=1, page_size=10, budget=None,
  max_age_seconds=0)` returns `ModernMessagesPage`. Pages are one-based. This GET
  returns summaries only; sent read status can be unknown.
- `modern_messages(folder=RECEIVED, *, cursor=None, page_size=50, max_pages=4,
  limit=128, budget=None, max_age_seconds=0)` returns `ModernMessages` with explicit
  truncation, duplicate counts and account/folder/page-size-bound continuation.
  Cursor drift and later-page errors never return partial output.
  Page size is 1-50, page number 1-1,000, `max_pages` 1-8, `limit` 1-256 and
  cursor history at most 2,000 IDs. These are library bounds, not upstream maxima.
- `modern_message_content(reference, *, allow_mark_read=False, budget=None,
  max_age_seconds=0)` requires a `ModernMessageReference`. Received opens require
  consent and invalidate inbox summary caches before dispatch. Results have inert
  rendered `text` and `ModernMessageAttachment` metadata. Optional inert original
  subject/body, archive/withdrawal flags and bounded sent `recipient_receipts`
  preserve observed layouts. `read` is true/false/unknown, `read_at` is optional,
  and `delivered` stays unknown. Aggregate `recipient_count`/`read_count` are not
  a claim that visible roster leaves are exhaustive. Modern metadata cannot be used with legacy
  `stream_attachment`.
  Base64 bodies must decode to UTF-8; XML BOM/preambles retain strict wrapper
  validation. Conflicting encoding declarations, DTDs and entities are rejected.
- `stream_modern_attachment(reference, *, max_bytes=50 * 1024 * 1024, budget=None)`
  returns `ModernAttachmentStream`, a single-owner uncached async context manager
  and iterator. It resolves only explicit modern/archived references, validates
  the exact official sandbox destination, and shares the existing bounded
  credential-free byte worker. It never opens content, follows redirects or
  retries. Use the optional `files.publish_attachment` with an explicit directory
  for durable, atomic, non-overwriting local saves. Its metadata reference is
  backend-specific; `AttachmentMetadata.reference` can now be legacy or modern.

Recipient type references accept `include_virtual=False`. Set it explicitly only
for `students` or combined `parents,guardians`; virtual expansion is not automatic.
Employee leaves have an empty `class_label` and optional inert
`availability_status_json`, not interpreted as send permission.
See [the communication contract](contracts/modern-communication.md) for limits,
strict supported shapes and remaining layout/availability qualification gates.

See [the modern contract](contracts/modern-messages.md) for evidence and live gates.

## Legacy sending (0.4.6, offline-qualified only)

`prepare_send(*, recipients: tuple[RecipientReference, ...], subject: str,
body: str)` returns a `SendAttempt` without network access. It validates same-login
recipient/type/selection references, unique recipient IDs, 1-50 recipients,
1-200 subject characters, 1-15,000 body characters and a 64 KiB complete encoded
form limit. Blank fields, invalid Unicode and unsupported control characters
fail before I/O. Body TAB/CR/LF are preserved; subject controls are not accepted.
Text, line endings and recipient order are never silently changed or truncated.

`attempt.submission` is an immutable `SendSubmission(recipients, subject, body)`;
its repr omits content. `attempt.used` becomes true when execution first starts,
before any await. `await attempt.execute(budget=...)` consumes it even on
pre-dispatch failure. Concurrent/repeated execution raises `InvalidInputError`
without mutating the original outcome or dispatching again. No caching,
coalescing, redirects, automatic retry, recipient lookup or send-time fallback.
Normal bounded initial authentication is possible; expiry after the send never
reauthenticates and replays the write.

`attempt.outcome` is an immutable `SendResult(status, reason, identity,
observation)` snapshot. Initially `status=SendStatus.NOT_DISPATCHED`. The
snapshot remains provisional while execution is running: seeing NOT_DISPATCHED
then is not permission to start another attempt. Await completion or joined
cancellation before reconciliation. `used` means consumed, not completed. The
dedicated scheduled HTTP boundary changes it to UNKNOWN; only a recognized
acknowledgement changes it to ACCEPTED or REJECTED. Acceptance means upstream
acceptance, not delivery or reading. HTTP status, redirects or sent-folder
similarity alone cannot establish success. Form/acknowledgement shapes are
source-informed, with original offline fixtures, not live-compatible claims.

Pre-dispatch errors raise existing typed errors and retain NOT_DISPATCHED.
Ordinary failures after the boundary return UNKNOWN with a closed `ErrorKind`
reason, never raw exceptions/responses. Cancellation propagates
`asyncio.CancelledError` after joined cleanup; inspect `attempt.outcome` afterwards.
Its reason is `"cancelled"` unless a terminal acknowledgement was already
established. Shutdown preserves these cancellation semantics for the send path.
In 0.4.11 completed bounded send responses survive return-time budget expiry.
Receipt parsing has a separate local deadline of
`TransportLimits.request_timeout_seconds` and the same bounded parser/admission
policy. No further HTTP or retry is granted. Incomplete responses and local
parsing timeout remain UNKNOWN; external cancellation still propagates.
Sender identity/observation are bound at the potential-dispatch boundary, not
invented for failures before it. Sent page/batch caches are invalidated there,
including uncertain sends; unrelated received summaries remain cached unless
session invalidation requires a full clear. Diagnostic `ok` means classified
completion, not necessarily ACCEPTED; inspect the typed result.

Attempts are process-local, not confirmation tokens, a durable outbox or
upstream idempotency. Constructing another attempt can duplicate delivery; no
automatic retry of UNKNOWN or cancelled attempts is safe. The optional persistence
workflow below adds durable confirmation/claim safeguards. Applications still own
human approval and any manual reconciliation.
References are structural values, not proof of consent or intended identity.
No attachment upload, reply, forward or scheduled-send API is introduced.

No live send is authorized by installation or this API. Qualification remains
separately gated to the one privately specified recipient, one approved message
and at most one dispatch, after exact sender/recipient/payload verification and
fresh bounded discovery approval. No additional/group/substitute recipient or
fallback is allowed. See [the send contract](contracts/sending.md).

## Optional durable sending

### 0.4.11 format and explicit retention

Storage schema version 2 uses a random salt created once per database. Persisted
context identifiers are store-local HMAC-SHA256 pseudonyms, not the public
`client.context.identifier` hash. `store.context_identifier(client.context.identifier)`
returns that pseudonym only on an open store. Core clients remain storage-independent.
Version-1 stores reject without modification; no automatic migration/reset.

`await store.prune_send_history(context=client.context, identifiers=(...),
allow_accepted=False)` returns the number of deleted rows. Use identifiers from
`send_history`. The entire selection validates before deletion: foreign/missing
IDs, live pending confirmations, CLAIMED and UNKNOWN rows reject. Expired pending,
INVALIDATED, NOT_DISPATCHED and REJECTED rows are eligible. ACCEPTED rows require
explicit `allow_accepted=True`, which removes protection against a new confirmation
for an identical submission. No implicit expiry of consumed history or HTTP calls.

Explicitly import `PersistenceStore`, `PersistenceLimits`, `SendConfirmation`,
`DurableSendOutcome`, `DurableSendPhase` and `DurableSendRecord` from
`librus_python_api.persistence`.
Core clients work without storage. No import, constructor, login or prepare call
creates state, reads old MCP files or starts background recovery.

- `PersistenceStore(directory: Path, *, limits=None)` selects an absolute private
  directory whose parent already exists. `async with` opens/closes it; `open()`
  and idempotent `aclose()` are also available. One store belongs to one event loop.
  Use the same directory across cooperating processes for coordinated claims.
  Select a trusted local filesystem with working SQLite locks/fsync. No network
  filesystem, encrypted-at-rest, or hostile same-user filesystem isolation claim.
- `client.context` and `attempt.account_context` expose a frozen `AccountContext`
  binding the configured alias, login and native/API/modern origins, not a shared
  student identity. Password rotation preserves this context; login/origin/alias
  changes do not. Identifiers are hashes, not anonymization or authority tokens.
- `await store.preview_send(attempt)` performs no HTTP and returns an expiring
  `SendConfirmation(token, expires_at)`. Only a token hash and exact context/backend/
  complete immutable-submission digest are persisted. Message bodies, recipient
  labels, token plaintext, credentials and cookies are never stored. The caller
  must preserve approved input and obtain human consent before execution.
- `await store.execute_send(token, attempt, budget=None)` accepts the original or
  an identically prepared unused native attempt, including after restart. It
  commits the single-use claim before any authentication/send. Mismatch, expiry
  or backwards time invalidates the unused token; replay rejects without HTTP.
  A claimed/unknown/accepted identical submission also blocks another preview
  or an already-issued duplicate token in this same store. Distinct contexts and
  backends remain independent; the store never dispatches a fallback.
- Execution returns the native `SendResult`. Cancellation and shutdown join owned
  network/storage work. A final-save failure raises a closed typed storage/limit
  error; inspect the native attempt but treat the durable claim as uncertain.
  `await store.send_outcome(token, context=client.context)` returns a typed phase,
  `SendStatus | None`, and `requires_reconciliation`. CLAIMED always means UNKNOWN,
  including a process lost before dispatch; it is never permission to replay.
  `await store.send_history(context=client.context)` returns bounded immutable
  records with opaque token-hash identifiers, payload digests, UTC creation/expiry
  and outcomes, ordered by creation then identifier. It works without plaintext
  tokens and neither clears uncertainty nor authorizes another send.
- SQLite FULL synchronous transactions serialize cross-process claims. Unknown
  schema, extra triggers, corrupt data, replaced files, symlinks, non-regular
  files and unsafe POSIX permissions fail closed, never reset/migrate state.
  No automatic retry, reconciliation, deletion of consumed history or polling.
- Defaults: 8 admitted storage workers and 8 send workflows, 256 total records,
  32 unused previews, 300-second expiry and 0.1-second SQLite busy timeout.
  Configured maxima: 64 each, 4,096 records, 256 previews, 300 seconds and 5 seconds.
  Storage workers are serialized per store; full queues/contention fail immediately
  or after the bounded busy interval. The final outcome save after a claim waits
  up to `final_busy_timeout_seconds` (default 5, maximum 60); if it still fails,
  `execute_send` raises STORAGE and the claim stays uncertain. LIMIT is only raised
  before upstream work. The database is capped at 8 MiB. Expired
  unused previews may be reclaimed; consumed history is not silently evicted.

These are local conservative safeguards, not upstream idempotency or exactly-once
delivery. Direct `attempt.execute()` and other stores do not participate in this
store's duplicate protection. Applications must route the protected workflow
consistently. MCP integration belongs in its separate repository at backend
migration time.
See [contracts/persistence.md](contracts/persistence.md).

## Optional durable notifications

In 0.4.11, notification schema and neutral archive versions are 2. Export payloads
carry the source salt and store-local identifiers, not the public context hash.
Empty-target import validates the source namespace and rebinds to the target salt;
receipts/events/progress remain unchanged, but export bytes differ across stores.
Old version-1 archives explicitly reject. See the storage format decision in
[contracts/persistence.md](contracts/persistence.md).

`await store.prune_seen(context=client.context, category=NotificationCategory.GRADES,
identifiers=(...))` explicitly forgets the selected seen IDs and returns the deleted
count. It requires no uncertain reservation or pending delivery in that context.
Raw checkpoint bytes/cursor stay intact, allowing saturated history to shrink and
replay without another read-once request. Foreign/missing/duplicate/invalid IDs
reject atomically.
Agenda IDs proving the acknowledged raw prefix cannot be pruned until it drains.
Other categories and initialization/last receipt stay intact. Forgotten IDs can be
notified again; no automatic school-year/age expiry is performed.

Explicitly import `NotificationStore`, `NotificationLimits`, `NotificationWorkflow`,
`NotificationBatch`, `NotificationItem`, `NotificationState`, `NotificationSeen`,
`NotificationArchive` and `canonical_notification_id` from
`librus_python_api.persistence`. Construction is inert; core clients remain
independent of this optional layer.

```python
from pathlib import Path
from librus_python_api import NotificationCategory
from librus_python_api.persistence import NotificationStore, NotificationWorkflow

# Inside the application's existing LibrusService scope. Parent directory exists.
async with NotificationStore(Path("/absolute/private/notification-state")) as store:
    workflow = NotificationWorkflow(service.account("parent"), store)
    batch = await workflow.poll(categories=(NotificationCategory.MESSAGES,))
    await application_deliver(batch)  # application-owned delivery boundary
    await workflow.acknowledge(batch.receipt)
```

- `NotificationStore(directory: Path, *, limits=None)` opens the private separate
  `notifications.sqlite3` via `async with` or explicit `open()`/`aclose()`.
  Existing send databases remain unchanged. Select a trusted local filesystem
  with SQLite/fsync/POSIX flock support; other platforms fail explicitly on
  context operations. One store belongs to one event loop. Shutdown/cancellation
  joins owned work. Same-context competition fails with LIMIT, without HTTP.
- `NotificationWorkflow(client, store).poll(*, categories, allow_consume_events=False,
  homework_window=None, checkpoint_timeout_seconds=5.0, budget=None)` accepts a
  nonempty tuple of distinct native categories. Ordinary reads precede schedule
  consumption. Homework defaults to today minus seven days through today in
  Europe/Warsaw. Grades/attendance use LAST_LOGIN, messages use received page zero,
  announcements use the ordinary collection. No menu counts, message content,
  detail calls, modern fallback or arbitrary historical catch-up is performed.
- New `AGENDA` consumption requires explicit `allow_consume_events=True` each
  time. Complete encoded raw bytes and original metadata commit before parsing.
  Existing raw checkpoints replay locally before another consume. Malformed raw
  data remains stored and blocks another consume, even with fresh consent.
- `NotificationBatch(receipt, context, first_run, categories, items,
  has_more_schedule)` is a durably staged batch. Each `NotificationItem` carries
  category, canonical identifier, native typed value, identity and observation.
  First run diffs against empty IDs and ends only at acknowledgement. Requested
  categories alone update seen state. Until acknowledgement, polling the exact
  same category tuple returns that batch without authentication/HTTP. A different
  tuple fails explicitly, not silently discarding the prior delivery.
- `await workflow.acknowledge(receipt)` (or
  `await store.acknowledge(receipt, context=client.context)`) atomically saves seen
  IDs, advances the schedule cursor and cleans completed raw/delivery rows.
  Repeating the most recently committed receipt is idempotent; older or foreign
  receipts reject. Even an empty batch needs acknowledgement. Application delivery
  then process loss before acknowledgement can duplicate delivery: at-least-once,
  not exactly-once. Acknowledging before actual application delivery risks loss.
- `await store.state(context=client.context)` returns immutable initialized/seen
  state without HTTP. Pending batches do not mark IDs seen. Defaults are bounded:
  16 contexts, 8 workers/workflows, 32 raw/reservation records, 16 MiB checkpoint
  bytes, 4 MiB total seen-state bytes, 4,096 IDs/category, 500 items/1 MiB per batch,
  500 events/128 KiB value JSON per replay slice, 0.1 s busy timeout, and 5 s
  `final_busy_timeout_seconds` for checkpoint, staging and acknowledgement saves
  that follow upstream work, since all contexts share one write lock. The full
  envelope is capped at 4 MiB encoded body plus 4 MiB metadata; database main file
  at 64 MiB and global staged delivery/candidate state at 16 MiB. Bounds fail closed
  without silently evicting history. A retained raw envelope can be recovered with
  explicit supported larger limits; oversized single events are never skipped.
- `await store.export_archive(context=...)` returns a version-1 neutral archive
  containing exact context, seen IDs, receipt, raw bytes/progress, pending delivery
  and uncertainty. `await store.import_archive(archive)` is empty-target-only and
  validates the complete import transaction before commit. Unknown versions,
  foreign contexts, malformed raw/progress and inconsistent staged events reject.
  Protect private archive bytes: they are not encrypted/authenticated and are not
  MCP JSON/spool formats. No auto migration, production-file discovery or overwrite.
- `await store.resolve_uncertain_consume(context=...,
  accept_possible_loss=True)` explicitly clears only a reservation without raw
  or pending delivery. Such a marker remains after any failure before checkpoint,
  including possible pre-dispatch failure; it never expires or authorizes retry.
  Clearing it accepts possible lost upstream events, not proof of no consumption.

`canonical_notification_id(category, value)` exposes version-1 native identities.
Schedule hashes cover date_added/type/data; stable native IDs identify ordinary
records where available, otherwise complete visible typed content. Stable-ID
updates do not automatically re-notify. MCP `schedule`/legacy IDs need a separately
qualified explicit mapping to `agenda`/native IDs. See
[contracts/persistence.md](contracts/persistence.md) for compatibility and loss
windows. No live qualification or MCP migration is implied by offline recovery.

## Message content

`message_content(reference, *, allow_mark_read=False)` returns
`MessageContent(identity, content, may_mark_read, observation)`. `reference` must
be a `MessageReference` for the same login with a numeric ID and typed folder.
Foreign accounts, arbitrary URLs and injected IDs fail before authentication.

- Received opens require `allow_mark_read=True`, even for an already-read
  selection or warm cache. Opening may mark read before any response or parse
  failure. Consent does not assert that upstream actually changed a read flag.
- `may_mark_read` describes the route, not delivery or mutation confirmation.
  Sent opens do not require the opt-in. Neither folder is automatically replayed,
  including after proven expiry or a stale keepalive disconnect.
- `content` is `MessageContentData(reference, correspondent, subject, timestamp,
  read_timestamp, text, attachments, recipient_receipts)`. School timestamps use the same raw/civil
  time policy as lists. `read_timestamp` retains the optional displayed
  `Przeczytano` value; it is not inbox unread or per-recipient status.
- Sent content may omit an `Adresat` field: `correspondent=None` then preserves
  absence rather than inventing a name from another table. `recipient_receipts`
  holds ordered `MessageRecipientReceipt(recipient, raw_status, read_timestamp)`
  records when a separate individual receipt table is displayed. Equal labels
  survive; no recipient IDs or aggregate read time are invented. `NIE` has no
  read timestamp; displayed dates retain school civil time. Unknown statuses fail.
  At most 256 receipt rows, 4,096 characters per field and 128 KiB total receipt
  text are accepted. An absent table means no reported receipts, not zero recipients.
- `text` is full plain text with supported block/`br` boundaries and normalized
  whitespace, at most 65,536 characters. No HTML, scripts or external resources
  are returned or fetched. Active body content is unsupported, not executed.
- `attachments` contains up to 20 inert `MessageAttachment(reference, filename)`
  entries. Each `MessageAttachmentReference(message, identifier)` binds a numeric
  file ID to the full account/folder/message reference. Duplicate names survive;
  duplicate file IDs, foreign message IDs and unrecognized marked download
  handlers fail. The displayed filename is untrusted text, never a local path.
   No file bytes, signed URL, MIME type or size are guessed. The separate 0.4.3
   stream accepts these references; one populated metadata layout is now observed.
- Identical opens share the existing account/budget/cache boundary. Fresh
  received opens invalidate cached received pages and batches before dispatch,
  including failures, so potentially stale unread flags cannot be reused. Warm
  content reuse dispatches no request and does not mutate the mailbox.

Unknown metadata/body layouts and bounds fail the whole operation. Full HTML
   fidelity, populated sent content, receipt variants, other attachment handlers and
other/new mailbox layouts remain live qualification gaps.

## Attachment streams

0.4.11 adds `TransportLimits.attachment_idle_timeout_seconds` (default 15 seconds)
for every paused consumer-demand wait, independently of a long operation budget.
Idle expiry reports TIMEOUT, leaves `complete=False`, joins/closes the download
and frees shared admission. Network reads use their separate transport deadlines.
Unsupported signed redirect route/key shapes report UNSUPPORTED_CAPABILITY without
permission cooldown. Foreign origin/scheme/userinfo and HTTP 403 remain denied;
neither error permits download dispatch or replay.

`stream_attachment(reference, *, max_bytes=50*1024*1024, budget=None)` constructs
an `AttachmentStream` without I/O. Use it as an async context manager:

```python
budget = RequestBudget(
    max_requests=24, timeout_seconds=120, max_response_bytes=12 * 1024 * 1024
)
async with client.stream_attachment(
    attachment.reference, budget=budget, max_bytes=10 * 1024 * 1024
) as stream:
    async for chunk in stream:
        await caller_owned_sink.write(chunk)
    assert stream.complete  # Publish only after clean EOF and joined cleanup.
```

- Only account/folder/message/file-bound `MessageAttachmentReference` values are
  accepted. No arbitrary URL, automatic content open or consent bypass exists.
- Exactly two fresh HTTP dispatches after authentication: authenticated redirect
  resolution and a separate credential-free download. Neither hop retries,
  follows redirects or resumes partial output. There is no cache/coalescing.
- Official verified HTTPS sandbox destinations use a bounded, unreserved signed
  key and exact route grammar. Userinfo, query, fragment, percent encoding,
  traversal and alternate destinations fail closed. Loopback origins can be
  explicitly configured for fixtures, independently of authenticated origins.
- `metadata` is immutable `AttachmentMetadata(identity, reference, headers,
  observation)`. `AttachmentHeaders` exposes optional `content_type`,
  `content_length` and raw `content_disposition`; these are untrusted server
  hints, not filenames or MIME detection. Signed URLs and credentials are absent.
- Chunks are at most 64 KiB. Actual bytes count against the file cap and shared
  cumulative budget before delivery. Default service byte budgets remain 4 MiB
  including authentication/source bodies; larger files need an explicit budget.
  The file cap must be 1 byte through 50 MiB. Unknown Content-Length is supported.
- Only identity content coding and ordinary chunked framing are supported.
  Unsupported or ambiguous encodings, oversized/truncated bodies and transport
  errors raise typed, redacted failures, never successful partial EOF.
- One task consumes a non-reentrant stream. The account lock, service operation
  slot and shared scheduler admission stay occupied during streaming and pauses.
  The whole-operation deadline includes queues and consumer backpressure and
  independently closes paused streams. Other accounts still use shared limits.
- `complete` is true only after clean EOF and joined transport work. Context
  exit, idempotent `aclose()`, cancellation or service shutdown close/join work.
  Early breaks leave it false. An async iterator used without its context is
  invalid. The library never writes, names, saves or atomically publishes files.

Evidence, source-informed restrictions and remaining gaps:
[contracts/attachments.md](contracts/attachments.md).

## Recipient discovery

- `recipient_groups()` returns `RecipientGroups(identity, groups, observation)`.
  Each `RecipientGroup` has an account-bound `reference`, displayed `label`,
  upstream `available` flag and library `lookup_supported` flag. Group identifiers are named
  tokens, not numeric IDs. A fresh call makes one selection-view GET.
- `recipients(group: RecipientGroupReference)` returns
  `Recipients(identity, group, items, observation)` through one fixed POST.
  References must belong to the same account alias; arbitrary URLs, token
  injection and foreign references fail before I/O. `RecipientGroupReference`
  includes a `selection_id` defaulting to `"0"`. The root `grupa` reference is
  not a direct lookup and raises `UnsupportedCapabilityError` before I/O.
  `recipient_group_choices(root)` returns `RecipientGroupChoices(identity, group,
  items, observation)` with `RecipientGroupChoice(reference, label, available)`
  records from nonzero `idGrupy` options. Pass a choice reference to `recipients`.
  Nonzero selections are permitted only for `grupa`, use the exact fixed form,
  and remain source-informed/offline-qualified until populated live evidence.
  Virtual classes stay disabled; no recursive hierarchy or group-zero membership
  is guessed. An empty option list means no selectable groups, not no recipients.
  A disabled group's metadata does not
  grant permission; callers should not select it and upstream denial stays typed.
- Each `Recipient` preserves a plain-text `label` and a numeric
  `RecipientReference(identifier, account, group_type, selection_id)`. Equal display names with
  different IDs remain different records. No dictionary keyed by a person's
  name or cross-account deduplication occurs. IDs must match the label's checkbox
  target/value; a missing label or duplicate ID is a parse failure. The one
  independently observed anonymous `sadmin` control-pair layout returns a numeric
  reference with `label=None`, never an invented name or an empty list. This does
  not authorize sending to an unidentified target.
- The class-unavailable notice raises `UnsupportedCapabilityError`; it is not an
  explicit empty-recipient result. Unknown notices and contradictory empty/prompt
  layouts fail rather than silently returning only the recognizable rows.

Limits: 32 group selectors, 2,048 recipients, 1,024 characters per label and
128 KiB total recipient text, plus shared transport/parser/body limits. Each
lookup has its own account/type/selection cache key and accepts the common budget and
freshness parameters. Fresh reads are default. Both selection operations are
never replayed, even though group discovery uses GET. No send route, message
   content, mark-read, attachment or read-once access occurs in recipient discovery.

The empty group-option selector is observed. Populated choices, nonzero dispatch,
virtual-class selection and explicit empty-recipient success remain live-unqualified;
an unknown/empty response is never silently accepted as a recipient list.
Evidence and apix differences: [contracts/recipients.md](contracts/recipients.md).

## Notification and checkpoint primitives

`notification_counts()` returns `NotificationCounts(identity, items, observation)`
with ordered `NotificationCount(category, label, count)` records. Categories are
grades, attendance, messages, announcements, agenda and homework. A shown category
without a counter has zero; missing categories are not fabricated. Invalid or
duplicate counters fail. The menu may be a token-scoped snapshot, not a fresh poll
or the input for seen-state updates. This ordinary read accepts the common
budget/freshness arguments and conservatively does not replay on expiry.

```python
batch = await client.consume_schedule_events(
    allow_consume_events=True,
    checkpoint=consumer_owned_durable_checkpoint,
    checkpoint_timeout_seconds=5,
    budget=budget,
)
```

- Consent defaults to false; the awaitable checkpoint callback is mandatory.
  A simultaneous consume on the same login is rejected. There is no cache,
  coalescing, automatic retry, filtering, enrichment or pagination.
- Before content decoding or parsing, the complete accepted HTTP payload is
  handed to the callback as `ScheduleEventResponse(version=1, identity, wire,
  observation)`. `ScheduleEventWire` holds immutable payload bytes with transfer
  framing removed, optional Content-Type, and content/transfer coding tuples.
  It has no URL, cookie jar, arbitrary headers or filesystem path. Private fields
  are excluded from reprs; the callback must protect the response as private data.
- Callback success acknowledges durable storage. Exceptions, invalid awaitable
  returns and checkpoint timeouts raise redacted `CheckpointError`; acknowledgement
  is unknown and may already have committed. No callback or upstream retry occurs.
- Receipt establishes owned checkpoint work before scheduler delivery. After full
  receipt, caller cancellation, repeated cancellation, operation deadline and
  service close wait for the one checkpoint attempt to finish. Its separate
  interval is positive and at most 30 seconds, default 5. Callbacks must cooperate
  with cancellation and join owned I/O. If they block or suppress cancellation,
  ownership remains held until termination, without a hard wall-clock guarantee.
  Callback re-entry into its own service, including close, fails explicitly.
- `ScheduleEvents(identity, items, observation)` preserves the complete ordered
  batch of `RecentScheduleEvent(date_added, type, data)`. Date/type remain strings;
  data is bounded normalized multiline plain text. No invented ID/hash/UTC offset
  exists. Duplicates survive. Limits: 1,024 events, 1,024 characters per metadata
  field, 65,536 per data field, 262,144 total text and shared parser/body budgets.
- `await client.decode_schedule_events(persisted_response, budget=...)` performs
  only bounded local decoding/parsing, no login or HTTP. It retains original
  identity/observation and validates account alias and envelope version. The
  consumer supplies serialization, recovery policy and trusted provenance.

MCP retains category selection, first-run policy, seen IDs, hashes, locking,
spooling, migrations and bounded replay. Drain persisted responses before a new
consume. Loss remains possible after upstream consumption but before complete
accepted receipt or acknowledged handoff, including crashes, connection failure
and wire-limit rejection. There is no exactly-once guarantee. Read-once layouts
are offline-qualified only and excluded from routine live checks.

Full boundary and provenance: [contracts/notifications.md](contracts/notifications.md).

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
| `StaleCursorError` | A previously valid continuation no longer matches the current sequence; restart explicitly |
| `ThrottledError`, `MaintenanceError` | HTTP 429 or 503; the shared scheduler pauses |
| `ConnectionError`, `OperationTimeoutError` | Transport failure or budget deadline |
| `LimitError` | A request, byte, item or queue bound was reached |
| `ClosedError` | The service is closed |
| `CheckpointError` | Durable handoff failed/timed out; acknowledgement unknown, never automatically replay |

Recovery policy:

- Only a 401, or a redirect to an approved login route, proves expiry.
- Safe GET reads then log in once more and retry once, within the same budget.
- View-selection POSTs are never replayed.
- A denial or unrecovered expiry starts a 60-second cooldown for that operation
  on that login; a failed login starts one for the whole login.
- 429 and 503 pause the whole scheduler, honouring `Retry-After` up to 24 hours.
