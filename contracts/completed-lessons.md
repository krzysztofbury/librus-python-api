# Completed lessons: 0.3.0.dev0

This increment adds ordinary completed-lesson reads, not message/event consumption,
consumer migration or publication. The central HTML route and selection form are
source-informed business requirements. Original implementation and fixtures contain
no copied third-party source, captures or identifiable records. The initial
increment was offline-only. Later explicitly authorized installed qualification
attempts stopped without qualifying the live lesson layout; see the evidence below.

## Public domain and wire contract

- `completed_lessons_page(start, end, page=0)` fetches one explicit zero-based page
  and returns immutable `CompletedLessonsPage` with rows and `page_count` parsed
  from that same response. There is no page-count preflight request.
- `completed_lessons(start, end, cursor=None, max_pages=4, limit=128)` fetches a
  bounded batch and returns `CompletedLessons` with `pages_fetched` and optional
  `next_cursor`. Both APIs accept the usual `budget` and `max_age_seconds`.
- Dates must be plain civil `datetime.date` values, ordered and inclusive over
  at most 371 days. No local-clock default or school timezone is guessed. The wire
  form fixes all-subject selection and container 1001; callers cannot supply forms
  or arbitrary authenticated destinations.
- A row retains raw/typed date and lesson number, weekday text, combined
  `subject_teacher_text`, subject, optional teacher, multiline topic, opaque
  `z_value`, attendance symbol and optional numeric `attendance_detail_id`.
  Blank/`-` lesson numbers stay `None`. A single combined name is not fabricated
  into a teacher. Exactly two comma-space-delimited components supply separate
  subject/teacher; ambiguous combined text is retained without inventing a teacher.
- Dates accept ISO or DD-MM-YYYY, must be valid civil dates within the selected
  window, and retain their original string. Attendance links reuse the fixed
  existing attendance-detail namespace. A caller may pass the returned numeric ID
  to the same account's `attendance_detail()`; no automatic detail fan-out occurs.

## Pagination, limits and lifecycle

Recognize one decorated table with seven-cell rows: one center/small date marker,
one tiny weekday marker and five ordered data cells. Class order/additional classes
do not change meaning. Nested tables, merged/missing columns, active content in
record values, ambiguous references and invalid dates fail without partial output.
An empty result requires one nonblank `msgEmptyTable` marker and single-page
metadata, never missing markup alone. Headers are not records.

The optional pagination display must report one-based current and total pages as
`[Strona ]N z M`, with normalized whitespace. It must match the requested page.
Missing pagination is accepted only for page zero as a single page. Total pages
must be 1..1000. Clamp/wrong-page responses and malformed/contradictory metadata
fail. Short nonterminal pages do not imply completion; metadata decides it.
Other live pagination layouts remain unsupported until independently evidenced.

Bounds: 256 rows per page, eight pages and 256 returned rows per batch, 1024
characters per ordinary field, 65536 per topic, 262144 total rendered characters
per page, plus common body/tree/parser-worker and shared admission budgets. Parser
overflow rejects the page. Only caller-selected batch limits intentionally stop
retrieval and produce a cursor; errors never return a partial-success cursor.

The whole batch owns one account operation/lock, original deadline, request/body
budget and diagnostic outcome. Every request passes through the existing global
rate/concurrency/queue scheduler. Selections are POSTs with `select_view` effect
and are never replayed, even for proven expiry on a later page. Authentication,
coalescing, bounded caching, invalidation and joined cancellation remain isolated
per login. Cache keys distinguish page selections from batch/cursor/limit selections.

## Continuation integrity and limitations

`CompletedLessonsCursor` binds account alias, explicit dates, next page/offset,
page count and SHA-256 fingerprint of canonical domain rows. Fingerprints exclude
HTML/CSRF noise. Cursors are immutable caller data, not access tokens, upstream IDs,
durable notification state or snapshot guarantees. Reprs hide names, dates and
fingerprints. Account/window mismatch and invalid cursor values fail before login.

A mid-page resume re-fetches that page, verifies count and fingerprint, and returns
only remaining rows. A page-boundary resume fetches the next page directly and
rejects immediate repetition of the prior fingerprint. Within a batch, any repeated
page fingerprint, count drift or wrong current-page display fails with `ParseError`.
Identical legitimate pages are conservatively ambiguous. Start again without a
cursor after drift rather than editing its fields to suppress integrity checks.

There is no transactional snapshot or stable upstream lesson ID. Changes to already
consumed pages at page boundaries, same-count insertion/reordering, long repeated
cycles across separate batches, a service restart or cursor reuse across sessions
cannot all be detected. Persisted cursors should not be treated as reliable sync
watermarks. Explicit cache reuse serves prior results; fresh resumed reads remain
the default. Consumer serialization/persistence is a separate task.

## Evidence and qualification

The 2026-10-02 qualification follow-up reached one first-page POST in each of two
separately authorized installed-wheel attempts. Both responses had no decorated
table or pagination span. The first stopped with `AttributeError`; the second
stopped with `ParseError`. No successful native/apix/browser comparison, explicit
empty lesson result, pagination or resume was established. A third reordered attempt
stopped in agenda comparison before reaching lessons. Raw pages were discarded.

An original commented-markup regression independently reproduces an attribute
error in empty-marker discovery. Comments are now excluded from attribute reads;
recognized records and empty pages keep their semantics, while unknown commented
pages produce `ParseError`. This offline bug and fix do not prove the cause of the
discarded first live failure or explain why the live lesson layout was absent.

The original parser/service tests own visible fields, pagination integrity, exact
forms, four-login isolation/coalescing, page/batch cache distinction, maximum bounds,
resume drift, POST non-replay, cumulative budgets and later-page cleanup. Optional
apix comparisons feed identical original bytes to unmodified baseline business
functions with external sockets/DNS blocked and distribution hashes checked.
They distinguish common fields from fabricated teachers/dates, BR word joins and
whitespace-sensitive baseline counts. They do not qualify rendered live school data.

No JSON parity, live populated/empty pages, account roles, school-specific symbols,
live date/layout variants, sustained live performance or consumer readiness is
claimed. Those require fresh bounded authorization, identical-response native/apix
comparison and independent rendered school-content validation. See VERIFICATION.md.
