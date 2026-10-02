# Verification

What has actually been run, and what has not. Earlier per-increment logs are
in the Git history of this file.

## 0.4.0 (2026-10-02) - Message lists only

### Offline

| Check | Result |
| --- | --- |
| Complete suite from source, Python 3.13 and 3.14 | 697 passed in both environments; one opt-in performance case deselected |
| Installed wheel and sdist, Python 3.13 and 3.14, outside the checkout | 697 passed in each of four environments; installed imports, metadata, MIT license and `py.typed` checked |
| Ruff, format, strict mypy | Clean |
| Repository hooks, untracked-inclusive secret scan, locked dependency audit | Pass; no known vulnerabilities |
| OpenAPI / route catalogue parity | Pass, 28 operations |
| Full bounded mailbox workload | Four concurrently requested independent 250-row mailboxes, five pages each, 40 total login/list requests; warm batch reuse dispatches none |

The shared read suite was extended for both mailbox folders, covering exact
wire forms, account isolation, caching/coalescing, expiry, no POST replay,
throttling, maintenance, notices, budgets and cancellation. Family tests own
summary semantics, numeric references, explicit empty sent/received pages,
header/row/date validation, limits, overlap deduplication, bounded continuation,
mid-page drift, repeated/clamped/non-progress pages and later-page failure.
Capture-scope tests execute discovery and installed-smoke flows on loopback,
reject send fields, unapproved pages/operations and a second login, and enforce
actual-attempt/list caps. No external code or fixtures were copied.

### Live and identical-byte replay

Fresh approval covered two attempts on one configured login, each capped at 24
requests and ten fixed received/sent pagination POSTs on pages 0..2. Identity was
allowed. Recipients, content opens, mark-read, downloads, sends, deletes and
read-once events were excluded. There was no automatic login replay.

| Attempt | Login submissions | Actual HTTP requests | Result |
| --- | --- | --- | --- |
| Early installed-route discovery | 1 | 11 | Populated received and explicit-empty sent page zero captured |
| Installed 0.4.0 wheel public smoke | 1 | 14 | Page, bounded batch, mid-page resume and zero-request warm page cache passed |
| Total | 2 | 25 of 48 allowed | Approval exhausted; unused requests do not authorize another login |

The final received page had two rows, one read and one unread; sent was explicitly
empty. Chromium, with networking and scripts disabled, independently checked
every visible summary field, numeric reference, computed unread/attachment flag
and empty marker in all seven captured list responses. The separately installed
MIT-licensed apix 1.5.3 pure parsers received the exact same bytes; there were zero
comparable summary-field mismatches. Neither replay used a live client.

The live smoke exercised the installed library, not checkout imports. Final
package documentation was updated afterwards; all library package bytes were
compared with the live-smoke wheel and were identical. Rebuilt artifacts were
qualified offline. Distribution checksums are in `release-evidence/0.4.0.sha256`;
sanitized live accounting is in `release-evidence/0.4.0-messages.json`.

Private captures were 0600 under a task-owned 0700 directory outside Git and
deleted after replay. No raw page, private assertion dump, screenshot, record ID
or message text is retained.

### Live-derived corrections and gaps

The first offline replay failed despite green synthetic tests: the real table
has a blank footer, and both folders show a benign legacy-module banner. Four
original regressions failed before the parser was corrected to read `tbody`
only and allow that exact information banner. Unknown notices still fail.

- Populated sent rows, multi-page metadata/continuation, attachment indicators,
  other account roles and the newer mailbox layout have no live evidence yet.
- Full mailboxes and pagination/drift limits were exercised offline. The small
  live mailbox is not load verification or a performance-improvement claim.
- Recipient discovery, full content, streams, notification checkpoints and
  sending are not implemented in 0.4.0. Their separate versions and sending
  approval plan are in [contracts/messages.md](contracts/messages.md).
- Earlier school-read families were fully regression-tested offline, not rerun
  live outside this approval. Their 0.3.0 evidence and follow-ups remain below.
- No consumer migration, credentialed CI, macOS/Windows check, push,
  hosted PR qualification or PyPI publication was performed in this increment.

## 0.3.0 (2026-10-02)

### Offline

| Check | Result |
| --- | --- |
| `pytest` from source, Python 3.14 | 622 passed (1 opt-in performance case deselected) |
| Installed wheel and sdist, Python 3.13 and 3.14, run outside the checkout | 622 passed in each of the four environments; imports resolve to the installed package |
| Ruff, format, strict mypy (src, tests, scripts) | Clean |
| OpenAPI and route catalogue parity | Pass, 26 operations |

Distribution checksums are in `release-evidence/0.3.0.sha256`, kept outside
the sdist inputs so the archive does not checksum itself.

