# Changelog

## 1.0.1 (2026-10-06) - Bounded subject frequency and reliability fixes

Compatible patch release. The public library API is unchanged.

- Resolve subject-frequency lesson and subject names from the gateway `Lessons`
  and `Subjects` collections, read once per login session and cached for the
  existing one-hour TTL. A cold call now costs three requests regardless of how
  many lessons and subjects a student has. Before, it cost one request per unique
  lesson plus one per subject, which exceeded the default 32-request operation
  budget near 15 subjects and failed with `LIMIT`. References missing from a
  collection keep the strict per-reference routes. An unavailable, denied,
  oversized or malformed collection falls back to them; deadlines, budgets and
  cancellation still propagate.
- Report a published attachment as published when removing the private temporary
  name fails after the atomic link commit, instead of raising `STORAGE` for a
  complete file. The inert temporary file may remain.
- Wait up to one second, not 100 ms, for another process's SQLite write lock in
  ordinary store operations. Several local processes commonly share one store;
  final saves after upstream side effects keep their five-second wait.

## 1.0.0 (2026-10-05) - Stable native library API

Freeze the documented library API and compatibility policy for consumers moving
to native contracts. This is a library release, not proof of completed MCP 2.0
cutover or universal live-school compatibility. Existing school/layout limitations
and separately authorized live checks remain explicit. No live requests or
production-state migration occur during release qualification.

- Require sealed Windows disk qualification in addition to Linux/macOS release
  checks, on Python 3.13/3.14 with locked and newest permitted dependencies.
- Preserve explicit account keys, format-3 state and conservative UNKNOWN sending
  history. No automatic old-store import, silent notification reset or rollback.

- Support optional Windows disk workflows on fixed local NTFS: private protected
  inheritable ACLs, pinned directory/ancestor handles, cross-process notification
  locks and complete non-overwriting attachment publication by handle. Add explicit
  private attachment-directory preparation and Windows-only pywin32/tzdata runtime
  dependencies. Reject network namespaces, unsafe ACLs and reparse-point paths.

- Add compact, account-bound offline notification recovery status and pending-batch
  lookup. Discover original categories/backend/receipt, retained raw progress and
  uncertain consumption without remembered selections or implicit acknowledgement.

- Add a neutral offline notification bootstrap API for explicitly mapped baseline
  IDs and consumed historical events. Report unmapped IDs without writes; atomically
  stage bounded pending history with explicit missing provenance. Preserve restart,
  archive round-trip and acknowledgement without fabricating native metadata.

- Add explicit legacy/modern mailbox selection to durable notification workflows.
  Modern summaries use their own canonical ID domain; pending batches retain their
  original source across restart and archive import. Existing legacy IDs and
  format-3 state remain readable without reset or rewriting seen history.

## 1.0.0rc1 (2026-10-05) - Library-only release candidate

First candidate prepared for PyPI Trusted Publishing. The supported library API
is unchanged from 0.7.0; this is a beta prerelease, not stable 1.0 acceptance or
an MCP backend cutover.

- Add manual, approval-gated publishing with sealed wheel/sdist qualification on
  Linux/macOS and Python 3.13/3.14, using locked and newest permitted dependencies.
- Add public distribution checksum confirmation, installed runtime smokes, weekly
  dependency-drift checks and documented release recovery.
- Retain required application context keys and persistence/archive format 3.
  Older stores are refused without modification; automatic migration is absent.

MCP integration, durable-state migration/rollback and broader live qualification
remain unfinished. Behaviour notes and observation cards are not implemented;
some communication layouts and read-once operations remain unqualified. No live
Librus calls or message sends are part of release preparation or publishing.

## 0.7.0 (2026-10-05) - Application-keyed contexts and package usability

Pre-1.0 breaking changes: service construction now requires `context_key`, and
old persistent stores/notification archives need explicit migration outside this
release. See [the upgrade guide](contracts/account-context.md).

