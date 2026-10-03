# Public API (0.4.2)

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
  counts, clamped/repeated pages and pages containing only seen IDs fail with
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

Live scope, apix coverage and remaining gates: [contracts/messages.md](contracts/messages.md).

## Sending (0.4.6, offline-qualified only)

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
Sender identity/observation are bound at the potential-dispatch boundary, not
invented for failures before it. Sent page/batch caches are invalidated there,
including uncertain sends; unrelated received summaries remain cached unless
session invalidation requires a full clear. Diagnostic `ok` means classified
completion, not necessarily ACCEPTED; inspect the typed result.

Attempts are process-local, not confirmation tokens, a durable outbox or
upstream idempotency. Constructing another attempt can duplicate delivery; no
automatic retry of UNKNOWN or cancelled attempts is safe. The consumer owns
preview/confirmation, durable attempt records and any manual reconciliation.
References are structural values, not proof of consent or intended identity.
No attachment upload, reply, forward or scheduled-send API is introduced.

No live send is authorized by installation or this API. Qualification remains
separately gated to the one privately specified recipient, one approved message
and at most one dispatch, after exact sender/recipient/payload verification and
fresh bounded discovery approval. No additional/group/substitute recipient or
fallback is allowed. See [the send contract](contracts/sending.md).

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
