# TODO

## Goal

Replace `librus-apix` in [librus-mcp](https://github.com/krzysztofbury/librus-mcp)
with this independently implemented, MIT-licensed library, published on PyPI,
while preserving the MCP v1.7.0 public contract. The library gives MCP a small,
typed async API over several independent Librus logins with shared, bounded
traffic. Optional API workflows own reusable durable state and orchestration;
MCP chooses accounts, configures paths, presents consent and owns its tool schemas.

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
| `0.4.2` | Full message content, explicit read side effects, attachment metadata | Done locally for observed already-read received content; populated attachment/sent gaps remain |
| `0.4.3` | Bounded attachment streams | Done locally for one received attachment; broader file/layout/effect gaps remain |
| `0.4.4` | Notification/checkpoint primitives | Done locally for count snapshots and offline checkpoint/replay; read-once live/consumer compatibility pending |
| `0.4.5` | Broader recipient selection and message-layout coverage | Implemented: choice discovery, selection-bound references, anonymous targets, sent receipts and observed received pagination; broader gaps remain |
| `0.4.6` | Single-use send attempts and typed uncertainty | Implemented and offline-qualified; exact one-recipient live qualification remains separately gated |
| `0.4.7` | Explicit modern identity, council discovery and single-use JSON sending | Implemented; offline qualification recorded in VERIFICATION.md; positive acknowledgements and sole-recipient live send remain gated |
| `0.4.8` | Optional durable send confirmations, claims and restart recovery | Implemented; 44 original SQLite/public-native fault/load cases; see VERIFICATION.md for source/artifact qualification |
| `0.4.9` | Optional notification persistence, bounded replay and delivery acknowledgement | Implemented; 50 original notification fault/load cases, source/wheel/sdist qualified on Python 3.13/3.14; final 0.4 persistence prerequisite, not full compatibility closure |
| `0.4.10` | PR #13 review hardening | Implemented; independent review fixes with fail-before regressions, source/wheel/sdist qualified on Python 3.13/3.14 |
| `0.5.x` | Modern authentication, broader communication coverage and live qualification | Planned; explicit evidence/consent gates below |
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
- [x] 0.4.2: full-message content and inert attachment metadata implemented.
  Explicit mark-read consent, summary-cache invalidation and no hidden replay;
  installed live smoke and Chromium/apix agree on one already-read received
  message. Source and installed wheel/sdist suites pass on 3.13/3.14. Populated sent content and
  attachment metadata, receipt variants and richer/new layouts remain unqualified.
- [x] 0.4.3: single-owner credential-free bounded download streams, shared
  request/byte/deadline limits and joined cancellation. Pair-programmer design
  and corrected post-review complete. Installed live smoke streams one received
  attachment; populated metadata and page-zero sent rows checked independently.
  MCP file naming and atomic-publication integration from P4 remain separate.
- [ ] Attachment follow-ups: sent-message downloads, multiple/empty files,
  broader signed-key/handler/header variants and upstream read-effect evidence.
  Do not expand allowlists without independent qualification.
- [x] 0.4.4 library primitives: explicit read-once consent, durable encoded-response
  handoff before parsing, typed events and zero-network local replay. Ordinary
  token-scoped counts use typed categories. No orchestration/seen state/hashes.
- [ ] Qualify read-once layouts on a dedicated test login with disposable events
  and separately approved recovery integration. Routine live checks exclude it.
- [x] 0.4.9: API notification seen state, canonical identities, raw/pending replay,
  explicit acknowledgement and neutral empty-target archive import/export through
  the optional persistence layer. No automatic schema or production-state migration.
  MCP's thin old-format compatibility adapter remains a separate migration task.
- [x] 0.4.5: bounded group-choice discovery, account/type/selection provenance and
  exact nonzero group forms qualified offline. Four independent contexts observe
  five named types, an anonymous target, unavailable class-dependent lookup,
  empty group options, populated received pagination and sent content/receipts.
  Keep typed unavailable outcomes separate from explicit empty-recipient success.
- [ ] 0.4.5 follow-ups: populated subgroup/virtual-class semantics, explicit empty
  recipients, sent pagination, multiple-recipient receipt/status variants and
  richer/new layouts. No claimed universal layout coverage. Any new live scope
  requires fresh approval; received opens still need explicit mark-read consent.
- [x] 0.4.7: explicit modern identity, type/council discovery and single-use JSON
  sending, with account/backend-bound references, separate cookies, central
  routes/OpenAPI contracts and original offline fixtures. 0.4.6 stays legacy-only.
  No cross-backend ID reuse, automatic fallback, setting changes or inferred
  retirement date. See
  [contracts/modern-messages.md](contracts/modern-messages.md).
- [x] 0.5 modern installed sender/council verification and sole-recipient manual
  send: one exact created/sent receipt, independently confirmed in the official UI.
  The receipt-parser correction is offline-qualified, not exercised by another send.
- [ ] Modern follow-ups: rejection envelopes and other positive send-acceptance
  variants, independent delivery acknowledgements, unavailable directory/virtual
  branches and unobserved archive/expanded recipient layouts remain gates.
- [x] Modern ordinary content, recipient read observations, fixed credential-free
  attachment streams, empty/sent-second-page layouts and one consented mark-read
  transition are implemented and narrowly source-API qualified on this PR.
- [x] 0.4.6, the legacy sending increment in the same PR: approved single-use
  attempt design implemented with typed uncertainty, exact fixed wire forms,
  shared limits and offline cancellation/fault proofs. See
  [contracts/sending.md](contracts/sending.md). MCP confirmation/token adapters
  and persistent attempt state remain separate; never widen the
  daily check to sends, mark-read content or event consumption.
  Planned manual live test: at most one Polish automation-test message to one
  privately specified recipient, explicitly requiring no response and apologizing
  for the unsolicited test. Verify sender and exact recipient first; qualify the
  native single-attempt path offline and agree on fresh authentication/discovery
  budgets before execution. Never retry uncertain delivery. Keep personal target
  details and the exact payload in owner-only local state outside Git.
- [ ] Library and consumer regression evidence for these paths, exposing only
  public supported APIs to the adapter.

### 0.4 persistence completion and deferred 0.5 sequence

The owner approved completing the remaining communication work one slice at a
time, including API-owned optional persistent send/notification workflows. Each slice
gets a separate scoped implementation/evidence commit; new library contracts get
their own 0.4.x version and source/wheel/sdist qualification. Consumer-only changes
do not fabricate a library version. The owner subsequently clarified the target:
extract reusable safeguards from MCP into the API and leave MCP as a thin consumer.
Replacement proceeds family by family after proof, not by deleting unqualified
legacy paths. This supersedes the earlier consumer-owned persistence split.

| Order | Work item | Owner and completion gate |
| --- | --- | --- |
| S2 | Persistent send attempts and recovery, 0.4.8 | Done offline: explicit API SQLite store, login/backend/exact-payload-bound confirmation, atomic claims, crash/uncertainty recovery without replay, bounded history and competing-process/load/fault proofs. Source/wheel/sdist qualified on Python 3.13/3.14. MCP adapter implementation stays deferred to its separate backend migration |
| S3 | Persistent notifications and checkpoint replay, 0.4.9 | Done offline: explicit native store/workflow, canonical identities, first-run/requested-category semantics, raw checkpoint before parsing, bounded replay before consume, two-phase acknowledgement, neutral archive and competing-process proofs. Source/wheel/sdist qualified on Python 3.13/3.14. MCP old-format mapping remains a separate migration task |
| S10 | Review follow-ups, 0.4.11 | Implemented offline: (a,b) modern expiry isolation and fresh pre-send identity GET; (c,d) explicit retention and salted version-2 disk/archive contexts; (e-i) stale-cursor kind, redirect-shape classification, full pager-less refusal, consumer idle timeout and completed-receipt deadline preservation. Source/wheel/sdist release qualification is recorded in VERIFICATION.md. No production migration, live authentication replacement or send authorization |

### 0.5 TODO - Compatibility and live communication qualification

0.5.0 delivers the bounded S1/S8 library slice, not universal messaging coverage.
S4-S7 and consumer integration remain separately qualified follow-ups. The package
and OpenAPI versions advance together; publication is still deferred.

The owner deferred the remaining authentication, coverage and live qualification
work to 0.5. Completing 0.4.9 closes the planned optional persistence prerequisites,
not universal upstream compatibility or the separate MCP migration. No live
authorization is created or renewed by moving these items.

| Order | Work item | Owner and completion gate |
| --- | --- | --- |
| S1 | Installed modern authentication, identity and council verification | Qualified for the one separately approved account/council context: scope 6 verified native/modern sender and uniquely matched the privately planned class-qualified recipient with the installed candidate. Fourteen requests, one credential submission, zero sends. All six scopes closed; no universal role/directory coverage claimed |
| S4 | Recipient coverage | Library; legacy populated selections/virtual classes/explicit empty layouts plus modern non-council branches, with independently established contracts and unsupported states explicit |
| S5 | Mailbox and receipt coverage | Library; sent pagination, richer/multiple-recipient receipts, modern received/sent lists and content, explicit read effects and backend-bound references |
| S6 | Attachment coverage | Library; sent/multiple/empty files, qualified signed routes/headers and modern metadata/streams; reusable safe naming and atomic publication move to an optional API file layer, with destination selected by MCP |
| S7 | Read-once live qualification | Separate approved dedicated test login with disposable events and tested persistent recovery; never use production events or routine CI |
| S8 | Sole-recipient send and acknowledgement qualification | Qualified one approved dispatch with durable claim, HTTP 201 exact created/sent receipt and independent owner confirmation in the official UI. Offline correction accepts only that envelope. Original UNKNOWN history is preserved; no retry, fallback or additional send; other receipt variants remain pending |
| S9 | Delivery closure | 0.5.0 library source/wheel/sdist and representative-load qualification plus local artifacts; current-head PR CI and consumer integration remain separate gates. Merge requires separate authorization |

The compatibility continuation stays on PR #15 in separate scoped commits.
The optional `librus_python_api.files` layer now supplies bounded portable naming,
owner-only temporary files, joined disk workers and atomic non-overwriting
publication of complete API streams. Its original tests use real loopback HTTP
and concurrent accounts; modern streams and broader upstream evidence remain
separate. This does not change MCP's configured download destination or install
anything into the consumer. See [contracts/attachment-files.md](contracts/attachment-files.md).

The same-PR continuation also implements modern inbox/outbox pages and bounded
collection, explicit read-consent content parsing with inert modern attachment
metadata, employee/class/student/parent directory routes and opt-in virtual query
selection. Source API live scopes qualify inbox pages 1-2, outbox page 1 and
teacher/tutor/school-admin/council branches on one account. Legacy group discovery
worked but returned no subgroup choices; classParents was not advertised. Unknown
sent read status remains unknown. Modern content is offline-qualified only;
modern downloads, richer receipts, populated legacy subgroups, virtual live
coverage and consumer integration remain gates. All three new authenticated
scopes are closed, with no send/content/download/read-once calls. See
[contracts/modern-communication.md](contracts/modern-communication.md) and
`release-evidence/0.5-communication-scopes.json` for exact scope boundaries.

The subsequent same-PR expansion implements explicit modern/archived attachment
resolution and credential-free streaming, richer recipient read observations,
plain/HTML/XML bodies and inert original/withdrawal metadata. Four fresh scopes
qualify available empty/sent-second-page layouts, ordinary content, a complete
7 MB modern stream and one consented unread-to-read transition. All four scopes
are closed; the first candidate stream hit its approved ceiling and was not
automatically rerun. Independent delivery acknowledgements are unknown. No login
advertised class-parent/virtual selections or exposed populated legacy subgroups;
those live checks remain unavailable, not passed. Archive/original layouts and
expanded receipt rosters have original offline tests but no live examples. See
`release-evidence/0.5-communication-expansion-scopes.json` and the communication
contract for exact evidence and limits. Consumer integration remains separate.

S1 progress: the first freshly approved 0.5 read-only scope used the qualified
installed 0.4.11 wheel. Native identity matched the private plan, but the modern
launch returned an unsupported path before handoff. Ten requests and one credential
submission were used; zero sends or read-once calls. That scope is closed without
automatic rerun. Sanitized facts: `release-evidence/0.5-modern-scope-1.json`.
The second separately approved launch-only diagnostic used ten requests and one
credential submission, verified native identity and retained only a redacted
`pobierz12` template and field facts. No handoff was followed and that scope is
closed. Facts: `release-evidence/0.5-modern-scope-2.json`.
`scripts/describe_modern_launch.py` is an offline redactor, not a network client
or redirect permission. At this early checkpoint the package version was 0.4.11; the candidate exact
route fix is not a qualified 0.5 release or a replacement for fresh installed
verification and sole-send execution-budget approval.
The third separately approved installed verification matched the qualified wheel
hash but stopped on a new `pobierz31` launch after ten requests and one credential
submission. No handoff or send. Facts: `release-evidence/0.5-modern-scope-3.json`.
The numbered namespace varies; the exact-number fix is not live-qualified and
adding numbers individually is not a proven complete contract.
The approved bounded-family candidate passes 1,353 tests per source/wheel/sdist
on both supported Python versions. The fourth fresh installed scope followed one
validated `pobierz16` handoff but stopped at modern identity with PARSE after
twelve requests and one credential submission. No recipient lookup or send.
Facts: `release-evidence/0.5-modern-scope-4.json`; offline candidate evidence:
`release-evidence/0.5-modern-family-offline-candidate.json`. The namespace fix is
live-exercised, not complete modern authentication/identity qualification.
Scope 5 established integer modern identity accountId with matching decimal owner
ID and names, without accepting identity. Identity-only normalization fixes the
original PARSE regression; directory IDs are unchanged. Twelve requests and one
credential submission, no send, scope closed. Facts: `release-evidence/0.5-modern-scope-5.json`.
Scope 6 passed installed native/modern identity and exact-recipient verification
after the integer identity fix: fourteen requests, one credential submission,
zero sends, scope closed. Facts: `release-evidence/0.5-modern-scope-6.json`.
The pre-send source/wheel/sdist candidate passed 1,366 tests on Python 3.13/3.14:
`release-evidence/0.5-modern-identity-offline-candidate.json`. S8 sole-message
execution at that checkpoint still required its separately approved fresh budget and durable claim.
Scope 7 consumed a fresh exact-message approval: sixteen requests, one credential
submission and one modern send POST, with fresh sender/recipient checks and a
native durable claim. HTTP 201 returned the exact created/sent receipt. Original
API result was UNKNOWN/PARSE because generic read validation rejected 201; the
owner independently confirmed the exact sent message in the official UI. The
candidate receipt fix preserves uncertainty for all other shapes, and no send
was replayed. Facts: `release-evidence/0.5-modern-scope-7.json` and
`release-evidence/0.5-modern-send-confirmation.json`. All seven scopes are closed.
The final receipt-corrected 0.5.0 library qualification is recorded separately in
`release-evidence/0.5.0-modern-qualification.json` and `VERIFICATION.md`; older
0.4.11-version candidate hashes remain historical and do not identify 0.5.0.

Live verification is evidence gathering, not permission to guess undocumented
wire shapes. Read-only discovery approvals do not authorize content opens,
downloads, sends, event consumption or account-setting changes. If evidence or
safe test accounts are unavailable, record that slice as blocked and continue
with the next independently implementable slice rather than claiming completion.

Persistence is explicitly selected by the application, with no credentials/cookies
in durable records and no coupling of core client/domain/transport contracts to
MCP schemas, file discovery or existing consumer storage formats. The optional
API layer owns expiry, payload/account/backend binding, locks, transactions,
retention and recovery primitives. MCP selects paths, presents human approval,
maps wire records and invokes deliberately reviewed compatibility migration. A crash
after claiming a send is conservatively uncertain, never an invitation to replay.
Preserve existing notification data and recovery files; do not reset production
state or automatically migrate it during development or offline tests.

Build the reusable prerequisites here first. MCP adapter implementation belongs
in the separate `librus-mcp` repository when migrating from `librus-apix` to this
API, not in the current library implementation slice. Default/release cutover still
requires installed acceptance and the release gate. Credentialed CI, PR merge
and publication require separate authorization. PyPI remains deferred until
`1.0.0rc1`. Existing evidence gaps remain open until their actual gates pass.

Each version is independently qualified and packaged locally. No sending or
live read-once operation is authorized by this sequence. Consumer migration,
credentialed CI and publication keep their separate approval gates.
The 0.4 series remains together in [PR #13](https://github.com/krzysztofbury/librus-python-api/pull/13):
0.4.0-0.4.10 are implemented; 0.4.9 completes persistence and 0.4.10 applies review fixes. Sending is offline-qualified only, with the
one-recipient live gate still pending. MCP migration is separate from this PR.
The separately approved offline S10 follow-ups are implemented in 0.4.11 on a new
branch; this supersedes only their previous 0.5 deferral, not S1/S4-S9 or live gates.

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
| Requested-category orchestration, first-run/diff/seen-state policy | Optional API notification workflow; MCP selects requested categories and serializes results |
| Durable checkpoints, canonical hashes, process locks, transactions, recovery | Optional API persistence layer; MCP maps legacy formats through explicit compatibility adapters |
| Attachment authorization and bounded byte streaming | Library |
| Download destination selection | MCP configuration |
| Reusable safe filenames, bounded temporary files, atomic non-overwriting publication | Optional API file layer |
| Message send transport and typed delivery outcome | Library |
| Durable send confirmation expiry/binding, single-use claims and recovery | Optional API persistence layer |
| Human approval and permission to invoke a write | MCP or other application |
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

- [x] Specify an awaitable checkpoint callback for the read-once schedule
  operation. The 0.4.4 design strengthens the boundary: consumer-owned durable
  handoff of the complete encoded response before decoding/parsing, then a typed
  complete batch. No filtering/enrichment before handoff. Define unknown
  acknowledgement, joined ownership and a finite cooperative checkpoint interval.
- [x] Document the remaining loss window before complete receipt/checkpoint;
  no exactly-once promise. Drain already persisted events before another live
  consume. Preserve overflow batches for later bounded processing.
- [ ] Move reusable first-run semantics, deduplication and persisted seen IDs to
  the optional API workflow. MCP selects requested categories and uses adapters
  instead of upstream `NotificationIds`, `RecentEvent`, and private diff parsers.
- [ ] Preserve canonical schedule identities, hashes, date/text normalization,
  pending-spool replay, and unrequested-category state. New gateway IDs need an
  explicit migration map/versioning strategy; do not silently reset history.
- [x] Library proofs: read-once receipt, checkpoint failure/cancellation, local
  restart decoding and same-login concurrency rejection on original loopback
  fixtures plus a real temporary filesystem sink. Never live double-fetch.
- [ ] Consumer proofs: failed seen saves, bounded spool draining, competing
  processes and state-format compatibility. The new raw envelope is not a
  drop-in replacement for the existing persisted event spool.
- [ ] Implement recipient discovery and a typed send result. Validate unique
  recipient references and payload bounds before I/O. Do not expose arbitrary
  authenticated URLs as a public escape hatch.
- [ ] Preserve at-most-one send attempt and distinguish rejection from unknown
  delivery after timeout/cancellation/unrecognized response. Do not retry or
  switch backend after possible acceptance. Optional API storage owns token expiry,
  binding and claims; MCP presents human approval when its backend is migrated.
- [ ] Verify confirmation expiration, payload binding, token reuse rejection,
  and uncertain-delivery MCP error mapping with the new library installed.

Exit: replay and delivery semantics survive end-to-end fault injection; no
live writes or read-once calls are necessary for routine CI verification.

## P6 - Performance and regression acceptance

Dependencies: each completed slice; full run before P8.

- [ ] Maintain a requirement-to-proof map for R01-R17. Library tests own transport,
  parsing, budgets and optional persistence transactions; MCP tests own wire
  serialization, consent presentation and adapter compatibility. Rework old private-internal mocks only when
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