- Replace the public unkeyed login digest with domain-separated HMAC-SHA256 using
  a required application-owned 32-byte key. Password rotation remains stable;
  key changes deliberately change the namespace. No implicit key generation.
- Advance SQLite and notification archive formats to 3. Refuse older formats
  without reset or automatic migration, preserving old pending/UNKNOWN records.
- Remove Loguru from dependencies and replace the optional `loguru_sink` with
  standard-library `logging_sink`. The inspected MCP source and manifest do not
  use Loguru; custom diagnostic callbacks remain supported.
- Mark the package Beta with AsyncIO and POSIX/macOS classifiers. Document Linux
  qualification and the POSIX requirement for persistence/attachment publication;
  stores fail explicitly on unsupported platforms before creating files.
- Ship a lean sdist with runtime sources, build metadata and user documentation;
  exclude agent instructions, roadmap, capture scripts, tests and evidence logs.
  Check built archive contents and metadata in CI.
- Rewrite the README around installation, first requests, common tasks, error
  handling and upgrades. Execute its Python examples against offline HTTP fixtures.

No PyPI publication or live Librus access is included.

## 0.6.1 (2026-10-05) - Pre-1.0 readiness review

No public API, wire contract or storage format change. Offline only.

- Remove the unused `tenacity` runtime dependency.
- `publish_attachment` reports UNSUPPORTED_CAPABILITY on platforms without
  `os.O_DIRECTORY`/`os.O_NOFOLLOW` instead of failing with a raw AttributeError;
  directory-relative no-follow opens are its safety boundary (POSIX only).
- Remove the offline reference-client comparison scripts. Their recorded results
  stay in VERIFICATION.md and `release-evidence/`; the scripts remain in Git
  history. Documentation outside the validation records now calls that client
  "the reference client"; provenance is in VERIFICATION.md.
- Documentation: received-mailbox pagination evidence (observed live in 0.4.5)
  is no longer described as unqualified in the contract and OpenAPI note; API.md
  lists the attachment idle timeout and warns that `AccountContext.identifier` is
  an unsalted login-derived hash; README links are absolute so they work on PyPI.

## 0.6.0 (2026-10-04) - Native MCP 2.0 foundations

- Add `DetailField`/`DetailFieldKey` and stable-key `normalized_fields` to agenda,
  homework and attendance details. Preserve unknown/raw values and reject
  ambiguous labels before caching. No new upstream operation is introduced.
- Keep original detail constructor arguments and equality/hash semantics:
  derived normalized metadata defaults to an empty tuple for manually constructed
  results and does not participate in equality. Service results populate it.
- Target a direct native MCP 2.0 migration, replacing the planned intermediate
  MCP 1.x compatibility layer. Review all 18 consumer roadmap items and retain
  explicit durable-state migration, rollback and send-uncertainty safeguards.
- Add typed `HomeworkRangeRequest` and bounded `homework_range()` aggregation
  across disjoint monthly selections, under one total budget. Conflicting duplicate
  references and later failures produce errors, never partial cached success.
- Grade/attendance windows accept optional date boundaries and explicit upstream
  views, retain the selected view, and accept dates at most 370 days apart.
- Reject non-standard non-finite JSON constants and overflowing decoded numbers,
  including unknown fields. Four identity regressions fail before the correction.
- Extend modern sent/archive/zero-byte attachment publication proof offline.
- Record the MCP tool/type cutover matrix and Snyk-based security/architecture
  review. Populated notes, observation cards and further live qualification remain
  evidence-dependent; no consumer migration or new live access is included.

Compatibility: existing method calls and raw detail fields remain supported.
Dataclass serialization includes additive `normalized_fields` and window `view`
metadata; consumers needing exact wire schemas must project fields explicitly.
Window boundary annotations now allow `None` for new open-ended calls; existing
date-bounded calls still return their supplied dates. Non-finite JSON and
ambiguous detail labels now raise parse errors rather than accepting invalid
upstream data. This is a local-first release, not a PyPI publication.

## 0.5.0 (2026-10-04) - Modern live qualification