The shared read suite (`tests/test_account_reads.py`) was checked against
planted regressions. Replaying a POST after expiry fails 6 cases. Disabling
coalescing fails 13. Caching failed reads fails 13.

### Live

The owner authorized live use of the configured accounts. Every run used
`scripts/live_capture.py`: one credential submission per run, an operation
allowlist, a request cap, and no sends, read-once events, mark-read calls or
attachments. Raw pages stayed in private 0600 scratch directories outside the
repository and were deleted afterwards.

Total for 0.3.0: 12 logins and 216 requests over four logins (two students,
each with two logins).

The final smoke ran through the installed 0.3.0 wheel on one login per student:

| Read | Student A | Student B |
| --- | --- | --- |
| identity, student_information | OK, matches Chromium | OK, matches Chromium |
| final_grades, grades | 26 subjects, 17 grades | 11 subjects, 6 grades |
| attendance, attendance_detail | 10 records | 1 record |
| attendance_frequency, subject_frequency (one day) | OK, 125 gateway rows | OK, 112 gateway rows |
| timetable | 91 slots match Chromium, including substitution notices | 91 slots match Chromium |
| announcements | 7 items | 7 items |
| agenda, two months, plus one detail | 5 and 13 events and the detail match Chromium | 3 and 3 events and the detail match Chromium |
| homework | Empty month matches Chromium | Empty month matches Chromium |
| completed_lessons_page | `ViewDisabledError` | `ViewDisabledError` |
| behaviour notes page | Explicit empty | Explicit empty |
| Requests | 28 | 28 |

"Matches Chromium" means `scripts/crosscheck.py` compared the parser's output
with Chromium's rendering of the same bytes: every event, tooltip text,
reference, detail field, timetable slot and notice tooltip, and profile field.

Grade, attendance and announcement counts were checked against the raw page
structure. On both students, every real grade box became a record. The
remaining boxes are a hidden template row and the observation card (see gaps).

Populated homework was verified on an earlier capture of the same build: 2
assignments (one marked done) and their detail page match Chromium. The
one-month window boundary was confirmed live: 1 Sep to 1 Oct is accepted and
1 Sep to 31 Oct is rejected.

### Defects found live and fixed

Each one had a failing test, written from an original fixture with the observed
structure, before its fix.

| Family | Live behaviour | Before | Now |
| --- | --- | --- | --- |
| Homework | Columns: subject, teacher, topic, category, date and weekday, due date and weekday, status, options | Mislabeled fields; weekday parsed as clock; every populated list failed | Header-mapped columns, weekday check, status and done marker |
| Homework | Ranges longer than one month answered with "Wybrano nieprawidłowy zakres daty." and an empty marker | Reported as an empty list | Rejected up front; the notice is `InvalidInputError` |
| Completed lessons | "Ten widok został wyłączony przez administratora szkoły." on all four logins | `ParseError` | `ViewDisabledError`, on every page parser |
| Profile | Name label "Imię i nazwisko ucznia" | `ParseError` | Parsed; the login owner's rows are ignored |
| Timetable | Substitution notice wrapped in its tooltip anchor | `UnsupportedCapabilityError` | Notice metadata read from the wrapping anchor |
| Agenda | 33-line meeting description | `LimitError`; with a larger cap, numbered lines became bogus fields | One `Opis` field until the next known label; 256-line cap |

The profile, timetable and agenda failures also occur on the previous `main`.
They were found only because the final smoke covered every family, not only the
0.3 ones.

## Gaps

- **Completed lessons, populated.** Every available login shows the view
  disabled by its school, so no populated layout or pagination has been seen
  live. The parser follows source-informed requirements with original fixtures.
- **Behaviour notes.** Both students have an explicit empty page. Public support
  stays deferred ([decision](contracts/behaviour-notes.md)).
- **Observation card.** The grades page can include "Karta spostrzeżeń", a table
  of formative assessments. It is not read yet, and apix does not read it either.
- **Coverage breadth.** Two students at the observed schools. Other schools,
  account roles, last-login views, custom attendance types and populated
  descriptive grades are unverified.
- **Not run in 0.3.0.** The scheduled credentialed CI, macOS and Windows, PyPI,
  and the `librus-mcp` migration.

## Earlier releases

- **0.1.0** (2026-09-30): login, identity and profile, with transport, scheduler
  and budget proof offline. Installed artifacts were verified on Linux with
  Python 3.13 and 3.14. A four-login MCP stdio experiment (closed PR #38)
  completed offline. First GitHub CI run:
  [36721820811](https://github.com/krzysztofbury/librus-python-api/actions/runs/36721820811).
  Checksums are in `release-evidence/0.1.0.sha256`.
- **0.2.0**: grades. A bounded four-context live comparison used 94 of 128
  allowed requests. See [contracts/grades.md](contracts/grades.md) and
  [BENCHMARKS.md](BENCHMARKS.md).
