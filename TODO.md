# TODO

## Goal and baseline

Primary goal: a secure, economical async API through which MCP queries multiple
independent Librus logins and combines their results. Minimize upstream requests,
enforce shared traffic budgets, return validated types, and verify the actual
integration end to end, including
a small daily credentialed CI check. The work packages below define the public
acceptance criteria; supporting research in `docs/` is local and untracked.

Replace `librus-apix==1.5.2` in `librus-mcp` with an independently implemented,
MIT-licensed `librus-python-api` distributed through PyPI. Preserve the MCP
v1.7.0 public contract while removing its dependence on private upstream
sessions, parsers, and notification types.

Research date: 2026-09-29. The local `docs/ECOSYSTEM_REVIEW.md`
compares all seven requested packages and records regression requirements
R01-R17 with current consumer source/test owners. Research, repository
documentation, commit checks, and a local package foundation exist today.
The local-first 0.1.0 identity delivery is complete. Later operation families,
live qualification, publishing, and full consumer cutover below remain pending.

Current delivery: `0.1.0` packaging, typed route/error configuration,
OpenAPI catalogue tests and shared
request admission/budgets verified with a saturated four-account HTTP workload.
The native scope-preserving HTTP transport and evidence-labelled OpenAPI routes
are implemented. The public service, coalesced safe reads, account-scoped freshness,
authentication, typed identity/profile, bounded Tenacity recovery, and redacted
Loguru diagnostics are implemented and tested offline. Installed-artifact and
real MCP stdio adapter qualification are complete on Linux. See VERIFICATION.md
for measurements, exact proof commands, and explicit live/platform limitations.

**Local-first scope adjustment:** develop and verify `0.x` using local wheel/
sdist builds and offline runtime tests, including local `librus-mcp` integration.
PyPI publication and its CI automation are deferred until `1.0.0rc1`, not required
for the earlier local deliveries and not marked complete.
The daily credentialed workflow remains planned separately. No live verification
is authorized merely by documenting its future workflow.

Repository hygiene is configured separately from the library milestones:
pre-commit checks block common private files and scan staged secrets; manual
worktree/history scans are available. See CONTRIBUTING for hook installation.

The local `docs/MCP_OWNERSHIP_MAP.md` assigns all 18 current MCP
2.0 roadmap items and existing consumer extensions to their intended owners.
Library foundations should be built now; MCP's breaking interface changes
remain a separately released follow-up, not a prerequisite for replacement.

**Recommended first delivery:** package skeleton, transport and typed errors,
then a shared-budget multi-account service with authentication and student
information through a real consumer adapter and a local fixture server. Add
the daily live check once this slice can safely use configured test credentials.
Prove this slice before porting every endpoint. Ship centralized route metadata
and a matching OpenAPI YAML contract with each implemented operation, including
HTML scraping routes, evidence gaps, and explicit side effects.

## Versioned delivery plan

Versions below are planned release boundaries, not published packages. Group
related implementation, documentation, and verification into useful releases;
do not issue a version for each commit or checkbox. Each release should contain
multiple focused commits and can span several PRs. A larger cohesive release is
preferable to shipping disconnected foundations as separate versions.

P0-P9 below remain the detailed acceptance checklist. The version plan assigns
that work to releases; it does not replace the checklist or defer security,
typing, and E2E proof until the end. Complete each phase's requirements for the
operations enabled in that release, then extend them with later capabilities.

