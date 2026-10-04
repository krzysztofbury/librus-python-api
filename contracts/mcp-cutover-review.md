# MCP cutover contract review

Review date: 2026-10-04. Library baseline: merged PR #15, commit
`7c9f4b7604f93ecb031963cc9cfb41483c44440a`, confirmed through GitHub.
Consumer default branch: `0aaf658c657197817a7c8cae35d39f05484403fd`, confirmed
through GitHub. Also inspected consumer adapter branch
`1b400cfed1ab87d14d1be1939851de820bc5adeb`: its additional identity/final-grade
adapters are opt-in experiments, not deployed default-backend evidence.

The GPL-3.0-only consumer's tool signatures, output models and orchestration
were inspected as requirements. No implementation, fixture or documentation was
copied. Original library changes and examples follow this repository's MIT
provenance rules. This review makes no consumer configuration or storage changes.

## Migration decision

Updated 2026-10-04 after PR #16: target native MCP 2.0 directly. There is no
requirement to preserve MCP 1.x names, inputs, grouping, field aliases or null
conventions. Replace its schemas and serialization with the library's native
semantics. Preserve safety and durable-state invariants through explicit migration
and rollback. The complete 18-item MCP 2.0 review is in the
[roadmap review](mcp2-roadmap.md).

## Tool-by-tool mapping

Names in the first column refer to `librus-mcp/src/server.py`; the typed schema
reference is `src/output_models.py` at the consumer revision above.

| Current MCP tool | Library owner | Native integration semantics / remaining gap |
| --- | --- | --- |
| `list_students` | Application account configuration | Return configured aliases, not upstream student IDs; separate logins remain separate contexts |
| `get_student_information` | `student_information()` / `StudentInformation` | Use native register number and explicit lucky-number availability |
| `get_final_grades` | `final_grades()` / `FinalGrades` | Expose `predicted_annual`, `annual` and availability; no fabricated `-` sentinel |
| `get_grades` | `grades(view=...)` / `Grades` | Expose typed numeric/descriptive records; school averages are raw values, not computed GPA |
| `get_grades_window` | `grades_window(start, end, view=...)` / `GradeWindow` | Optional inclusive boundaries and original view now supported. Preserve numeric-then-descriptive ordering; consumer owns compact projection and response offset/limit |
| `get_attendance` | `attendance(view=...)` / `Attendance` | Expose records and displayed semesters without legacy map grouping |
| `get_attendance_window` | `attendance_window(start, end, view=...)` / `AttendanceWindow` | Optional inclusive boundaries and view now supported; consumer owns compact projection and offset/limit |
| `get_attendance_detail` | `attendance_detail(id)` / `AttendanceDetail` | Expose stable `normalized_fields`, preserving unknown/raw data and ancillary notes |
| `get_attendance_frequency` | `attendance_frequency()` / `AttendanceFrequency` | Ratios are 0..1; unknown or zero-denominator results are `None`, not fabricated 0 or 1 |
| `get_subject_frequency` | `subject_frequency(start, end)` / `SubjectFrequencies` | Expose native ratios, unknowns and subject records without merging duplicate display labels |
| `get_homework` | `homework()` or `homework_range(request)` / `Homework` | Consumer chooses default dates; keep native `subject` and `topic`. Multi-month helper supports a 370-day date difference |
| `get_homework_detail` | `homework_detail(reference)` / `SchoolDetail` | Accept the native same-account reference; expose normalized fields and preserve full text |
| `get_schedule` | `agenda(year, month)` / `Agenda` | Integer inputs and typed day/event arrays, retaining metadata, lesson/time and reference |
| `get_schedule_detail` | `agenda_detail(reference)` / `SchoolDetail` | Native same-account reference and normalized detail fields; no arbitrary URL input |
| `get_timetable` | `timetable(monday)` / `Timetable` | Consumer chooses default Monday; expose nested days/periods/lessons, changes and optional recess |
| `get_announcements` | `announcements()` / `Announcements` | Keep `content` and displayed/typed dates; content fingerprint is not an upstream ID |
| `get_completed_lessons` | `completed_lessons()` / `CompletedLessons` | Continue bounded batches with one shared total budget; preserve combined subject/teacher information without guessed splitting |
| `get_completed_lessons_page` | `completed_lessons_page()` or `completed_lessons()` | Native page count differs from last-page index; native cursor includes fingerprint/account/range. Preserve it rather than inventing one from offsets |
| `get_messages` | `messages_page()` / `messages()`; explicit modern equivalents | Choose backend explicitly; keep native page counts, truncation and cursor drift. Full pager-less legacy sent pages remain unsupported rather than silently treated as complete |
| `get_message_content` | `message_content()` or `modern_message_content()` | Native references include folder/backend/account. Received opens need `allow_mark_read=True`; current MCP read-only annotation does not express that side effect |
| `get_message_attachments` | Content response attachment metadata | Listing via received content can mark read. Correct the consumer contract/consent before enabling, never silently grant permission |
| `download_attachment` | Attachment streams plus `files.publish_attachment()` | MCP selects an existing destination. Native returns size, digest, media type and path; use final basename for MCP filename. No content open is needed |
| `get_recipient_groups` | `recipient_groups()` / `modern_recipient_types()` | Preserve native type/group records with account/backend and hierarchy |
| `get_recipients` | `recipients()` / explicit modern directory methods | Preserve unsupported/empty distinction and qualified group selections; an ID/name map cannot represent every hierarchy |
| `send_message` | Prepare/send attempts plus optional `PersistenceStore` | Consumer owns preview wording and human approval; library owns bounded single-use dispatch and durable payload/context binding. ACCEPTED is not independent delivery. UNKNOWN never becomes failed/retryable |
| `get_recent_schedule_events` | `consume_schedule_events()` / `decode_schedule_events()` | Checkpoint complete bytes before parse; explicit consume consent, no retry; replay stored response locally |
| `get_new_notifications` | `NotificationStore` and `NotificationWorkflow` | Map `schedule` category to native `AGENDA`; preserve requested-category baselines, staged receipts and replay. Consumer acknowledges only after delivery boundary; migrate old state explicitly |
| `get_behaviour_notes` | No public implementation | Existing MCP parser is experimental and its populated shapes were assumed. It is not sufficient independent evidence to enable a native populated parser |

