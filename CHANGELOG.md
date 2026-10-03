# Changelog

## 0.4.7 - Explicit modern messaging backend

Local-first. No live credentialed operation, message or publication in this increment.

- Separate modern identity/type/council discovery, strict native-owner binding,
  account/backend-specific references and isolated modern session cookies.
- Exact bounded authentication handoff and six central routes with OpenAPI parity;
  no arbitrary redirect follow, legacy fallback or account-setting mutation.
- `prepare_modern_send` freezes plain-text input for the existing single-use
  attempt lifecycle. Fixed ordinary JSON uses recipient account IDs, UTF-8
  Base64, HTML-escaped body literals, null attachment storage and normal category.
- Modern 2xx is UNKNOWN, not inferred acceptance. Only allowlisted explicit
  source-informed denial codes on validation responses establish REJECTED.
  Response loss, cancellation, expiry and unqualified evidence never allow replay.
- Original two-origin loopback tests and independent Chromium plain-text rendering
  exercise installed runtime paths. Broader directory roles/layouts, modern
  content/attachments and positive acknowledgements remain unqualified.

## 0.4.6 - Single-use sending attempts

Local-first, offline qualification only. No live message sent or package published.

- Local immutable payload preparation and single-use execution with inspectable
  NOT_DISPATCHED, UNKNOWN, ACCEPTED and REJECTED outcomes.
- Dedicated write transport, fixed repeated-recipient form, encoded-byte/field
  limits and shared account/traffic budgets. No read cache/coalescing, replay,
  redirects, recipient lookup or fallback backend.
- Joined cancellation/shutdown preserve the attempt outcome. Unknown responses,
  response loss, expired sessions and post-dispatch limits never imply rejection
  or safe retry. Sent-list caches are conservatively invalidated at the boundary.
- Source-informed send request variant documented separately from sent-list
  pagination on the shared upstream URL, with validated OpenAPI parity.
- Original loopback fault proofs, four-account full-payload workload and optional
  inert same-byte Chromium/apix comparison. Live form/acknowledgement compatibility
  and the one-recipient manual test remain separately approved future work.

## 0.4.5 - Recipient and mailbox coverage

Local-first extension in the 0.4 PR; no sending or publication.

- Bounded group-choice discovery and account/type/selection-bound references,
  fixed nonzero-group forms and isolated cache keys. Populated subgroup dispatch
  is offline-qualified only; virtual classes remain disabled.
- Preserve the observed unnamed hidden recipient as `label=None`; report a
  class-unavailable notice as a typed capability error instead of an empty list.
- Sent content with absent correspondent metadata and ordered individual read
  receipts. No invented addressee, ID or aggregate timestamp; bounded whole results.
- Four-account ordinary discovery adds independently checked received pagination,
  five named recipient types, anonymous targets, empty group options and sent
  content. Apix capability differences are classified rather than inherited.
- Original failure regressions, maximum receipt/body workloads and private
  Chromium expectations replayed against installed artifacts. Wider layouts,
  explicit empty recipients and populated subgroup semantics remain pending.

## 0.4.4 - Notification and checkpoint primitives

Local-first; no publication, sending or consumer migration. Read-once behavior
is qualified offline only and excluded from routine live checks.

- Typed token-scoped notification counts and three-string recent-event records,
  preserving event order/duplicates without library seen state or hashes.
- Explicitly consenting, uncached one-attempt consumption with mandatory durable
  encoded-response handoff before MIME/content decoding or parsing.
- Joined checkpoint ownership across receipt-boundary cancellation, repeated
  cancellation, operation deadline and service close. A finite cooperative
  checkpoint interval and redacted unknown-acknowledgement `CheckpointError`.
- Versioned private response envelopes and zero-network local decoding for
  consumer-owned serialization/recovery. No spool/state format is invented.
- Conservative original event layouts and real filesystem checkpoint/restart
  proofs; cross-process transactions and persisted hash compatibility remain P8.
- Correct later provenance labels: external apix metadata advertises MIT while
  its bundled license is GPLv3. No external implementation or fixtures copied.

## 0.4.3 - Bounded attachment streams

Local-first; no sending, publication or consumer filesystem changes.

- Single-owner context-managed streams, credential-free validated signed
  destinations, shared request/byte/deadline budgets and joined cancellation.
- Bounded 64 KiB chunks, 50 MiB ceiling, no cache/replay/resume/redirect following
  and clean-EOF completion rather than implicit successful partial output.
- Independent encoding regressions and mixed saturation/maximum-file proofs;
  one installed live 930,056-byte received attachment streamed without saving it.
  Broader file/handler/effect variants remain pending.

## 0.4.2 - Message content and inert attachments

Local-first feature release; no downloads, sending or publication.

- Typed full plain-text content, civil send/read timestamps and account/folder/
  message-bound attachment references with untrusted displayed filenames.
- `message_content()` requires explicit `allow_mark_read=True` for received
  opens. Potential read effects invalidate cached received summaries even when
  the open fails. No automatic content replay or hidden aiohttp GET retry.
- Bounded body/file metadata, strict reference and layout validation, shared
  isolation, traffic, parsing, coalescing and cancellation boundaries.
- Independent original fixtures and regressions for the observed separate read
  receipt table and page comments. Populated sent content, attachment metadata
  and richer layouts remain live-unqualified; see [VERIFICATION.md](VERIFICATION.md).

## 0.4.1 - Recipient discovery

Local-first feature release; not published to PyPI. No send operation is enabled.

- Typed account-bound group and recipient references, displayed group labels,
  availability/subgroup metadata and ID-bearing recipient collections.
- `recipient_groups()` and `recipients(group)` use shared traffic, parsing and
  caching boundaries. Selection-view GET/POST requests are never replayed.
- Named selector tokens are preserved; distinct IDs with the same name cannot
  overwrite each other. Label/checkbox/value linkage and cardinality are checked.
- Explicit pre-I/O rejection of foreign/injected references and the unsupported
  subgroup selector. Unknown/empty layouts fail rather than silently returning
  an empty collection.
- Bounded one-login capture, public installed smoke and identical-byte apix and
  independent Chromium replay. Eight group types and three populated simple
  lookup types were observed; hierarchy, empty layouts and other roles remain
  pending.

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