| Target | Related work delivered together | Detailed scope |
| --- | --- | --- |
| `0.1.0` | Locally installable secure async account service, authentication, identity, and offline proof | P0; core P1/P2; P3 identity; initial P6; local artifact subset of P7; identity adapter experiment from P8 |
| `0.2.0` | Grades, school averages, final summaries, upstream views, and date windows | Grade subset of P1/P3; corresponding P6 and local artifacts; business baseline and explicit qualification limits |
| `0.3.0` | Remaining academic and school-information reads | Attendance, timetable, agenda/homework, announcements, completed lessons; P4 notes evidence decision; corresponding P6 |
| `0.4.0` | Messaging, attachment streaming, and notification primitives with explicit side effects | Remaining message P1/P3; P4 content/attachments; P5; corresponding P6; consumer migration separately authorized |
| `1.0.0rc1` | Complete MCP replacement candidate and representative qualification | Full P6; migration-ready P7; P8 implementation, installed-artifact proof, and rollback rehearsal |
| `1.0.0` | Stable library contract and coordinated backward-compatible MCP backend cutover | Final P7/P8 release gates and supported API documentation |
| MCP `2.0.0` | Consumer-facing contract, packaging, configuration, and resource changes | P9 and ownership-map A01-A18; separate consumer version line |

Release order is sequential. P6 acceptance and local P7 artifact checks run for
every delivery, not only the release candidate. PyPI publishing gates start at
`1.0.0rc1`. During 0.x development, document
breaking library API changes in minor-release migration notes; reserve patches
for compatible fixes. After 1.0, use semantic versioning for the supported public
API. Release candidates use Python-compatible versions such as `1.0.0rc1`.

### 0.1.0 - Local-first secure account service and identity

First useful release: MCP can use public async methods to authenticate and read
identity through independent login-scoped clients under one shared scheduler.

- [x] Group packaging, provenance, transport selection, public lifecycle, typed
  identity/errors/references, and consumer contract inventory into the foundation.
  Design the domain conventions now; implement later endpoint records with their
  endpoint release instead of shipping unused model-only versions.
- [x] Deliver account isolation, session reuse, coalesced authentication, scoped
  cookies, destination validation, safe recovery, and redacted errors together.
- [x] Enforce shared rate/burst/concurrency/queue limits and bounded attempts,
  bodies, deadlines, parsing, and cancellation from the first network operation.
  Introduce safe-read coalescing and account-scoped cache infrastructure here;
  domain-specific metadata caches follow in 0.2.0.
- [x] Complete identity retrieval and the public-service/MCP adapter experiment,
  including the four-independent-login fixture-server workload from P6. Capture
  initial request-count and lifecycle measurements before widening coverage.
- [x] Build wheel/sdist and verify a clean local installation through a real
  fixture-server identity read. Publishing automation and PyPI installation
  evidence are deferred to P7 at `1.0.0rc1`; a bare skeleton is not a functional
  milestone. Exercise the consumer adapter with the exact local built artifact.
- [x] Document remaining live authentication/identity evidence gaps. P6-live is
  enabled separately after owner setup; it is not a local-first release gate.
  A later academic check must not be claimed from identity verification alone.

Suggested commit groups: package/contracts; scheduler/transport; authentication/
identity; adapter/E2E evidence; local artifacts/documentation. These
are review boundaries within one release, not five versions.

Local delivery gate: usable typed identity API, enforced combined traffic bounds
and login isolation, installed-wheel offline E2E proof, and explicit live
verification status. Daily live CI/PyPI gates remain deferred and incomplete.
Local gates are satisfied on Linux/Python 3.13 and 3.14. Consumer experiment PR #38
was closed without merging; its retained branch is optional local test material.
Default production backend migration remains a separate task.

### 0.2.0 - Grade coverage

Release scope was narrowed to grades by the owner. Attendance and every other
school-read family move to 0.3.0; communication moves to 0.4.0. This is not a
claim that postponed features have been implemented. Grade completion means
the declared business contracts, original offline failures/variants, installed
artifacts, and explicit live qualification status, not every possible school layout.

The local-first version is `0.2.0`, with `final_grades()`, `grades()`, and
`grades_window()`. It includes all/week/last-login views, descriptive-only rows,
multiple publications, dated period/annual/predicted-annual records, and separate
undated descriptive summaries. Missing metadata stays unknown. See contracts/grades.md
for declared compatibility and VERIFICATION.md for actual execution evidence.
The bounded four-context comparison used 94 of 128 allowed requests. Three contexts
completed installed comparisons; the second had an initial native parser failure
followed by successful installed-parser replay without new native traffic. Populated
dated descriptions/publications/corrections/averages and a second-context full
runtime rerun remain explicitly unqualified. Other school reads are outside 0.2.0.

