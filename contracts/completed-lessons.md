# Completed lessons (0.3.0)

Calls: `completed_lessons_page` and `completed_lessons`. The route and form are
source-informed. Fixtures are original. A page whose notice says the school
disabled the view ("Ten widok został wyłączony przez administratora szkoły.")
raises `ViewDisabledError`.

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
  into a teacher. Exactly two comma-delimited components, each stripped of
  surrounding whitespace and line breaks, supply separate subject/teacher (some
  schools render `<b>Subject</b>, <br>Teacher`); a blank component fails.
  Ambiguous combined text is retained without inventing a teacher.
- Dates accept ISO or DD-MM-YYYY, must be valid civil dates within the selected
  window, and retain their original string. Attendance links reuse the fixed
  existing attendance-detail namespace. A caller may pass the returned numeric ID
  to the same account's `attendance_detail()`; no automatic detail fan-out occurs.

## Pagination, limits and lifecycle

Recognize one decorated table with seven-cell rows: one center/small date marker,
one tiny weekday marker and five ordered data cells. Class order/additional classes
do not change meaning. A `decorated filters` table (the date-filter form) is not a
data table. Nested tables, merged/missing columns, active content in
record values, ambiguous references and invalid dates fail without partial output.

Some schools add an `e-Tablica` header column. Optional columns are located by
their header labels (`COMPLETED_LESSONS_OPTIONAL_HEADERS`); that header row must
then span exactly the extended row width. Their content is not modelled, so a
nonempty optional cell raises `UnsupportedCapabilityError` rather than being
dropped. A single blank full-width cell as the last body row is a closing
spacer, not a lesson; anywhere else, nonblank or with another width it fails.
An empty result requires one nonblank `msgEmptyTable` marker and single-page
metadata, never missing markup alone. Headers are not records.

The optional pagination display must report one-based current and total pages as
`[Strona ]N z M`, with normalized whitespace, optionally followed by the item
range `Pozycje A..B z T`. It must match the requested page. A shown range must
satisfy `1 <= A <= B <= T` and count exactly the rows parsed from the page.
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

From 0.4.11 detected sequence drift/repeated pages raise `StaleCursorError`
(`kind=stale_cursor`), not `ParseError`. Malformed/clamped page metadata remains
PARSE and invalid caller cursors remain INVALID_INPUT. Restart is explicit;
the library never returns partial success or retries a selection.

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

## Evidence

On 2026-10-02, all four available logins (two students, each with two logins)
returned the disabled-view notice for every requested window, including a past
window and one ending in the future. The earlier `AttributeError` and
`ParseError` stops were this notice. The page had no lesson table because the
view is switched off; nothing was wrong with the request. The reference client returns `[]` for
the same page.

A populated page, pagination and resume have therefore never been observed
live by the guarded capture. On 2026-10-18 the owner read a populated page of
another school privately and offline: it showed the filter table, the
`e-Tablica` column, the bold subject cell, the item range and the closing
spacer handled above. Fixtures copy that structure with invented values. The
guarded live gate for this layout is still pending. The row and pagination rules above come from source-informed requirements
and original fixtures. Verify them on an account with the view enabled before
relying on them (see [TODO.md](../TODO.md)).
