# TODO

## Goal

Replace `librus-apix` in [librus-mcp](https://github.com/krzysztofbury/librus-mcp)
with this independently implemented, MIT-licensed library, published on PyPI,
while preserving the MCP v1.7.0 public contract. The library gives MCP a small,
typed async API over several independent Librus logins with shared, bounded
traffic. MCP chooses accounts, combines results and owns its tools and state.

Rules that hold for every release:

- 0.x releases are local-first. PyPI publication and its automation start at
  `1.0.0rc1`.
- Ordinary tests and CI stay offline. Live checks need explicit authorization
  and follow the workflow in [CONTRIBUTING.md](CONTRIBUTING.md#live-verification).
  The scheduled credentialed CI (P6-live) is planned, not running.
- A family is "verified" only after a live page from the current build has been
  checked. Record missing access as pending, never as passed.
- Consumer (`librus-mcp`) changes are a separately authorized task.

## Releases

| Version | Scope | State |
| --- | --- | --- |
| `0.1.0` | Account service, login, identity, profile, scheduler, budgets | Done |
| `0.2.0` | Grades: summaries, records, views, windows | Done |
| `0.3.0` | Attendance, timetable, announcements, agenda, homework, completed lessons; behaviour-note decision | Done, with the gaps below |
| `0.4.0` | Received/sent message lists and bounded continuation | Done locally, with message-layout gaps below |
| `0.4.1` | Recipient groups and recipients | Done locally for observed simple groups; hierarchy/empty-list gaps remain |
| `0.4.2` | Full message content, explicit read side effects, attachment metadata | Planned |
| `0.4.3` | Bounded attachment streams | Planned |
| `0.4.4` | Notification/checkpoint primitives | Planned |
| Sending (version TBD) | Validated one-attempt delivery | Plan and approve before implementation |
| `1.0.0rc1` | Complete MCP replacement candidate on PyPI, consumer branch qualified | Planned |
| `1.0.0` | Stable API, backward-compatible MCP 1.x backend cutover | Planned |
| MCP `2.0.0` | Consumer modernization (P9, ownership map A01-A18) | Separate |

P0-P9 below are the detailed acceptance checklist for 1.0. Each release
completes their requirements for the operations it enables. Live evidence for
each release is in [VERIFICATION.md](VERIFICATION.md).

### 0.3.0 follow-ups

- [ ] Completed lessons: verify a populated page and pagination live on an
  account whose school has the view enabled. All four available logins show it
  disabled.
- [ ] Behaviour notes: implement the public read once a populated page is
  observed ([decision](contracts/behaviour-notes.md)).
- [ ] Grades page observation card ("Karta spostrzeżeń", formative assessments):
  design a typed read. It is shown on both observed students' pages.
- [ ] Broaden coverage: other schools and roles, populated last-login views,
  custom attendance types, full-year subject-frequency resolution, parallel
  group lessons in the timetable, empty and rich announcement layouts, and
  populated descriptive grades and publications.
- [ ] Homework windows longer than one month: decide whether the library should
  split them into monthly requests or leave that to the consumer.

### 0.4.x - Separate communication features

- [x] 0.4.0: received/sent message lists, bounded pagination and source-bound
  references. Keep message bodies out of list retrieval. Installed live smoke
  and same-byte Chromium/apix replay completed on one login. Populated sent
  rows, multi-page metadata, attachment flags, other roles and the newer mailbox
  layout remain live-unqualified; original offline proofs are not live evidence.
- [x] 0.4.1: named recipient-group discovery and ID-bearing simple-group lookup.
  Installed live smoke covered tutor, teachers and school office; Chromium/apix
  replay agreed. Empty lists, subgroup/virtual-class discovery, other groups and
  roles remain pending. Details: [contracts/recipients.md](contracts/recipients.md).
- [ ] 0.4.2: full-message content and attachment metadata. Audit mark-read effects
  before enabling any content read; use a separately approved message selection.
- [ ] 0.4.3: credential-free bounded download streams, with the
  MCP atomic-publication integration and cancellation proof from P4.
- [ ] 0.4.4: the read-once schedule/checkpoint interface, and adapting notification
  records while MCP keeps its seen state, hashes, replay and migrations.
- [ ] Sending (version TBD): approve the plan in
  [contracts/messages.md](contracts/messages.md#featureversion-sequence) before
  implementing validated single-attempt sending with typed unknown-delivery results, plus
  MCP confirmation and token integration. Exercise offline only; never widen the
  daily check to sends, mark-read content or event consumption.
- [ ] Library and consumer regression evidence for these paths, exposing only
  public supported APIs to the adapter.

Each version is independently qualified and packaged locally. No sending or
live read-once operation is authorized by this sequence. Consumer migration,
credentialed CI and publication keep their separate approval gates.

### 1.0.0rc1 - Complete replacement qualification

- [ ] Finish P8 for every required consumer operation and remove `librus-apix`
  imports, private patches, duplicated recovery and obsolete dependencies in the
  migration branch. Keep the notification storage and file-publication owners.
- [ ] Complete the R01-R17 proof map, the declared Python/platform matrix,
  installed-library and MCP stdio checks, and representative P6 comparisons with
  numeric acceptance thresholds.
- [ ] Reconcile the notes gap explicitly. No supported operation may silently
  disappear; an unavailable feature is a recorded, approved default-off gap.
- [ ] Publish the candidate and qualify the consumer against that exact PyPI
  artifact, including existing state and spool readability and downgrade.
- [ ] Authorized account-type live checks, API and migration docs, release notes,
  dependency review and a rollback procedure.

### 1.0.0 - Stable API and consumer cutover

- [ ] Freeze and document the supported API, limits, account ownership, error
  and capability semantics, and compatibility policy.
- [ ] Publish the final artifact and rerun installed acceptance against it before
  releasing the consumer.
- [ ] Release a backward-compatible MCP 1.x pinned to the tested library, and
  verify its public `uvx` installation, dependency graph, CLI and contract.

### MCP 2.0.0 - Separate consumer modernization

- [ ] Complete ownership-map items A01-A18 in consumer PRs (typed wire contracts,
  deprecated-tool removal, packaging, configuration and state migration,
  attachment resources), released as one documented major version.
- [ ] Change the library version only when its own contract changes.

## Architecture and ownership

Proposed direction: async-first client, one HTTP stack, pure validated parsers,
and typed domain results. Use verified JSON endpoints where they cover the
contract; keep narrowly scoped HTML adapters for missing fields and operations.

| Concern | Final owner |
| --- | --- |
| Account credentials/configuration, aliases, feature flags | MCP |
| Session lifecycle, authentication, scoped cookies, transport budgets | Library |
| Shared rate/burst/concurrency/queue limits across independent account clients | Library service, reused across MCP calls |
| Choosing logins, combining overlapping results, and summary generation | MCP |
| Retry classification, bounded reauthentication, account/operation cooldown machinery | Library, with public policy settings supplied by MCP |
| Endpoint capabilities, JSON/HTML parsing, typed domain data, pagination, reference caches | Library |
| Requested-category orchestration and notification diff/seen-state policy | MCP, using public library operations |
| Durable schedule checkpoint storage, hashes, process locks, state migrations | MCP; library guarantees the checkpoint handoff boundary |
| Attachment authorization and bounded byte streaming | Library |
| Download directory, safe temporary files, atomic non-overwriting publication | MCP |
| Message send transport and typed delivery outcome | Library |
| Send confirmation tokens and permission to invoke a write | MCP |
| Legacy field names, Polish-label detail maps, ratio/percentage conversion, MCP schemas | MCP adapter |

During migration, keep existing safeguards until the replacement owner is
proven. Retire duplicate retry/cooldown logic in the same slice that enables
the library policy; nested recovery must not multiply login or send attempts.

## P0 - Contract and provenance foundation

P0-P9 are work packages shared by the release slices above, not an instruction
to finish every domain model before the first endpoint or to wait until P6/P7
   to test early useful deliveries. Publish to PyPI starting at `1.0.0rc1`.

Dependencies: none. Regression coverage: R01-R17 inventory.

- [x] Record independent implementation provenance and dependency licenses.
  Treat external implementations as research references, not material to copy.
  Retain consumer fixtures/tests in their existing repository; write new library
  fixtures independently. Do not claim this source-informed effort is clean-room.
- [ ] Decide distribution `librus-python-api` and import `librus_python_api`;
  confirm PyPI availability/ownership before release. Do not shadow `librus`,
  `librus_apix`, or `src`, and do not depend on upstream as a hidden fallback.
  Status: names decided and used; PyPI ownership is confirmed in P7.
- [x] Establish `src/librus_python_api/`, `pyproject.toml`, MIT SPDX metadata,
  bundled license, `py.typed`, and a single package-version source. Select and
  test supported Python versions; Python 3.14 compatibility is mandatory for
  the consumer. Claim older-version support only if exercised in the declared
  verification matrix.
  Verified on Linux with Python 3.13 and 3.14, from source and installed
  artifacts, locally and in GitHub CI. Other platforms are tracked in P6.
- [x] Choose one async transport after a small lifecycle/cookie/cancellation
  spike. Prefer evaluating `aiohttp`, already used by the consumer; do not add
  parallel `requests` and async implementations by default.
  Selected `aiohttp` after a loopback experiment, now retired in favor of real
  transport/service tests. The 0.1.0 account
  transport and login/identity network paths are implemented and tested offline.
- [x] Define public async client ownership, `aclose`/context-manager behavior,
  explicit limits/proxy/TLS configuration, and an injectable transport boundary.
  Construction/import must do no network I/O or implicit environment discovery.
- [x] Design one service-level lifecycle for all consumer accounts/tools, with
  account-scoped typed clients. MCP selects logins, operations, date ranges,
  and freshness and combines their results; the service handles scheduling and
  shared budgets. No summary/batch endpoint, private patches, or manual cookie
  wiring is required. Parent and student logins remain independent contexts.
- [ ] Create a per-operation contract matrix: account types, source endpoint,
  requested fields, result types, capability status, pagination, side effects,
  retry safety, and evidence confidence. Include every row in P3-P5.
  Status: every enabled read has its route, side effect, retry safety and
   evidence in `config.py` and the OpenAPI file; the P4-P5 rows come with 0.4.x.
- [x] Keep upstream routes centralized in `config.py` and maintain importable
  OpenAPI YAML for every enabled operation, including raw HTML/form contracts.
  Validate method/path/operation/policy parity offline and document fixture
   provenance and live gaps. 30 operations, checked by `tests/test_contracts.py`.
- [ ] Freeze the consumer's current MCP schema/annotation snapshot and document
  adapters for missing versus null fields, detail labels, default dates,
  `sort_by` filtering, string IDs, and legacy list/map output shapes.
- [ ] Use ownership-map A01-A08 to design clean library contracts before they
  become public. Track extraction of each existing consumer responsibility
  against that map; avoid building a second copy in MCP's 2.0 work.
- [x] Establish development tooling and CI: locked setup, Ruff, strict typing,
  offline tests, package build, and installed-wheel checks. Document real
  commands in CONTRIBUTING once the tools exist. GitHub CI additionally qualifies
  installed sdists, workflow syntax, complete-history secrets, and locked
  runtime/development dependency audits. Publishing and credentialed CI are separate.

Exit: an installable independent skeleton, reviewed contracts, and runnable
offline checks. No published claim of functional Librus support yet.

## P1 - Typed domain and failure contracts

Dependencies: P0.

- [ ] Define immutable domain records for identity, grades, attendance, lessons,
  agenda, homework, announcements, messages, recipients, attachments, and notes.
  Keep MCP/Pydantic wire models out of the library API. Prefer typed dataclasses
  with explicit runtime validation at parse boundaries; document serialization.
  Status: done for every 0.1-0.3 family, message summaries and simple recipient
  discovery; content, attachments and notes are pending.
- [ ] Define typed page results with items, continuation, truncation reason,
  source identity, and detected-change information. Never imply that an offset
  cursor freezes upstream data. Bind continuation to account/query/source.
  Status: completed lessons and messages have bound cursors and fingerprints;
  message batches include seen IDs and explicit truncation reasons.
- [ ] Normalize IDs without conflating distinct sources: retain opaque IDs where
  evidenced, distinguish display IDs from valid legacy detail references, and
  reject URL/path injection. Numeric legacy routes remain strictly numeric.
  Status: done for every enabled route (numeric references, account-bound
  `SchoolReference` and folder/account-bound numeric `MessageReference`).
- [ ] Model empty success, unsupported capability, unpublished data, permission
  denial, incomplete data, and parse failure separately. Required-field failures
  must not silently become `[]`, zero, or a fabricated record.
  Status: empty markers, `ViewDisabledError`, `UnsupportedCapabilityError`,
  `AccessDeniedError`, `LimitError` and `ParseError` are distinct; unpublished
  data (for example an unpublished timetable) is not modelled yet.
- [x] Define account provenance, observation times, freshness, completeness, and
  typed operation failures. An account failure must not invalidate another's
  session/results; MCP owns partial-summary policy and cross-account merging.
- [x] Define typed exceptions for invalid input, rejected credentials, required
  account action/captcha, session expiry, access denial, throttling, maintenance,
  connection/timeout, response limits, parsing, and uncertain delivery.
  Error messages and attached diagnostics must exclude secret/raw response data.
- [ ] Specify date-only values, school timezone (`Europe/Warsaw`), nullable fields,
  raw grade strings, missing grades, and explicit attendance units. Preserve
  school-provided averages where available; derived averages need documented
  weighting and grade-symbol rules, not assumptions from another school.
  Status: civil dates and local clocks are never converted, raw grades and
  school averages are kept, and ratios are explicit. Message timestamps retain
  school wall time, raw displayed text and `Europe/Warsaw`, without guessing an
  offset or DST fold.
- [ ] Start with `scope`, typed detail/event references, integer calendar inputs,
  normalized field names, and ID-bearing record collections. Prefer an explicit
  ratio domain type; keep presentation conversion in MCP. Support A01-A08
  without inheriting legacy tool names or dynamic display-name dictionaries.
  Status: typed references, integer calendar inputs, ID-bearing collections and
  `FrequencyMeasure` exist; `scope` is not implemented.

Exit: valid and invalid independent examples exercise actual validation, and
the proposed records can be mapped to existing MCP outputs without data loss.

## P2 - Session, transport, and authentication

Dependencies: P0-P1. Regression requirements: R01-R04, R10, R17.

Scheduler progress: global/per-account active and queue limits, shared rate/burst
admission, round-robin fairness, service pauses, shared request/deadline budgets,
and cancellation/close ownership are implemented and tested offline. Every enabled
0.1.0 authentication/identity request passes through this boundary. Remaining
messaging/page/capability requirements below are extended with later releases;
their broad checkboxes are not blanket claims from the identity slice.

- [ ] Use one authenticated session/cookie jar per configured login, including
  separate student and parent logins for the same student. Confirm expected
  identity without using student identity as the cache/security key. Isolate
  messaging session state too. Multi-child switching inside one login is not
  assumed or required for the initial four-login use case.
  Status: ordinary account isolation verified live on four logins; message-list
  isolation exercised offline on four independent full mailboxes. Message live
  qualification covers one login only.
- [x] Implement explicit session ownership and deterministic resource cleanup.
  Public injection must not require consumers to replace `_session` or clone
  private fields. Preserve all cookie restrictions and duplicate names.
- [x] Independently validate the current login handshake, bounded redirect
  allowlist, proxy behavior, and authenticated terminal state. Do not reuse the
  obsolete password-grant path solely because historical packages used it.
- [x] Coalesce concurrent authentication; allow at most one reauthentication for
  a proven safe operation. Distinguish bad credentials, expired session,
  persistent endpoint denial, maintenance, and confirmed throttling. Apply
  cooldowns once at the library owner boundary, with consumer-equivalent defaults.
- [x] Recognize unsupported interactive authentication as an explicit outcome.
  Do not loop, mislabel it as a parser failure, or promise CAPTCHA/2FA support.
- [x] Enforce connection/read and whole-operation deadlines, including queue
  wait, redirects, authentication recovery, body streaming, and pagination.
  A slow-drip response must not run indefinitely by resetting an idle timeout.
- [ ] Bound bytes before parsing for HTML/JSON and attachments. Cover absent or
  misleading Content-Length, chunked bodies, decompression, cumulative redirect
  bodies, malformed encodings, and cancellation while waiting for bytes.
  Status: done for HTML and JSON; attachment streams come with 0.4.3.
- [x] Bound parser CPU/memory and measure event-loop responsiveness on maximum
  accepted bodies. An asyncio deadline cannot preempt synchronous parsing;
  if parsing is offloaded, bound workers and account for their actual completion
  without letting them mutate session state after cancellation.
- [x] Bound global and per-account active requests AND queued tasks. Share the
  global budget across clients without sharing authentication state. Decide
  which proven-safe reads may overlap; serialize session-changing operations.
- [x] Enforce shared request rate and burst limits in addition to concurrency.
  Count login steps, redirects, retries, bootstraps, lookups, and page reads at
  dispatch. Use fair admission, bounded waits, and service-wide backoff where
  appropriate. Test that multiple account clients cannot multiply the budget.
- [x] Set explicit service account/queue limits and per-operation attempt/page/
  byte/deadline budgets with conservative defaults. Allow MCP to share a total
  retrieval budget across its calls. Exhaustion stops new dispatch and returns
  a typed incomplete/limit result. No Librus-approved rate is currently known.
- [x] Coalesce identical safe in-flight reads within account/query/session scope;
  reuse sessions and reference caches across summaries. Define waiter cancellation
  and freshness behavior; never share account data or coalesce side-effecting work.
- [x] Classify retries by operation semantics, not GET/POST. Bounded backoff and
  Retry-After handling apply only to safe retryable operations. Never replay a
  send or read-once event request after an ambiguous result.
  Retry safety is per endpoint, and `Endpoint` rejects any route that has a side
  effect yet is marked retry-safe.
- [x] Prove cancellation closes/releases resources and cannot leave requests
  mutating a session later. Do not remove MCP's thread-worker protections before
  the corresponding paths use the new native async implementation.
- [x] Provide redacted diagnostics: endpoint class, status, elapsed time, counts,
  error kind. No credential/token repr, response body excerpts, or signed URLs.

Exit: a local HTTP fixture server proves isolation, lifecycle, bounded work,
denial/cooldown behavior, resource release, and redaction through the public API.

## P3 - Read-only vertical slices and parser coverage

Dependencies: P1-P2. Regression requirements: R05-R06, R13-R16.

The matrix is a candidate implementation order, not a claim that JSON supplies
all fields. Each slice needs independently authored populated, empty, malformed,
and relevant account-variant fixtures before its adapter becomes the default.

| Slice | Consumer operations | Candidate source and parity risks |
| --- | --- | --- |
| Identity | `get_student_information`; live doctor profile read | Evaluate gateway identity/class/school/lucky-number reads; retain HTML for missing class-register number or other fields. Distinguish login owner from student and today's lucky number from another day. |
| Grades | `get_grades`, `get_grades_window`, `get_final_grades` | Evaluate JSON grades/categories/comments plus HTML summaries where needed. Preserve semester grouping, GPA, descriptive values, predicted/final distinctions, merged behaviour rows, and linkless descriptive grades. |
| Attendance | `get_attendance`, window/detail, overall/subject frequency | Evaluate records plus type/lesson/subject lookups. Preserve detail references and raw labels; resolve custom types and units explicitly. |
| Timetable | `get_timetable` | Evaluate gateway nested period slots and evidenced HTML variants. Preserve all parallel groups, substitutions, cancellations, times, breaks, week selection, and unpublished/account-specific status. |
| Agenda/homework | `get_schedule`, detail, `get_homework`, detail | Verify agenda versus assignment sources, date windows, descriptions, subjects, categories, and legacy references; do not equate similarly named endpoints. |
| Announcements | `get_announcements` | Validate full text, author, date, IDs, and account coverage; a JSON endpoint with missing author is not automatically equivalent. |
| Completed lessons | list and bounded-page tools | Retain an independently implemented HTML route unless JSON parity is demonstrated for topic, attendance reference, teacher, and pagination. |
| Message lists | received/sent/page/all-pages/bounded `get_messages` | Assess legacy and separate JSON subsystems independently. Prove sent-folder support, ID mapping, unread status, and stable source selection; do not eagerly fetch bodies. |

- [x] Implement the identity slice first, including an MCP adapter experiment
  and a fixture-server integration test. Record request count, session reuse,
  and exact field coverage before widening scope.
- [ ] Complete the remaining slices using separate fetching and pure parsing.
  Parse each response once and return pagination metadata with its rows.
  Status: all slices except message lists are done and verified live
  (VERIFICATION.md).
- [x] For HTML, locate semantic page/table markers and map verified headers.
  Handle documented span variants explicitly; reject ambiguous layouts. Avoid
  whole-document positional XPath and guessing empty success from missing tables.
- [x] For JSON, validate envelopes, nested references, required values, and
  endpoint-specific variants. Bound IDs, list sizes, nesting/decoding work;
  preserve justified optional/unknown fields without silently skipping bad rows.
- [x] Implement bounded page/offset continuation and ID deduplication. Cover page
  zero, repeated/clamped pages, overlaps, short/oversized pages, and empty ranges.
  Cursor translation may require retaining the legacy endpoint during migration.
  Status: done for completed lessons and message lists; populated live message
  pagination remains a recorded coverage gate, not inferred from fixtures.
- [x] Support current scope/date filtering semantics. Label client-side filtering
  separately from upstream bounds; do not approximate `last_login` with a date
  window or lose events because authentication changed its reference point.
- [x] Fetch needed metadata in bounded bulk or deduplicated per-ID requests.
  Add per-account bounded TTL caches, invalidation on account/session changes,
  and explicit freshness rules. Do not cache changing attendance as reference data.
- [x] Define unknown attendance-type behavior using verified metadata. Never
  classify an unknown type as present or return 100% merely for lack of evidence.
- [x] Keep JSON-to-HTML fallback explicit, capability-scoped, and budgeted. A
  schema failure must surface; it must not silently change data source or IDs.
  There is no fallback: each read has one source and its failures are typed.

Exit: all enabled ordinary reads map to the existing MCP contract; parser and
transport tests protect real behavior rather than supplying prebuilt results.

## P4 - Content, attachments, and experimental notes

Dependencies: P3 message/grade foundations. Requirements: R10-R11, R14.

- [ ] Audit message-body and attachment-list reads for mark-read effects on each
  backend. Provide explicit operation metadata and document effects in MCP;
  any annotation correction needs deliberate consumer contract review.
- [ ] Implement full-message parsing and bounded content decoding. Distinguish
  truncated previews from complete bodies; preserve formatting/links as data,
  do not execute content or fetch embedded resources, and disable unsafe XML
  features where that envelope is independently confirmed.
- [ ] Provide typed attachment references and an async bounded stream. Preserve
  exact-host/path/scheme/port validation and a cookie-free signed-download client.
  Do not assume new messaging IDs can authorize legacy sandbox downloads.
- [ ] Integrate streaming with MCP's existing safe filename, temporary-file, byte
  cap, and atomic publication policy. Exercise cancellation before/after the
  final byte and around publication; a canceled result must not publish later.
- [ ] Implement notes only from independently validated shapes. Keep the MCP gate
  off and the feature explicitly experimental while a populated anonymized
  fixture is unavailable. A third-party inferred JSON shape is not verification.

Exit: attachment safety holds across the library/consumer boundary; content
side effects are explicit. The notes evidence gap is recorded, not disguised
as completed parser validation.

## P5 - Read-once notifications and message delivery

Dependencies: P2-P4. Requirements: R07-R09, R12.

- [ ] Specify an awaitable checkpoint callback for the read-once schedule
  operation. MCP supplies persistence; the library must await durable handoff of
  the complete validated batch before optional enrichment, filtering, or normal
  cancellation propagation can discard the result. Define failure ownership
  and a bounded cancellation-deferral interval explicitly.
- [ ] Document the remaining loss window before receipt/parsing/checkpoint;
  no exactly-once promise. Drain already persisted events before another live
  consume. Preserve overflow batches for later bounded processing.
- [ ] Keep notification category selection, first-run semantics, deduplication,
  and persisted seen IDs in MCP. Use library records through explicit adapters
  instead of upstream `NotificationIds`, `RecentEvent`, and private diff parsers.
- [ ] Preserve canonical schedule identities, hashes, date/text normalization,
  pending-spool replay, and unrequested-category state. New gateway IDs need an
  explicit migration map/versioning strategy; do not silently reset history.
- [ ] Exercise read-once receipt, checkpoint failure, cancellation, failed seen
  saves, restart/replay, and competing consumers with a local fixture server
  plus real temporary filesystem state. Never test by live double-fetching.
- [ ] Implement recipient discovery and a typed send result. Validate unique
  recipient references and payload bounds before I/O. Do not expose arbitrary
  authenticated URLs as a public escape hatch.
- [ ] Preserve at-most-one send attempt and distinguish rejection from unknown
  delivery after timeout/cancellation/unrecognized response. Do not retry or
  switch backend after possible acceptance. Keep preview/token handling in MCP.
- [ ] Verify confirmation expiration, payload binding, token reuse rejection,
  and uncertain-delivery MCP error mapping with the new library installed.

Exit: replay and delivery semantics survive end-to-end fault injection; no
live writes or read-once calls are necessary for routine CI verification.

## P6 - Performance and regression acceptance

Dependencies: each completed slice; full run before P8.

- [ ] Maintain a requirement-to-proof map for R01-R17. Library tests own transport,
  parsing, and budgets; MCP tests own wire serialization, state transactions,
  confirmation, and publication. Rework old private-internal mocks only when
  stronger public-boundary proof replaces their actual invariant.
- [ ] Add representative fixture-server workloads: empty/small/full bounded
  mailboxes, changing pages, many unique lessons, warm/cold caches, slow bodies,
  multiple accounts, and cancellation under saturated concurrency.
- [ ] Exercise the installed library's public multi-account service with real
  local HTTP, and exercise MCP stdio through its adapter to that service. Cover
  four independent student/parent logins, overlapping records with different
  permissions, a failed account, concurrent tool requests, shared request-rate
  caps, cancellation, and budget exhaustion without mocking away retrieval.
- [ ] Compare old/new request counts, connection reuse, elapsed-time distribution,
  peak memory, and active/queued work. Set numeric acceptance thresholds after
  recording baseline measurements. A quiet live account is not a load test.
- [x] Prove cache capacity, TTL expiry, invalidation, and account isolation.
  Verify a warm cache skips metadata requests but still fetches fresh records.
- [ ] Use targeted mutation/property tests for critical guards: account isolation,
  bounded queues/bodies/pages, send non-retry, checkpoint ordering, and redirect
  rejection. Do not use test count or an untriaged mutation score as acceptance.
- [ ] Run strict typing, lint, formatting, dependency/security checks, and tests
  under the declared Python matrix. Test installed artifacts on Linux, macOS,
  and Windows, including timezone availability and stream/file integration.

Exit: documented representative measurements and no unresolved safety regression.
No performance improvement is claimed until this evidence exists.

### P6-live - Daily credentialed compatibility check

Dependencies: P2 and the P3 identity slice; run alongside later development.
Supporting local operating contract: `docs/SERVICE_REQUIREMENTS.md`,
"Daily live CI" section. Required release checks are listed below.

- [ ] Add an isolated daily/manual workflow for trusted default-branch code,
  using owner-provided environment secrets and an explicitly selected account
  set. Keep PR CI offline; restrict manual refs and secret access to trusted code.
- [ ] Use one Linux/Python job with a shared concurrency group, finite timeout,
  no matrix multiplication, and no automatic reruns. Enable unattended scheduling
  after one-time configuration, independently of PyPI publish approval.
- [ ] Install the tested wheel, log in once per account, verify authenticated
  identity, and perform a small allowlist of bounded ordinary reads. Apply the
  real scheduler with a strict total request budget and stop on service/auth errors.
- [ ] Check schemas and report populated versus empty coverage. Exclude sends,
  read-once events, mark-read operations, attachments, and production state writes.
  Check the effect of sign-ins on `last_login` before using production accounts.
- [ ] Report only redacted status, version/commit, request counts, timings, and
  coverage status. Suppress live-object assertion dumps and raw network logs;
  never publish response bodies or secrets as artifacts.
- [ ] Make missing secrets, unexecuted checks, and failed live expectations
  actionable non-successes in this workflow. Configure failure notifications
  and a last-run timestamp so a stale success is not mistaken for current health.
- [ ] Prove workflow/report redaction and allowed-operation enforcement offline
  before enabling credentials. Treat daily live checks as drift detection;
  keep populated parser/failure/load coverage in deterministic offline E2E tests.

Exit: a scheduled run performs real authentication and bounded reads, records
redacted evidence, and signals failure without unsafe retries or secret exposure.

## P7 - PyPI release pipeline

Dependencies: P0 packaging; PyPI publication starts at `1.0.0rc1`.
Before that candidate, verify exact local wheel/sdist artifacts and the local
consumer adapter without requiring publishing automation or a PyPI installation.

- [ ] Configure PyPI/TestPyPI project ownership and a GitHub Trusted Publisher
  tied to the exact repository, workflow, and protected release environment.
  Keep publish credentials out of build/test jobs; preserve manual approval.
- [ ] Build wheel and sdist from a verified tag matching package metadata and
  event commit. Verify MIT license content, declared runtime dependencies,
  Python requirements, public exports, and `py.typed` in installed artifacts.
- [ ] Build once, record distribution checksums, and publish those verified bytes
  after tests. Pin third-party Actions by SHA and document release recovery.
- [ ] Test a clean install outside the checkout, including import, public async
  client lifecycle, and a fixture-server read. Test both locked and newest
  permitted dependencies; schedule dependency-drift checks.
- [ ] Publish `1.0.0rc1` and document its coverage/limitations. Prove the consumer
  adapter against that PyPI artifact before the complete cutover; earlier 0.x
  adapter qualification uses exact local built artifacts.
  Use separate library/consumer versions and changelogs.
- [ ] Publish the migration-ready library before releasing the consumer that
  requires it. Prefer an exact tested dependency pin initially; no Git/path
  dependencies in the production consumer release.
- [ ] Verify public PyPI version, wheel/sdist checksums, fresh resolver install,
  and downstream `uvx` startup. Do not infer publication from a local build.

Exit: independently installable public library with a reproducible release path.

## P8 - Consumer cutover and retirement

Dependencies: P3-P7 for the required feature set.

- [ ] Add a small backend adapter behind `LibrusManager` without changing MCP
  tool signatures or replacing `server.py`. Select one backend per operation
  during development; never shadow-run real side-effecting calls.
- [ ] Reuse one library service for every account/tool in the MCP process so
  concurrent summary requests share the traffic budget. Document that separate
  processes/runners require coordination to enforce a combined budget.
- [ ] Migrate one family per reviewable slice. Authentication/session and retry
  policy must move coherently; do not shuttle flattened cookies between clients.
- [ ] Preserve MCP's 24 default/28 all-feature tool catalog, output schemas,
  text JSON and structuredContent, existing input validation, feature defaults,
  config sources, and legacy absent/null fields. Review any required change
  explicitly instead of refreshing the snapshot to hide a regression.
- [ ] Preserve grade/GPA grouping, timetable presentation, detail maps, frequency
  units, message/lesson cursors, notification first-run semantics, and all
  currently supported optional tools. Experimental notes remain default-off.
- [ ] Translate domain records explicitly: new `date`/enum/ID types must not
  accidentally pass through the old dataclass serializer with changed values.
- [ ] Replace imports from `librus_apix` in `src/librus_client.py`,
  `src/librus_optimizations.py`, `src/scraping.py`, and
  `src/notification_state.py`, including state DTO construction on restart.
- [ ] Remove private-session patching, upstream parser calls, redundant HTTP
  stacks, thread pools, response wrappers, and duplicate caches only after their
  replacement invariants pass. Keep notification persistence and download
  publication modules that still own application behavior.
- [ ] Remove `librus-apix` from the manifest/lock and prove its absence from the
  installed consumer dependency graph. Remove direct scraper/network dependencies
  only when no consumer-owned implementation still needs them.
- [ ] Run current MCP contract/runtime suites with the new backend and installed
  artifacts. Confirm old state and pending-spool data remain readable and that
  downgrading to the previous consumer release does not lose pending events.
- [ ] After explicit authorization and reconnection, run bounded live reads
  across supported account types. Record which responses are populated; do not
  treat empty results as parser coverage. No routine live sends/read-once reads.
- [ ] Release the consumer only after the exact library version is on PyPI and
  its complete required contract passes. Keep a tested previous-version pin and
  explicit downgrade instructions as rollback, not runtime fallback-on-error.
- [ ] Retain the consumer's existing GPL license unless a separate provenance
  and contributor review authorizes relicensing. Dependency replacement alone
  is not a license migration.

Exit: public `uvx librus-mcp` installation uses only supported library APIs,
without `librus-apix`, and preserves the established consumer contracts.

## P9 - Enable the separately released MCP 2.0 contract

Dependencies: P8 for rollout; A01-A08 library design starts in P0/P1.
This phase is coordinated work in `librus-mcp`, not library release scope.

- [ ] Use the ownership map to update MCP's 2.0 TODO with released library
  prerequisites and remaining consumer work. Do not mark a wire migration
  complete merely because a domain type is available.
- [ ] Expose the normalized records, collection envelopes, named units, `scope`,
  references, calendar inputs, and error mapping; publish explicit old/new tool
  examples, new schemas, and a compatibility/migration guide.
- [ ] Remove `all_pages` and the standalone read-once schedule tool only after
  bounded pagination and stateful notifications cover the replacement paths.
  Retain the library's underlying consume capability and checkpoint contract.
- [ ] Rename the consumer package and verify CLI routing. Reconcile the old
  `server:main` TODO wording with the current `cli:main` entry point before
  changing packaging. Evaluate mutation tooling against the resulting layout.
- [ ] Migrate explicit/XDG configuration and retire legacy state mirrors only
  after documented upgrade paths and collision/replay checks. The library
  must not inherit consumer file discovery or notification storage conventions.
- [ ] Evaluate MCP attachment resources using the library's bounded stream;
  maintain local publication/cancellation safety and agent-context byte limits.
- [ ] Publish and verify the consumer's major release independently. Keep the
  library version unchanged unless this work genuinely changes its own contract.

Exit: MCP 2.0 exposes the cleaner library capabilities, with no duplicated
transport/parsing implementations and documented breaking consumer changes.

## Deferred work

- Sync facade, persistent session export/import, extra account-management APIs,
  additional messaging folders, and wider endpoint coverage need demonstrated
  consumers before implementation. If session persistence is added, preserve
  full cookie restrictions and define secure storage ownership explicitly.
- Rust and a copied upstream compatibility namespace are outside this roadmap.
  MCP 2.0 rollout is tracked in P9, separately from the backend replacement.
- Populated behaviour-note evidence remains an explicit research dependency;
  it does not justify enabling the tool or claiming production readiness.