#### Compatibility lessons and remaining gates

See REVIEW.md for the retrospective and CONTRIBUTING.md for the evidence checklist.
Offline commits and green CI must not be promoted into live compatibility claims.

The long-term consumer remains librus-mcp, but its migration is a separate task.
This repository owns the library implementation and qualification; consumer code,
dependency pins, backend defaults, commits, and PRs must not change without explicit
authorization for that project. Read-only consumer references and local integration
experiments are permitted. The earlier consumer adapter experiment was closed
without merging; it is not a prerequisite or deliverable for this grade slice.

- [x] Diagnose the initial native live failures and protect exact login continuations,
  explicit represented-user ID references, stray closing tags, and empty summary
  spacers with independently authored offline regressions.
- [x] Complete the installed-artifact bounded login/identity/summary path with
  output parity, without changing the production consumer backend.
- [x] Replace the provisional one-request/second policy with five requests/second
  and shared burst ten. Verify default-policy four-account admission and cooldowns
  offline, then rerun the bounded live comparison. Preserve old benchmark settings
  and non-wins in BENCHMARKS.md; do not infer upstream capacity from light traffic.
- [ ] Apply an early authorized installed-path smoke to each new operation family
  before marking it live-qualified. Record missing access as pending, not passed.
- [ ] Establish a bounded account-role/layout coverage matrix with populated,
  empty, missing-column, and unsupported-state evidence. Do not extrapolate from
  one account; do not expand credential scope without explicit authorization.
- [ ] Compare the native service against the optimized consumer with identical
  freshness and traffic policies on representative offline multi-account workloads.
  Investigate higher fixed RSS separately from lower parser allocation pressure.
- [ ] Implement the owner-configured P6-live drift check with offline-proven report
  redaction and explicit non-success for missing credentials or unexecuted checks.
  Any local credentialed harness must use a cumulative approved diagnostic budget,
  retain private replay only in memory, and never publish school captures.

Depends on 0.1.0. Deliver grade reads as one coherent feature set with shared
parsing, metadata preservation, upstream views, and bounded collection caching.

- [x] Implement declared grade-family business flows against librus-apix with
  original fixtures. Explicitly document intentional differences and unqualified
  populated variants; numeric parity is not full-family live qualification.
- [x] Complete grades/windows/final grades, typed school averages, descriptive
  entries/publications, upstream all/week/last-login views, and dated period marks.
- [x] Add bounded inline metadata reuse/caching, session invalidation, and measured
  warm/cold request reduction under the common scheduler. Record performance
  and completeness limits for the four-login workload; no per-grade lookup traffic.
- [x] Build/install wheel and sdist and exercise offline HTTP runtime paths on
  Python 3.13/3.14. Maintain no-replay, cancellation, isolation, and bounds proof.

Academic adapter implementation, MCP qualification, and consumer release belong
to the separately authorized migration task, not implicit library development.
Daily credentialed CI remains separately owner-configured, not silently enabled
or a prerequisite for a local-first grade release. PyPI and consumer migration
remain separate gates.

Suggested commit groups: grade contracts/models; views/parser business gaps;
offline and installed qualification; library release evidence.

Release gate: grade coverage and documented consumer-contract compatibility, with
measured request budgets and no fabricated success for missing capabilities.
Local gates are satisfied for the documented Linux scope. Remote delivery status
is separate from these local checks. No PyPI publication or consumer switch occurred.

### 0.3.0 - Remaining academic and school-information coverage

Depends on 0.2.0. These families are not part of grade delivery. The current
`0.3.0.dev0` increment implements offline-tested attendance collections, strict
upstream views, cached civil-date windows, details/notes, gateway records, and
overall/per-subject ratios with bounded metadata reuse. See contracts/attendance.md
for business differences, provenance, and narrow live qualification. A completed
installed native/apix pair qualified populated collections/detail/frequency on one
context; populated last-login, custom types, and wider roles remain pending.
This is not completed 0.3.0 coverage.

