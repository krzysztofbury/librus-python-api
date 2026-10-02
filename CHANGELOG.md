# Changelog

## 0.4.0 - Ordinary message lists

Local-first feature release; not published to PyPI. Communication is split into
separate versions; sending remains plan-only.

- `MessageFolder`, immutable summary/reference/timestamp records and
  `messages_page` / `messages` under the shared account/budget/read boundary.
- Bounded zero-based pagination and account/folder-bound cursors with seen IDs,
  overlap deduplication, page/mid-page drift checks and explicit truncation reasons.
- School wall-time timestamps retain raw text and the `Europe/Warsaw` policy,
  without inventing UTC offsets or DST folds. Recipient-read status is not inbox
  unread status.
- Fixed pagination forms, including on the URL shared upstream with sending.
  Send, recipient, subject/body and upload fields are rejected before dispatch.
  No content opens, mark-read, deletes, downloads, sends or read-once calls.
- Private bounded list discovery/installed smoke tooling, offline identical-byte
  apix comparison and independent Chromium visible-field/reference/flag checks.
- Live-derived regressions for the blank footer and benign legacy-mailbox banner.
  Full bounded concurrent mailboxes, budgets, continuation and malformed layouts
  are exercised offline with original fixtures.
- Populated received and empty sent lists qualified on one login. Populated sent,
  multi-page metadata, attachment flags, other roles and newer mailbox layouts
  remain pending, not silently promoted by synthetic tests.

## 0.3.0 - School reads

Local-first release; not published to PyPI.

### Added

- Attendance: views, date windows, details, gateway records, and overall and
  per-subject frequency with explicit ratio policies.
- Timetable: explicit weeks with typed days, periods, lessons, notices and
  recesses.
- Announcements with full text and account-scoped content references.
- Agenda months and details. Homework windows and details.
- Completed-lesson pages and bounded resumable batches.
- `ViewDisabledError` for views the school has switched off, on every page.
- `scripts/live_capture.py` (one login, allowlist, request cap, private 0600
  captures outside any Git work tree) and `scripts/crosscheck.py` (offline Chromium
  comparison).

### Changed (breaking for 0.3.0.dev0 users)

- `HomeworkItem` now matches the live page: `subject`, `teacher`, `topic`,
  `category`, `assigned_on`, `due_on`, `submission_status`, `marked_done_at` and
  `reference`. `lesson`, `assigned`, `due`, `extra_cells` and `SchoolDateTime`
  are removed.
- `homework()` accepts at most one calendar month, the upstream limit.
- `AccountTransport.request` takes a plain string form for view POSTs, limited
  to that endpoint's known field names. The selection wrapper types are removed.

### Fixed

Each fix was found on live pages:

- Homework columns were mislabeled and weekday cells parsed as clocks, so every
  populated list failed.
- A homework range rejected upstream was reported as an empty list.
- The student profile failed on the current name label.
- Timetable substitution notices wrapped in their tooltip anchor failed.
- Long agenda descriptions exceeded the tooltip line cap, and their numbered
  lines became bogus fields.
- From review: text beside a wrapped timetable notice and unknown homework
  handlers now fail instead of being dropped.

### Internal

- One typed fetch per operation through a single read path, replacing two
  string-dispatched chains.
- Shared HTML helpers moved to `markup.py`.
- The shared read guarantees are tested once for every operation
  (`tests/test_account_reads.py`). 32 duplicated per-family tests, the apix
  parity suites and the tests that needed closed PR #38 were removed.
- The `mcp` development dependency was removed.

## 0.2.0 - Local-first grade coverage

- First increment: typed final-grade summaries through one bounded HTML GET,
  with school-provided strings and explicit optional-column availability.
- New original semantic-header, merged-behaviour, unassigned, malformed, bound,
  wire/isolation/cache/recovery fixtures and an opt-in real MCP stdio adapter.
- Existing lifecycle, budgets, diagnostics, and public identity/profile contracts
  are preserved. No PyPI publication or production consumer migration is included.
- Qualify exact PerformLogin/Grant continuations, explicit Account.UserId gateway
  references, and narrowly repaired browser HTML/spacer rows with original
  regressions. Reuse the authorization form instead of fetching it twice.
- Load optional Loguru diagnostics only when enabled. Add a paired synthetic
  parser measurement and document live sample benefits and non-wins.
- Raise the shared traffic defaults to five requests/second and burst ten while
  retaining concurrency, queues, deadlines, cooldowns, and token accounting for
  every login hop. These are configurable engineering defaults, not Librus quotas.
- Next increment: typed inline numeric/descriptive grade records, raw school
  average availability, and inclusive date windows over one cached collection.
  Grade-view POST is explicitly view-changing and never automatically replayed.
- Original regressions protect weekday date suffixes, invisible HTML comments,
  empty-grade markers, metadata/entry bounds, unsupported-layout rejection,
  four-login default-policy isolation/coalescing, budgets, and cancellation.
- Installed numeric-grade comparison with unmodified apix completed under approved
  caps with common-field parity. Document business gaps independently of speed,
  including intentional unknown-metadata and school-average differences.
- Complete descriptive-only rows, multiple publication blocks, dated period/annual
  and predicted marks, and all/week/last-login selections with isolated
  cache/coalescing keys. Preserve undated descriptive semester text separately.
- Expanded bounded qualification covered four independent login contexts, with
  three completed installed comparisons and one initial native parser failure
  followed by successful memory-only installed-parser replay. Original regressions
  protect the undated-text and overlapping-subject fixes. No automatic live retries.
  Populated averages, dated descriptions/publications/corrections remain live-unqualified.
- Close 0.2.0 scope at grades. Attendance and the remaining academic/school reads
  move to 0.3.0; messaging moves to 0.4.0. Daily live CI, broad capacity/RSS work,
  consumer migration, and PyPI publication retain separate gates.

## 0.1.0 - Local-first account and identity service

- Native async account-isolated transport with scoped cookies, fixed destinations,
  explicit TLS/proxy settings, and bounded streamed/decompressed bodies.
- Shared rate/burst/concurrency/queue and whole-operation budgets, deterministic
  cleanup, bounded parser workers, and repeated-cancellation regression coverage.
- Public typed service/client API, credentials/configuration, immutable owner/
  student identity and profile results, specific exception factory, and optional
  redacted structured Loguru diagnostics.
- Coalesced safe reads, explicit account/session freshness, and Tenacity-bounded
  recovery for proven expiry only, without automatic replay of login failures.
- Evidence-labelled OpenAPI wire contracts and independently authored fixtures.
- Installed-artifact loopback/MCP stdio qualification through an opt-in consumer
  adapter. No default consumer backend change or production release.

This version is a locally built delivery, not a PyPI publication or independently
verified live Librus integration. PyPI begins at 1.0.0rc1. Live authentication/
layout evidence, daily credentialed CI, wider platforms, and later endpoint
families remain explicitly pending.
