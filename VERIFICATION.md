# Verification

What has actually been run, and what has not. Earlier per-increment logs are
in the Git history of this file.

## 0.4.3 (2026-10-02) - Bounded attachment streams

### Offline and review

- Complete source suite on Python 3.13/3.14: 865 passed in both environments,
  one opt-in performance case deselected. Ruff, format and strict mypy pass.
  OpenAPI parity covers 34 operations.
- Installed wheel and sdist suites pass all 865 tests in four isolated Python
  3.13/3.14 environments outside the checkout. Installed import location,
  package version, MIT license, `py.typed` and dependency consistency pass.
  Every environment replays both content captures against independent private
  Chromium expectations, including the populated attachment linkage. Final
  library package bytes match the wheel used for the live stream smoke.
- Locked dependency audit reports no known vulnerabilities. Repository hooks
  and staged/worktree/history secret scans pass.
- Public stream tests exercise original two-origin HTTP, independent login
  contexts, account-bound references, credential/cookie isolation, hostile
  redirects, real streaming, 64 KiB chunks, exact byte bounds, unknown-length
  cumulative budgets, framing/encoding failure and no automatic replay.
- Representative offline load streams one full 50 MiB file with an exact
  seven-request login/resolve/download budget. Four independent logins with mixed
  reads/downloads saturate shared admission; paused streams retain scheduler
  slots and an exact six-request warm shared budget completes queued work.
- Early break, queued/entry/body cancellation, repeated cancellation during
  delayed cleanup, service close and paused-consumer deadline cases release
  capacity only after joining owned transport work. Subsequent reads succeed.
- Pair-programmer design precedes implementation. Independent post-review found
  a first-field-only encoding guard accepted duplicate Content-Encoding and
  unsupported Transfer-Encoding with false completion. All three raw-wire
  regressions failed before the fix. The corrected complete-field guard rejects
  those representations before delivery; ordinary chunked framing succeeds.
  Duplicate identity/chunked field cases also remain in the owning regression
  table. Re-review approved the corrected offline scope with no blockers.
- The qualification runner's original loopback tests enforce one login, 24
  attempts, exact account-bound selection, already-read discovery, one bounded
  smoke download, stop-on-ambiguity and no retained attachment bytes.

### Bounded live qualification

Fresh approval allowed up to four independent discovery logins and one reserved
installed-smoke login, each with 24 total wire attempts. Scope: identity,
received/sent page zero, at most one already-read received content open per
login, and the selected smoke attachment's resolution/download up to 10 MiB.

| Attempt | Logins | Requests | Content opens | Download | Result |
| --- | --- | --- | --- | --- | --- |
| Discovery A | 1 | 11 | 0 | None | No eligible attachment |
| Discovery B | 1 | 11 | 0 | None | No eligible attachment |
| Discovery C | 1 | 12 | 1 | None | One attachment reference observed |
| Installed wheel smoke, same selected login/reference | 1 | 14 | 1 | 1 | 930,056 bytes, clean EOF |
| Total | 4 of 5 allowed | 48 of 120 allowed | 2 | 1 | No expanded or repeated attempts |

The fourth discovery login was unnecessary after an eligible message was found.
Unused allowances are not permission for reruns. No unread or sent content was
opened; no sending, deletion, read-once operation or consumer migration occurred.
The download supplied no Content-Length; actual byte accounting and clean EOF
confirmed stream completion. Attachment bytes were consumed and discarded,
never saved. One successful file does not establish arbitrary key/header formats
or the absence of upstream read effects.

Chromium independently checked all ten captured responses with scripts and
networking disabled. This extends list evidence to 35 received rows and eight
populated sent rows on page zero, including attachment/unread flags. Two content
responses include one displayed attachment and a read receipt. Rendered fields,
body lines, filename and numeric route linkage agree. The browser check initially
mistook popup-name/dimension numbers for attachment IDs; extracting only the
inert route literal corrected that false mismatch without a parser change.

Apix 1.5.3 received identical captured list/content bytes through inert parsers.
Common summary and four content fields agree. Apix has no attachment-stream,
attachment-metadata or read-receipt contract; those are native independently
checked features, not inferred apix parity.

### Evidence and remaining gaps

- Sanitized accounting is in `release-evidence/0.4.3-streams.json`; local artifact
  checksums are in `release-evidence/0.4.3.sha256`. No public evidence contains
  account/message/file IDs, signed keys, filenames, cookies or body text.
  Task-owned private captures, browser expectations, build trees and virtual
  environments are deleted after qualification; only the two local distribution
  archives and sanitized evidence remain.