- [x] Attendance collection/views/windows with explicit semesters, unknown raw
  metadata, inert detail IDs, account isolation, fixed forms, and non-replayed POSTs.
- [x] Attendance/windows/details/frequency contracts, with explicit ratio units,
  preserved unknown types, bounded metadata reuse, and installed proof.
- [ ] Broader attendance role/layout qualification, populated last-login, custom
  type metadata semantics, and full-year subject-resolution qualification.
- [x] Ordinary agenda/details and homework/details with typed explicit month/window
  selections, full text/metadata, account-bound numeric references, central
  non-replayed wire forms and original parser/service proof.
- [ ] Complete installed agenda/homework/details qualification: current-month agenda
  has partial rendered proof; previous-month comparison stopped on an unclassified
  baseline tooltip difference. Installed live details/homework and populated live homework
  remain pending. Discovery alone is not installed qualification.
- [x] Compare unobserved populated homework/details and agenda variants against
  external unmodified apix with original synthetic responses; exercise all four
  installed public APIs offline and classify representation/integrity departures.
- [x] Completed lessons with typed records, same-response page metadata and bounded
  resumable batches; original parser/wire/lifecycle proof and installed artifacts.
- [ ] Qualify live completed-lesson pagination, populated/empty pages and broader
  role/date/layout variants under fresh authorization. Cursors are not snapshots.
- [x] Explicit timetable week API, typed days/slots/lessons/notices/recesses,
  centralized non-replayed forms, nineteen-operation wire catalogue, original
  offline fixtures, and installed two-week runtime retrieval on one context.
- [x] Resolve timetable teacher/classroom correctness with same-response Chromium
  checks: native matches all slots; document whitespace and incorrect baseline
  string departures rather than changing native to reproduce them.
- [ ] Obtain populated timetable group/replacement-tooltip and broader role proof.
- [x] Announcements with complete bounded text, author, raw/typed civil date,
  content-scoped references, central ordinary GET/OpenAPI, isolated cache/budgets,
  original fixtures and populated installed same-response apix/browser qualification.
- [ ] Broader announcement roles/empty/rich layouts and alternate date/ID variants.
- [ ] Bounded pagination/reference mapping, metadata reuse, account capabilities,
  original populated/empty/error fixtures, and installed-artifact proof per family.
- [ ] Apply the apix business compatibility gate and separately authorized live
  qualification to each enabled family; do not expand routine drift traffic.
- [ ] Record the behaviour-note capability decision. Implement only with
  independently sourced populated evidence; otherwise retain explicit limitations.

Consumer migration remains a separately authorized task, not an implicit adapter
deliverable in this release.

### 0.4.0 - Communication and notification safety

Depends on 0.3.0. Group messaging subsystem work with the operations whose
security and delivery semantics depend on it.

- [ ] Deliver received/sent message lists, bounded pagination, recipient discovery,
  full-message content, and source-bound references. Keep mark-read effects
  explicit and message bodies out of ordinary list retrieval.
- [ ] Deliver attachment metadata and credential-free bounded download streams
  with the MCP atomic-publication integration and cancellation proof from P4.
- [ ] Deliver the read-once schedule/checkpoint interface and adapt notification
  records while preserving MCP-owned seen state, hashes, replay, and migrations.
- [ ] Deliver validated single-attempt sending and typed unknown-delivery results
  together with MCP confirmation/token integration. Exercise these paths offline;
  do not widen daily CI to sends, mark-read content, or event consumption.
- [ ] Complete the corresponding library and consumer regression evidence and
  expose only public supported APIs to the adapter. Keep experimental notes
  governed by the evidence decision made in 0.3.0.

Suggested commit groups: messaging session/lists; content/streams; checkpoint/
notification adapters; send/confirmation integration; failure-path qualification.