- Bounded server-selected numbered handoff namespaces, preserving exact origin,
  login, token, target/source and terminal checks without guessing or fallback.
- Identity-only bounded integer account-ID normalization before native owner/name
  comparison. Directory identifiers remain strict strings.
- Exact HTTP 201 JSON created/sent receipt acceptance, grounded in one separately
  approved dispatch and independent official-UI owner confirmation. Other positive
  hints remain UNKNOWN; no second send qualified this parser correction.
- Original wire/privacy/load/deadline/durable regressions and sanitized closed-scope
  evidence. No consumer migration, read-once consumption or publication.
- Same-PR continuation: optional atomic, non-overwriting local attachment file
  publication; modern mailbox pages and bounded continuation; consent-gated inert
  content/attachment metadata; ordinary school directory and virtual-query support.
  Source API live checks qualify only available inbox/outbox and directory branches.
  Final source, wheel and sdist qualification is recorded separately in
  `VERIFICATION.md`; download and receipt expansion is described below.
- Further same-PR expansion: explicit modern/archive attachment resolution and
  bounded credential-free streams; recipient read/null/unknown observations with
  unknown independent delivery status; plain/HTML/XML body decoding and inert
  withdrawn original metadata. Narrow live scopes qualify available mailbox
  layouts, a complete ordinary attachment and one consented mark-read transition.
  Unavailable directories/subgroups and unobserved archive/expanded receipt layouts
  remain explicit gates, without new sends or UNKNOWN history changes.
- Pre-merge review: recognize XML wrappers after a UTF-8 BOM or inert preamble,
  enforce their unique Content element and reject conflicting encoding declarations
  instead of silently corrupting text. Discovery accepts the explicitly supported
  combined parent/guardian type. Original HTTP regressions fail before these fixes.
  Malformed recipient-type values fail locally with `InvalidInputError` instead
  of leaking an untyped dictionary-key exception during send preparation.
- Synchronize README/TODO release status and OpenAPI capability/evidence notes;
  keep unavailable communication evidence tracked as C01-C05. Review is offline.

## 0.4.11 - Storage retention and communication review follow-ups

Offline-only S10(a-i), on a separate branch after the 0.4.10 merge.

- Explicit atomic `prune_seen` and `prune_send_history`, with no automatic age
  expiry. Uncertain/live sends, staged deliveries and reservations remain protected;
  accepted-send pruning needs explicit duplicate-risk opt-in. Retained raw replay
  can recover seen saturation without another consume; acknowledged raw prefix IDs
  remain protected until drain so archive imports preserve progress proof.
- Both SQLite schemas and neutral notification archives advance to version 2.
  Random durable per-store salts namespace persisted contexts, locks, raw digests
  and batches. Archive import validates then rebinds to the target salt. Version-1
  layouts refuse without reset or automatic migration; no production data changes.
- Exact modern-launch-to-native-login redirects report SESSION_EXPIRED. Every warm
  send freshly revalidates modern identity with one GET before its POST. Modern
  expiry/permission/parse failures clear only modern state, preserving valid legacy
  sessions. No modern read/send retry or replacement live authentication layout.
- `StaleCursorError` distinguishes detected mailbox/lesson continuation drift from
  malformed wire data. Full pager-less 50-row mailboxes refuse apparent completion.
  Unsupported attachment redirect shapes no longer install permission cooldown;
  foreign destinations and HTTP denials still fail closed. Origin, scheme and
  userinfo are checked before query, fragment, percent or backslash encoding, so
  a foreign destination is ACCESS_DENIED even when its shape is also unsupported.
- Paused attachment demand waits have an independent finite idle timeout (15 s
  default). Complete bounded send responses survive return-time deadline expiry;
  local receipt parsing has its own bounded deadline without granting more HTTP.
  External cancellation and incomplete-response UNKNOWN semantics remain intact.
- Original public-native loopback/SQLite/process/load and deterministic deadline
  regressions. Pre/post review is recorded in `contracts/review-followups.md`.
  MCP migration, live qualification, merge and publication remain separate gates.