## Reusable additions in this branch

- Native MCP 2.0 follow-up: `DetailField` and family-specific stable detail keys,
  preserving unknown labels, complete displayed values and ancillary notes.
  Duplicate canonical labels fail before public result/cache publication. See
  [detail fields](detail-fields.md). Other reusable A01-A18 foundations already
  exist; unified MCP wire envelopes, packaging, config and resource hosting remain
  consumer implementation work.
- `HomeworkRangeRequest` and `homework_range()` implement explicit bounded
  aggregation. One budget covers authentication and all monthly POSTs. Partial
  failure is never a successful or cached aggregate. See [school reads](school-reads.md).
- Grade/attendance windows accept either missing civil-date boundary, preserve
  the selected upstream view, and accept two dates at most 370 days apart.
  Source collections remain bounded; windowing does not imply less upstream I/O.
- Strict JSON decoding rejects non-standard non-finite constants and finite-text
  numbers that overflow the decoder, even in otherwise ignored response fields.
- Original modern attachment wire cases include sent references and a zero-byte
  archived sent stream through atomic publication. This extends offline proof,
  not live evidence for those layouts.

## Typed request and response policy

Public domain values are frozen dataclasses with tuples and typed dates/enums.
Request dataclasses (including send submissions, references, cursors and the new
homework selection) are validated by public operations before I/O. Constructing
a dataclass is not runtime validation. Configuration uses strict frozen Pydantic
models; wire schemas/parsers validate upstream data. `py.typed` ships in the wheel.

The old consumer models frequently require non-null strings/numbers where native
values preserve unknown state. Replace them for MCP 2.0 instead of coercing native
results into legacy formats. Serialization still needs explicit decisions:

- Absent grade weight/count/teacher, sent unread status, unavailable lucky number
  and unknown attendance ratios must retain their native absence/availability.
- Civil dates and naive school wall times must not silently become UTC instants.
- Empty, unavailable, disabled, malformed and bounded-partial results differ.
- Native page-count, cursor, receipt and send-status values must not be reduced
  to a boolean or next offset that loses safety semantics.
- Unknown detail labels and full-width notes are data, not extra callable fields.
- Enforce the MCP response byte cap after its explicit projection; never truncate
  a library collection while describing it as complete.

Transport-specific output DTOs, JSON serialization, pagination presentation,
default date selection and human confirmation remain consumer responsibilities.
Creating parallel native DTOs that reproduce every MCP response would couple the
reusable client to the transport and would not remove these decisions.

## Evidence-dependent work

Behaviour notes need a populated page establishing label/row association, note
identity, dates, teacher/category semantics, detail links and explicit empty
markers. The observation card needs its own independently established table
boundary, row/column spans, assessment metadata and relationship to grade boxes.
The existing observation that the card is present does not specify those shapes.
Neither feature is implemented by guessing a schema or treating unsupported
populated data as empty. See [behaviour notes](behaviour-notes.md).

Populated completed lessons, additional schools/roles, new attachment layouts
and disposable read-once qualification remain live-evidence gates. No new live
calls were made for this review. C01-C05 retain their existing evidence limits.

## Consumer acceptance still required

The mapping above is a requirements review, not executed MCP 2.0 acceptance.
Before cutover, run every default and enabled optional tool through stdio with
the installed candidate, assert exact JSON keys/types/absence and error mapping,
and exercise old-state migration/rollback with disposable stores. Confirm that
the old send guard and notification checkpoints survive migration. Do not
enable fallback to the old backend on native parse/permission failures.