Release gate: all required operation families have implementations or explicitly
documented experimental capability gaps, and the side-effect boundaries hold
through actual library/consumer runtime paths. Full migration qualification is
the next milestone.

### 1.0.0rc1 - Complete replacement qualification

Depends on 0.4.0. This is the integration/hardening release, not an additional
endpoint tranche. Further candidates (`rc2`, etc.) address qualification findings.

- [ ] Finish P8 across every required consumer operation and remove `librus-apix`
  imports, private patches, duplicated recovery, and obsolete dependencies in
  the migration branch. Preserve notification storage and file-publication owners.
- [ ] Complete R01-R17 proof mapping, the declared Python/platform matrix,
  installed-library/MCP stdio checks, and representative P6 comparisons with
  numeric acceptance thresholds. Resolve safety regressions before promotion.
- [ ] Reconcile the notes evidence gap explicitly: no supported operation may
  silently disappear. If parity is unavailable, record the default-off capability
  limitation and approve that consumer impact before calling the migration ready.
- [ ] Publish the candidate and qualify the consumer against that exact PyPI
  artifact, including existing state/spool readability and downgrade behavior.
- [ ] Complete authorized bounded account-type live checks, API/migration docs,
  release notes, dependency review, and the rollback procedure. Record remaining
  live evidence gaps without treating empty data as populated parser coverage.

Suggested commit groups: complete adapter/cutover cleanup; compatibility/state
verification; performance fixes; packaging/platform fixes; migration/release docs.

Release gate: a migration-ready candidate and tested consumer branch with no
hidden upstream dependency, no unresolved required-contract failure, and current
redacted live evidence. A candidate does not authorize production cutover alone.

### 1.0.0 - Stable API and consumer cutover

Depends on an accepted release candidate. Promotion may reuse the qualified
feature set; it does not need artificial extra implementation commits.

- [ ] Freeze and document the supported public API, limits, account ownership,
  error/capability semantics, and compatibility policy. Close candidate findings.
- [ ] Publish and verify the final library artifact, then rerun installed-artifact
  acceptance against that exact stable version before releasing its consumer.
- [ ] Release a backward-compatible MCP 1.x update pinned to the tested library;
  choose its next available version from the actual consumer release state.
  Keep library and consumer versions independent.
- [ ] Verify the consumer's public `uvx` installation, dependency graph, CLI and
  contract; publish migration/rollback instructions and retain daily drift checks.

Release gate: PyPI-backed library and consumer installations use supported APIs,
preserve the agreed MCP 1.x behavior, and satisfy P7/P8 without `librus-apix`.

### MCP 2.0.0 - Separate consumer modernization

Depends on the completed backend cutover. Group P9 into consumer PRs for typed
wire contracts, deprecated-tool removal, packaging/tooling, configuration/state
migration, and attachment resources. Release those related breaking changes as
one documented consumer major version, with its own prerelease if needed.

- [ ] Complete the ownership map's A01-A18 consumer work and migration guidance.
- [ ] Reuse the established library APIs; change the library version only when
  its own public contract or implementation changes, not to match the MCP major.

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

- [ ] Record independent implementation provenance and dependency licenses.
  Treat external implementations as research references, not material to copy.
  Retain consumer fixtures/tests in their existing repository; write new library
  fixtures independently. Do not claim this source-informed effort is clean-room.
- [ ] Decide distribution `librus-python-api` and import `librus_python_api`;
  confirm PyPI availability/ownership before release. Do not shadow `librus`,
  `librus_apix`, or `src`, and do not depend on upstream as a hidden fallback.
- [ ] Establish `src/librus_python_api/`, `pyproject.toml`, MIT SPDX metadata,
  bundled license, `py.typed`, and a single package-version source. Select and
  test supported Python versions; Python 3.14 compatibility is mandatory for
  the consumer. Claim older-version support only if exercised in the declared
  verification matrix.
  Local 0.1.0 progress: builds, checks, and installed-client/adapter reads are
  verified on Linux/3.13/3.14. GitHub-hosted CI also verifies this matrix; other
  platforms remain pending. PyPI ownership is still a separate release gate.