## 0.4.10 - PR #13 review hardening

Fixes from an independent multi-agent review of the 0.4 series. Local-first;
no live Librus request, send or read-once consume was made.

- Legacy send acknowledgements tolerate the known legacy-module banner instead of
  reporting every send on a non-migrated account as UNKNOWN.
- Mid-page message cursors fingerprint row identities only, so a message opened
  (marked read) before resuming no longer raises a parse error.
- Final saves after an upstream side effect (read-once checkpoint, staged batch,
  acknowledgement, send outcome) wait up to `final_busy_timeout_seconds` (default
  5 s) for another context's SQLite write lock, instead of the 0.1 s default that
  could lose an already consumed read-once page.
- A post-claim send outcome save failure reports STORAGE, never LIMIT, which
  promises that no upstream work happened.
- Archive import rejects raw cursor progress past events missing from the seen
  set, and any progress without a known event total.
- The transport fails closed if aiohttp drops the private switch that prevents
  silent GET replays; transport close always closes every session.
- Capture scripts share a read-only transport base that refuses sends, modern
  authentication and read-once consumes, which bypass the per-request allowlist.
  Crosscheck expectation files are refused inside Git work trees, and their
  checks no longer rely on `assert`.
- New regression tests failed before each fix: send banner, read-state resume,
  real SQLite write-lock contention at post-consume and post-dispatch boundaries,
  import cursor tampering, concurrent same-login consume, capture refusals and
  official attachment destination rules.

## 0.4.9 - Optional notification persistence and replay

- Explicit native notification store/workflow with a private separate SQLite
  database, bounded POSIX process locks and no core/MCP storage dependency.
- Whole raw read-once envelopes commit before parsing; restart drains bounded
  local slices before another consume. Failed receipt/checkpoint keeps conservative
  uncertainty instead of replaying a potentially consumed upstream request.
- Durable batches require explicit delivery acknowledgement before atomically
  updating seen IDs/cursors. First-run/requested-category semantics and native
  canonical identities remain independent of MCP; delivery is at-least-once.
- Neutral exact-context/version-bound archive import/export into empty targets,
  retaining malformed raw bytes and rejecting inconsistent progress/delivery.
- Original real-SQLite/public-native loopback, process-loss/competition, cancellation,
  save-fault, capacity and representative load proofs. Existing send state remains
  unchanged; notification archives contain private data and are not encrypted.
- Modern authentication, broader coverage and live qualification move to the 0.5
  TODO. MCP migration, live operations, merge and publication remain separate gates.

## 0.4.8 - Optional durable send workflows

- Explicit optional SQLite store with private bounded files, versioned schema,
  cross-process transactions and cancellation-joined lifecycle, independent of MCP.
- Configured-login/backend/exact-submission-bound expiring confirmations, atomic
  single-use claims and durable outcomes. Persist hashes/status only, not message
  bodies, token plaintext, recipient labels, credentials or HTTP sessions.
- Claimed/unknown/accepted submissions block duplicate-preview/token bypass.
  Crash or final-save failure preserves uncertainty without replay or fallback.
- Original public legacy/modern loopback, competing-process, killed-sender,
  cancellation, fault, corruption, capacity and maximum-admission load proofs.
- MCP integration remains in its separate repository at backend migration time.
  Notification state/replay, manual reconciliation, live qualification and
  publication are not implemented or authorized by this increment.

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
  inert same-byte Chromium/reference-client comparison. Live form/acknowledgement compatibility
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
  content. The reference client capability differences are classified rather than inherited.
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
- Correct later provenance labels: the external reference client's metadata advertises MIT while
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
- Bounded one-login capture, public installed smoke and identical-byte reference-client and
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
  the reference client comparison and independent Chromium visible-field/reference/flag checks.
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
  (`tests/test_account_reads.py`). 32 duplicated per-family tests, the reference-client
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
- Installed numeric-grade comparison with the unmodified reference client completed under approved
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