- Sent-message downloads, multiple/empty files, alternate attachment handlers,
  key/header variants and upstream read effects remain live-unqualified.
  Conservative key grammar and provisional `none` effect classification remain
  source-informed restrictions. Populated pagination/new mailbox layouts and
  other 0.4.x gaps not explicitly observed here remain pending.
- Library file naming/saving/publication is intentionally absent. MCP atomic
  publication, notifications, sending, credentialed CI and PyPI publication
  retain their separate scopes. No push or publication is part of 0.4.3.

## 0.4.2 (2026-10-02) - Message content and inert attachment metadata

### Offline

- Complete source suite, Python 3.13/3.14: 803 passed in both environments,
  one opt-in performance case deselected. Installed wheel/sdist suites also pass
  all 803 tests in four isolated environments outside the checkout; installed
  imports, package metadata, license, `py.typed` and dependency consistency checked.
- All four artifact environments replay the three captured content responses
  and an original synthetic two-file response through the installed public API
  on loopback. Every content field agrees with independently recorded Chromium
  expectations, not a comparison against the same parser. Warm reuse dispatches
  zero requests. The qualified library package bytes match the live-smoke wheel.
- Ruff, format and strict mypy are clean. OpenAPI parity passes for 32 operations.
- Repository hooks, staged/worktree/history secret scans and locked dependency
  audit pass; no known dependency vulnerabilities were reported.
- Four independent maximum-content reads (65,536 characters and 20 file
  references each) pass through real loopback HTTP under one exact 24-request
  login/content budget. This is representative bounded offline load, not a
  performance-improvement or large live-mailbox claim.
- Shared read tests own isolation, coalescing/cache, budget/deadline/cancellation,
  notices, response limits, exact GET wire forms and no expiry replay.
- Content tests own explicit consent, bound reference validation, metadata/body/
  receipt semantics, whole-read failure, attachment linkage/cardinality/limits,
  duplicate names versus IDs, and invalidation of both received page and batch
  caches even when parsing fails. Capture tests exercise both approved flows,
  unread-selection rejection, scope and actual-attempt/login caps offline.

### Bounded live qualification

Fresh owner approval: two attempts on one independent account context, each
with one login submission, 24 total HTTP attempts, identity, received/sent page
zero and at most two opens of one already-read received message. No unread
opens, sending, downloads, deletion or read-once requests were allowed or made.

| Attempt | Login submissions | Requests | Received opens | Result |
| --- | --- | --- | --- | --- |
| Source-route discovery | 1 | 12 | 1 | Main metadata, optional read receipt and body captured |
| Installed 0.4.2 wheel public smoke | 1 | 13 | 2 | Two fresh results agree; warm reuse dispatches zero |
| Total | 2 | 25 of 48 allowed | 3 | Login authorization exhausted |

The selected already-read message has 395 normalized plain-text characters,
a displayed read timestamp and no attachments. Received lists contained two
rows (one unread) and sent lists were explicitly empty. Unread content was never
opened. Unused requests do not permit a third login or expanded scope.

Chromium independently checked all seven captured responses, including three
content responses, with scripts/networking disabled. Every common field,
rendered body line boundary and displayed read timestamp agrees. Two invented
file entries also pass the independent browser check, which is offline evidence
only. Apix 1.5.3 received the exact same three content responses through an inert
client; all four comparable fields agree. Apix has no attachment or read-receipt
contract, so those fields are independently checked, not parity-inferred.

### Regressions and evidence boundary

The observed page contains two exact `stretch` tables, not one: main metadata
and the read receipt. An original regression failed before receipt-aware parsing.
An HTML page comment caused a raw `TypeError` during attachment scanning; its
regression failed before non-element nodes were skipped. Both fixes precede the
successful installed live smoke.

A real persistent-connection disconnect test detects aiohttp's hidden GET replay:
it fails with the default retry behavior and passes with hidden retries disabled.
The service still owns explicit safe expiry recovery. Content opens never recover
or replay automatically. Potential read effects are not rolled back by parse,
transport, timeout or cancellation failure.

Privacy-safe metrics are retained in `release-evidence/0.4.2-content.json` and
distribution checksums in `release-evidence/0.4.2.sha256`. Private captures and
independent browser expectation files (0600, inside a task-owned 0700 directory
outside Git), temporary builds and environments are deleted after qualification.
No message text, field diffs, account/record IDs, cookies or screenshots remain.

### Remaining gaps