- [x] Choose one async transport after a small lifecycle/cookie/cancellation
  spike. Prefer evaluating `aiohttp`, already used by the consumer; do not add
  parallel `requests` and async implementations by default.
  Selected `aiohttp` after a loopback experiment, now retired in favor of real
  transport/service tests. The 0.1.0 account
  transport and login/identity network paths are implemented and tested offline.
- [ ] Define public async client ownership, `aclose`/context-manager behavior,
  explicit limits/proxy/TLS configuration, and an injectable transport boundary.
  Construction/import must do no network I/O or implicit environment discovery.
- [ ] Design one service-level lifecycle for all consumer accounts/tools, with
  account-scoped typed clients. MCP selects logins, operations, date ranges,
  and freshness and combines their results; the service handles scheduling and
  shared budgets. No summary/batch endpoint, private patches, or manual cookie
  wiring is required. Parent and student logins remain independent contexts.
- [ ] Create a per-operation contract matrix: account types, source endpoint,
  requested fields, result types, capability status, pagination, side effects,
  retry safety, and evidence confidence. Include every row in P3-P5.
- [ ] Keep upstream routes centralized in `config.py` and maintain importable
  OpenAPI YAML for every enabled operation, including raw HTML/form contracts.
  Validate method/path/operation/policy parity offline and document fixture
  provenance and live gaps. The initial empty contract/checker is implemented;
   nine login/identity wire contracts are populated. Later contracts accompany
   their own operation slices.
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
- [ ] Define typed page results with items, continuation, truncation reason,
  source identity, and detected-change information. Never imply that an offset
  cursor freezes upstream data. Bind continuation to account/query/source.
- [ ] Normalize IDs without conflating distinct sources: retain opaque IDs where
  evidenced, distinguish display IDs from valid legacy detail references, and
  reject URL/path injection. Numeric legacy routes remain strictly numeric.
- [ ] Model empty success, unsupported capability, unpublished data, permission
  denial, incomplete data, and parse failure separately. Required-field failures
  must not silently become `[]`, zero, or a fabricated record.
- [ ] Define account provenance, observation times, freshness, completeness, and
  typed operation failures. An account failure must not invalidate another's
  session/results; MCP owns partial-summary policy and cross-account merging.
- [ ] Define typed exceptions for invalid input, rejected credentials, required
  account action/captcha, session expiry, access denial, throttling, maintenance,
  connection/timeout, response limits, parsing, and uncertain delivery.
  Error messages and attached diagnostics must exclude secret/raw response data.
- [ ] Specify date-only values, school timezone (`Europe/Warsaw`), nullable fields,
  raw grade strings, missing grades, and explicit attendance units. Preserve
  school-provided averages where available; derived averages need documented
  weighting and grade-symbol rules, not assumptions from another school.
- [ ] Start with `scope`, typed detail/event references, integer calendar inputs,
  normalized field names, and ID-bearing record collections. Prefer an explicit
  ratio domain type; keep presentation conversion in MCP. Support A01-A08
  without inheriting legacy tool names or dynamic display-name dictionaries.

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
- [ ] Implement explicit session ownership and deterministic resource cleanup.
  Public injection must not require consumers to replace `_session` or clone
  private fields. Preserve all cookie restrictions and duplicate names.
- [ ] Independently validate the current login handshake, bounded redirect
  allowlist, proxy behavior, and authenticated terminal state. Do not reuse the
  obsolete password-grant path solely because historical packages used it.
- [ ] Coalesce concurrent authentication; allow at most one reauthentication for
  a proven safe operation. Distinguish bad credentials, expired session,
  persistent endpoint denial, maintenance, and confirmed throttling. Apply
  cooldowns once at the library owner boundary, with consumer-equivalent defaults.