- Populated sent content, populated attachment metadata, empty/rich live bodies,
  read-receipt variants, other account roles and newer mailbox layouts are not
  live-qualified. Attachment handlers/labels have original offline proof and
  source-informed consumer requirements only; no attachment route is enabled.
- No credentialed CI, consumer migration, PyPI publication or push is included.
  Earlier feature families were regression-tested offline, not rerun live except
  for the two explicitly approved mailbox page-zero lists.
- Bounded attachment streams are next in 0.4.3. Sending and read-once operations
  remain separately planned and authorized.

## 0.4.1 (2026-10-02) - Recipient discovery

### Offline

| Check | Result |
| --- | --- |
| Complete source suite, Python 3.13 and 3.14 | 748 passed in both environments; one opt-in performance case deselected |
| Installed wheel and sdist, Python 3.13 and 3.14, outside checkout | 748 passed in each of four environments; imports, metadata, license and `py.typed` checked |
| Installed public API replay of actual private captures through loopback HTTP | All four environments: eight group types and three lookups with 1/55/1 recipients; warm cache dispatches none |
| Ruff, format and strict mypy | Clean |
| OpenAPI / route catalogue parity | Pass, 30 operations |
| Full bounded lookup | 2,000 distinct IDs sharing one display name survive one real loopback HTTP lookup |

The shared read suite owns account isolation, cache/coalescing, notices,
budgets, cancellation, exact forms and no selection replay for both operations.
The family suite owns named selectors, header/body boundaries, label/checkbox
linkage and cardinality, duplicate names versus duplicate IDs, foreign and
injected references, unsupported subgroups, limits and cache selection keys.
Capture tests own approved token selection, six-list and one-login limits, and
the actual discovery/smoke flow on loopback. No external fixture or code was
copied. `scripts/replay_recipients.py` exercises the installed runtime against
real response bytes, not only synthetic tests.

### Bounded live use

One account context, initially two attempts of at most 24 requests each. The
first scope allowed only numeric group types, which the real composer does not
use. That attempt stopped after ten requests and one credential submission,
before any recipient POST. The owner explicitly amended the remaining attempt
to the observed `wychowawca`, `nauczyciel` and `sekretariat` tokens; no third
attempt was authorized or performed.

The installed 0.4.1 wheel public smoke then passed in sixteen requests, one
login, one group GET and six recipient POSTs (two fresh reads per approved
group). Group discovery and each group lookup also passed zero-request warm-cache
checks. The three groups had 1, 55 and 1 recipients. Total: two logins, 26/48
requests. Unused requests do not authorize another login.

Chromium independently checked all eight captured responses: displayed group
labels/tokens, availability and radio linkage; recipient labels, numeric IDs and
checkbox/value linkage. The separately acquired MIT-licensed apix 1.5.3 received
identical bytes through an inert replay client. Group-token and recipient-pair
mismatch counts were zero. No message open, sending, mark-read, download, deletion
or read-once call occurred.

### Review correction and evidence boundary

The real group header initially failed parsing; an original headed-table test
failed before the `tbody`-only correction. After the successful live smoke,
review found that an unlabeled numeric checkbox could silently disappear. A new
regression failed before a cardinality guard was added. The select-all checkbox
is explicitly excluded, not misidentified as a recipient.

The strengthened parser, conservative lookup-capability naming and updated
route-evidence metadata were qualified
offline against all private captured bytes, including Chromium comparison and
the installed public runtime on loopback. That is not a fresh credentialed smoke
of changed code and does not consume another login. Qualification uses real
populated responses rather than apix/synthetic agreement as its oracle.

Privacy-safe metrics are in `release-evidence/0.4.1-recipients.json`; distribution
checksums are in `release-evidence/0.4.1.sha256`. Raw responses were private 0600
captures outside Git, deleted after final offline replay. No names, numeric
recipient IDs, raw diffs, cookies or message text are retained.

### Gaps and next increment

- Empty recipient layouts, subgroup/virtual-class selection, other group types,
  disabled recipients and other account roles remain unqualified. `grupa` lookup
  is explicitly unsupported; unknown/empty pages fail, never silently become `[]`.
- No performance improvement, general-school compatibility, consumer migration,
  credentialed CI or PyPI publication is claimed. Earlier school reads/message
  lists were regression-tested offline, not rerun live outside this scope.
- Full message content is next (0.4.2). Its potentially mark-read effect requires
  a separate approved already-read/sent message selection before live access.
- Sending remains plan-only; discovery never authorizes contact with a recipient.

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