- [ ] Recognize unsupported interactive authentication as an explicit outcome.
  Do not loop, mislabel it as a parser failure, or promise CAPTCHA/2FA support.
- [ ] Enforce connection/read and whole-operation deadlines, including queue
  wait, redirects, authentication recovery, body streaming, and pagination.
  A slow-drip response must not run indefinitely by resetting an idle timeout.
- [ ] Bound bytes before parsing for HTML/JSON and attachments. Cover absent or
  misleading Content-Length, chunked bodies, decompression, cumulative redirect
  bodies, malformed encodings, and cancellation while waiting for bytes.
- [ ] Bound parser CPU/memory and measure event-loop responsiveness on maximum
  accepted bodies. An asyncio deadline cannot preempt synchronous parsing;
  if parsing is offloaded, bound workers and account for their actual completion
  without letting them mutate session state after cancellation.
- [ ] Bound global and per-account active requests AND queued tasks. Share the
  global budget across clients without sharing authentication state. Decide
  which proven-safe reads may overlap; serialize session-changing operations.
- [ ] Enforce shared request rate and burst limits in addition to concurrency.
  Count login steps, redirects, retries, bootstraps, lookups, and page reads at
  dispatch. Use fair admission, bounded waits, and service-wide backoff where
  appropriate. Test that multiple account clients cannot multiply the budget.
- [ ] Set explicit service account/queue limits and per-operation attempt/page/
  byte/deadline budgets with conservative defaults. Allow MCP to share a total
  retrieval budget across its calls. Exhaustion stops new dispatch and returns
  a typed incomplete/limit result. No Librus-approved rate is currently known.
- [ ] Coalesce identical safe in-flight reads within account/query/session scope;
  reuse sessions and reference caches across summaries. Define waiter cancellation
  and freshness behavior; never share account data or coalesce side-effecting work.
- [ ] Classify retries by operation semantics, not GET/POST. Bounded backoff and
  Retry-After handling apply only to safe retryable operations. Never replay a
  send or read-once event request after an ambiguous result.
- [ ] Prove cancellation closes/releases resources and cannot leave requests
  mutating a session later. Do not remove MCP's thread-worker protections before
  the corresponding paths use the new native async implementation.
- [ ] Provide redacted diagnostics: endpoint class, status, elapsed time, counts,
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

- [ ] Implement the identity slice first, including an MCP adapter experiment
  and a fixture-server integration test. Record request count, session reuse,
  and exact field coverage before widening scope.
- [ ] Complete the remaining slices using separate fetching and pure parsing.
  Parse each response once and return pagination metadata with its rows.
- [ ] For HTML, locate semantic page/table markers and map verified headers.
  Handle documented span variants explicitly; reject ambiguous layouts. Avoid
  whole-document positional XPath and guessing empty success from missing tables.
- [ ] For JSON, validate envelopes, nested references, required values, and
  endpoint-specific variants. Bound IDs, list sizes, nesting/decoding work;
  preserve justified optional/unknown fields without silently skipping bad rows.
- [ ] Implement bounded page/offset continuation and ID deduplication. Cover page
  zero, repeated/clamped pages, overlaps, short/oversized pages, and empty ranges.
  Cursor translation may require retaining the legacy endpoint during migration.
- [ ] Support current scope/date filtering semantics. Label client-side filtering
  separately from upstream bounds; do not approximate `last_login` with a date
  window or lose events because authentication changed its reference point.
- [ ] Fetch needed metadata in bounded bulk or deduplicated per-ID requests.
  Add per-account bounded TTL caches, invalidation on account/session changes,
  and explicit freshness rules. Do not cache changing attendance as reference data.
- [ ] Define unknown attendance-type behavior using verified metadata. Never
  classify an unknown type as present or return 100% merely for lack of evidence.
- [ ] Keep JSON-to-HTML fallback explicit, capability-scoped, and budgeted. A
  schema failure must surface; it must not silently change data source or IDs.

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
- [ ] Prove cache capacity, TTL expiry, invalidation, and account isolation.
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
