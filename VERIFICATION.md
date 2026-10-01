# Local verification history

Initial 0.1.0 check: 2026-09-30, Linux. No live Librus requests were made then. Fixtures are
independently authored synthetic examples, not copied HTML or credentialed captures.

## Proof matrix

| Boundary | Proof and local acceptance |
| --- | --- |
| Import/configuration | Strict frozen input limits, no credential/environment discovery, redacted construction failures, approved origins/TLS |
| Transport | Real aiohttp HTTP/cookie scope/isolation, foreign/auth-only redirect rejection, declared/chunked/inflated/cumulative body bounds, status classification, slow-body cleanup |
| Shared traffic | Four-account saturated scheduler workload; combined token bucket, global peak two/per-account peak one, bounded queues, shared budgets, pause/resume, repeated cancellation |
| Authentication | Original portal/form/cookie/redirect fixture, one POST, cookie plus parsed Me terminal verification, rejection/challenge/missing-cookie/malformed/loop failures |
| Identity/profile | Required envelopes/IDs and semantic labels, explicit missing lucky number, parent/student owner separation, immutable provenance, failed account isolation |
| Recovery | Tenacity two-attempt safe reads, one reauthentication, original budget, no replay of denials/ambiguous failures, shared throttle/maintenance pause |
| Freshness/coalescing | Three callers/login collapse to one cold profile flight, explicit-budget identity rules, TTL expiry, invalidation, survivor/last-waiter cancellation |
| Parser resources | Maximum-body probe with eight 256 KiB jobs, two workers, heartbeat and traced-memory measurements; actual thread completion joined after repeated cancellation |
| Consumer | Unchanged 24 default/28 all-feature catalog snapshots; real native identity adapter through stdio, legacy text JSON and structuredContent parity, scoped denial |
| Artifacts | Wheel and sdist installed outside source checkout; public-boundary suites and exact-wheel stdio probe, runtime metadata, py.typed/license contents |

The enabled subset of R01-R04/R05-R06/R10/R17 is owned by the transport, scheduler,
and identity tests above. Academic record regressions, notification/state ownership,
message delivery, attachment publication, and remaining R07-R16 coverage are not
claimed by an identity-only release. Existing consumer regression owners remain
in place; its full migration has not been performed.

## Results and measurements

- Library suite: 122 offline tests on Python 3.13 and 3.14, plus installed artifacts.
- Consumer branch: 570 offline tests, including existing stdio schemas/annotations.
- Ruff, formatting, strict mypy, OpenAPI/catalogue parity, and commit checks pass.
- Exact 0.1.0 wheel installed in a fresh Python 3.14 environment: 122 tests and
  the real stdio probe pass. The sdist build installed in a separate Python 3.13
  environment also passes 122 tests. Installed metadata confirms version 0.1.0,
  MIT, Python >=3.13, py.typed, and six declared runtime dependencies.
- The locked runtime dependency set was audited with pip-audit: no known
  vulnerabilities found at this check. This is database-based evidence, not a
  security guarantee or a claim about the consumer's remaining legacy dependencies.
- Real installed-library stdio workload: four login contexts, one shared represented
  student, three callers per context, and one profile denial. Exactly 28 cold
  requests, three warm requests, four reused TCP connections, one login per context,
  and combined 25 requests/second with burst two. Example elapsed time: 1.92 seconds.
- Maximum-body parser probe example: eight 262144-byte jobs in 0.105 seconds,
  maximum sampled heartbeat delay 0.011 seconds, traced peak 1648651 bytes.
  Thresholds: total under ten seconds, heartbeat under 250 ms, traced peak under
  32 MiB. Tracemalloc is not process RSS; these are local regression measurements.
- No old-backend comparison or live performance improvement is claimed. Fast
  fixture settings are not recommended live tuning values.

Reproduce using CONTRIBUTING.md and pytest: the default suite owns OpenAPI and
transport verification, `tests/performance` owns opt-in resource measurements,
and `tests/integration` owns opt-in consumer stdio verification in the installed
artifact environment. Expected
denied-account MCP calls return redacted error text rather than success/empty data.
The consumer adapter is draft PR #38 and remains opt-in.
Final distribution checksums are recorded in `release-evidence/0.1.0.sha256`,
outside the sdist inputs to avoid a self-referential archive checksum.
These checksums and the 122-test counts above describe the initial qualified
0.1.0 artifacts. The subsequent tools/model ownership cleanup retains their
behavioral proof with 121 default tests plus one performance and one integration
test; the retired experiment's duplicate-cookie case is in the real transport test.

## GitHub-hosted CI

[CI run 36721820811](https://github.com/krzysztofbury/librus-python-api/actions/runs/36721820811)
passed on 2026-09-30 for commit `95261910b7c7582cceb6155d42f5fea6523730fc`
in [PR #2](https://github.com/krzysztofbury/librus-python-api/pull/2).
All three Ubuntu 24.04 jobs passed: quality/security and Python 3.13/3.14.
Each Python job passed 121 portable tests against source, installed wheel, and
installed sdist. Logs confirm imports from separate site-packages directories.
Metadata/license/py.typed and dependency consistency checks passed, and both
distribution/report artifacts were uploaded. The quality job passed workflow
lint, repository hooks, full-history secrets, and the locked runtime/development
vulnerability audit. No live Librus requests or publishing occurred. These are
PR execution results, not evidence that the workflow has merged onto `main`.
The hardware-sensitive and cross-repository tests remain explicitly opt-in.

## 0.2.0.dev0 final-summary increment

The first academic increment is a development build, not a completed 0.2.0
release. On Linux/Python 3.13 and 3.14, 159 portable tests pass, including 38 new
final-summary cases. The exact built wheel passes all 162 tests when the opt-in
parser-resource and two real MCP stdio workloads are selected. A separately
installed sdist passes the 159-test portable suite on Python 3.13. The consumer
adapter checkout passes 573 tests; its Ruff/formatting and Bandit checks pass.
Library Ruff/formatting, strict mypy, and ten-operation OpenAPI parity pass.

The final-summary stdio workload keeps 24 default tools and exercises four login
contexts representing one student, three callers/context, one denial, optional
columns, and a two-subject result. It preserves one text block per summary and
the legacy structured result wrapper. Cold reads cost 28 requests, warm reads
three, with four reused connections and one login/context, under the shared
25 requests/second fixture budget. No school service or production state is used.

These tests own the new summary boundary. Common transport/cancellation/recovery
tests remain in place without being duplicated wholesale for another endpoint.
Tests also reproduced and fixed loss of word boundaries at HTML BR/paragraph
elements while preserving inline grade symbols. The implementation/fixtures are
original and source-informed; they do not establish live layout compatibility.
See `contracts/grades.md` for scope and provenance. The consumer backend stays
explicitly opt-in with no legacy fallback or production dependency change.

## Current compatibility/performance increment

The development wheel's bounded authorized login, identity, and final-summary
path now completes, with consumer-mapped summary parity. This uncovered exact
PerformLogin/Grant continuations, the explicit Account.UserId reference variant,
stray closing tags, and an empty full-width spacer. Original offline regressions
protect each variant and corresponding unsupported states. No live response,
identifier, credential, or school value enters repository fixtures.

After form reuse, the simplified four-login fixture uses 24 cold requests rather
than 28, retaining three warm requests and one denial. Live comparative observations
and same-page memory-only replay are documented in BENCHMARKS.md, including the
historically slower cold login and higher total process RSS. General live account
compatibility and multi-account performance remain pending.

The current suite has 174 portable tests plus four opt-in integration/performance
cases. The installed wheel exercises real MCP stdio and the paired synthetic
parser measurement; ordinary GitHub CI remains offline.

The revised default policy is five requests/second with a shared ten-token burst.
The new token-clock regression failed with the previous default, then passed with
the revised default. Four-account HTTP tests exercise both default and explicit
policies beyond burst capacity, checking the shared envelope and unchanged peak
concurrency. Existing 429/503 service tests now use default scheduler settings
and still prove cross-account cooldown and no replay. Pause/no-resume-burst,
queue, cancellation, and budget regressions remain in place.

An explicitly authorized rerun exercised the installed development wheel through
one login and three fresh summary reads per implementation. Outputs matched;
native cold retrieval was 949 ms versus 973 ms for the baseline, with 0.4 ms
admission wait instead of the earlier eight-second token delay. BENCHMARKS.md
retains both samples and documents the distinction between burst qualification,
offline saturation proof, and still-unqualified upstream sustained capacity.

## 0.2.0.dev0 inline-grade checkpoint

Historical checkpoint, superseded by the grades-only acceptance below.

The library now provides `grades()` and inclusive `grades_window()` with frozen
numeric/descriptive/average records, original parsing fixtures, and the explicit
view-selection POST contract. This is a development checkpoint, not completed
grade-family or 0.2.0 coverage. Business differences and gaps against unmodified
librus-apix 1.5.3 are recorded in contracts/grades.md.

The portable suite passes 219 tests on Linux/Python 3.13 and 3.14. The separately
installed wheel (3.14) and sdist (3.13) exercise the public grade path through
original loopback HTTP fixtures outside the source checkout. Coverage includes
numeric symbols, inline descriptive records, school average availability, inclusive
window validation, fixed POST form, original combined budgets, default-policy
four-login coalescing/isolation/cache reuse, and last-waiter cancellation. POST
401/login redirect/403/429/503 responses never replay credentials or the view
request. Credential forms are rejected on the grade route before dispatch.
Unknown nonempty/current or separate grade/publication layouts do not fabricate
empty or partial success. Existing shared transport/recovery tests remain intact.

Authorized discovery used ten requests, one login and one view POST, against a
20-request cap. It exercised the source transport path, not an installed public
grade read. The response remained in memory for parser work. Original regressions
exposed the ISO-only date assumption, lxml comment handling, and the `Brak ocen`
empty-cell marker before the fixes. Installed parser replay then completed, with
common numeric fields matching the unmodified baseline. The response was discarded.

A separately authorized installed-runtime comparison used one login and three
fresh all-view POSTs per implementation, 16 requests each/32 combined as caps.
Both completed with 12 HTTP requests each, 24 combined. The native cached date
window issued no extra request. Subject, raw symbol, civil day, semester, category,
and teacher matched for the observed populated numeric variant; no descriptive
entries or populated numeric averages were present. Full record parity is not
claimed because native preserves unknown metadata and raw/unavailable averages.
BENCHMARKS.md records cold/warm CPU/latency, requests, connection reuse, higher
native RSS, same-page replay measurements, and exclusions. Private school records
crossed only process memory/private pipes and were discarded; retained results are
redacted metrics. No consumer source, dependency pin, PR, or default backend changed.

Ruff, formatting, strict mypy, and thirteen-operation OpenAPI/catalogue parity
pass. No credentialed CI, PyPI publication, push, merge, or consumer migration is
claimed by this local checkpoint. Populated descriptive/average/correction and
other account variants, separate publication layouts, dated end-period metadata,
and upstream week/last-login filters remain grade-family gates.

## 0.2.0 local-first grade acceptance

0.2.0 is grades-only. Attendance and the remaining school reads move to 0.3.0;
communication moves to 0.4.0. The declared grade contracts are implemented, not a
claim of complete upstream layout or sustained-load coverage. No PyPI publication,
daily credentialed CI, or production consumer migration is part of this delivery.

Original offline regressions extend the grade suite with descriptive-only rows,
nested correction spans, period/annual/predicted-annual metadata, multiple publication
blocks, paragraph preservation, explicit/unknown semesters, strict view validation,
view-specific coalescing/cache reuse, and all-view date windows. Undated descriptive
semester text is a separate immutable summary, never assigned an invented date.
The same subject can appear in numeric and descriptive families without duplicated
averages; duplicate rows within a family remain failures. Existing traffic/error/
cancellation/expiry regressions continue to exercise the real loopback runtime.

The newly authorized installed comparison covered four independent login contexts
under a 128-request combined cap and a 16-request per implementation/context cap.
It dispatched 94 requests: three completed native/apix pairs at 12 requests each,
plus a native second-context failure at ten requests and a completed twelve-request
apix run. No automatic retry, read-once schedule request, message operation, capture,
or private normalized-record persistence was used. Runs were sequential and paced.

All three completed runtime comparisons matched the private legacy numeric projection
in all/week/last-login views. Missing native metadata was mapped to baseline defaults
only for comparison, not in domain results. Dated descriptive collections and numeric
averages were empty, so their equality is not populated qualification. The final
context exercised populated undated descriptive summaries using the updated installed
client; baseline omission is an intentional documented difference.

The second context's failure exposed undated descriptive cells and overlapping subject
families. Independently authored regressions failed before each fix. Its approved apix
read supplied memory-only response bodies for the updated installed native parser:
all three views then passed with common numeric parity, and the final-summary parser
also passed. This is not a successful second-context full runtime rerun. The replay
helper was closed and private response data discarded. A new runtime run requires
new bounded authorization. Populated dated descriptions, publication/correction/period
marks, numeric averages, role/layout extremes, and sustained capacity remain unqualified.

Week/last-login forms were independently exercised; sequential last-login parity
cannot prove identical historical-login state because authentication changes that
state. BENCHMARKS.md retains CPU, latency, request, connection, RSS, and sample limits,
including slower native latency in some views and higher whole-process RSS.

Final portable suites passed 236 tests each on source Python 3.13 and 3.14,
installed wheel Python 3.14, and installed sdist Python 3.13. The installed runs
started outside the checkout and exercised the full portable suite, including
real loopback authentication/view POSTs, windows, cache/isolation, and cancellation.
The four optional integration/performance tests were deselected; the grade consumer
migration is not implemented or implied by an old optional adapter checkout.

Commands: `uv run --locked pytest`, `uv run --locked --python 3.13 pytest`,
`uv build --no-sources`, then installed-environment `python -m pytest` with only
the original test directory on PYTHONPATH. Ruff, format checks, strict mypy,
thirteen-operation contracts, repository hooks, and `git diff --check` pass.
Redacted worktree secret scanning also passed, including untracked grade files.
Built distributions are local version 0.2.0, not published packages.

## 0.3.0.dev0 attendance collection increment

Historical first checkpoint; superseded by the detail/frequency qualification below.

2026-10-01, Linux. This development increment enables attendance collections,
strict upstream views, and cached civil-date windows. Detail/frequency and the
remaining 0.3 school-read families are not implemented. The route, forms, and
tooltip concepts are source-informed; semantic semester labels and all fixtures
are independently authored synthetic requirements, not observed live captures.
No live Librus request, consumer edit, PyPI publication, or merge occurred.

- 276 portable tests pass on source Python 3.13/3.14, separately installed wheel
  Python 3.14, and separately installed sdist Python 3.13. The four optional
  consumer/performance cases remain deselected. Installed suites run outside
  the checkout with an import-location guard; metadata confirms 0.3.0.dev0,
  MIT, Python >=3.13, six runtime dependencies, license files, and py.typed.
- Forty attendance cases exercise original populated/empty/malformed parsers,
  explicit reversed/single-second-semester grouping, raw custom types, unknown
  optional metadata, BR/bold tooltips, value/collection bounds, and inert references.
  Distinct view responses protect form-to-selection mapping; date windows include
  an excluded record and an empty selection, not only an all-record self-comparison.
- Actual loopback HTTP exercises login, fixed attendance forms, three-view cache
  reuse, four independent coalesced login contexts, request exhaustion, last-waiter
  cancellation, and no replay after 401/login redirect/403/429/503. Existing
  scheduler/transport suites continue to verify saturated shared budgets, cleanup,
  cooldowns, and destination guards rather than duplicating every lower-level test.
- Original regressions failed before guards for dated entries outside the grid,
  nested-table double counting, control-character URL normalization, nonliteral
  script arguments, and oversized plain tooltip values. They pass after the fixes.
- Ruff, formatting, strict mypy, lock consistency, fourteen-operation OpenAPI
  parity, repository hooks, redacted worktree/history secret scans, dependency
  consistency, and diff checks pass. The locked runtime/development dependency
  audit reports no known vulnerabilities at this check, not a security guarantee.

Reproduce with the portable/source and installed-artifact commands in
CONTRIBUTING.md. See contracts/attendance.md for the business matrix, intentional
semester/missing-value differences, and unresolved detail/type/frequency gates.
Installed attendance live smoke, populated role/layout qualification, and a
completed equivalent apix comparison remain pending fresh bounded authorization.
No attendance speedup or upstream sustained-capacity claim is made.

### Separate Dependabot review

PR #3 updates mypy/OpenAPI-validator/Ruff constraints but not uv.lock, so hosted
CI fails at lock validation before lint or tests. Read-only review plus an isolated
local worktree experiment refreshed its lock: mypy 2.3.1, openapi-spec-validator
0.9.0, and Ruff 0.16.9. Its existing 174 portable tests pass on Python 3.13/3.14;
lint and strict mypy pass. Ruff's new Markdown formatting flags API.md Python
examples; after local formatting, its format check passes too. These checks
describe the bot branch's older feature set, not the attendance increment.

No fix was pushed to the bot branch and PR #3 was not merged. It needs both lock
refresh and Markdown formatting before reconsideration. The repository currently
configures the pip ecosystem; GitHub now documents a dedicated uv ecosystem.
Review switching that configuration separately so future updates maintain uv.lock,
then qualify the generated PR instead of assuming the configuration fixes it.

## 0.3.0.dev0 detail/frequency and installed attendance qualification

2026-10-01, Linux. `attendance_detail()`, `gateway_attendance()`,
`attendance_frequency()`, and `subject_frequency()` now implement the documented
detail and ratio contracts. Raw type IDs remain available; standard classification
is source-informed, never inferred from HTML labels. Unknown types and zero
denominators make the ratio unavailable with explicit counts. Subject results use
numeric lesson/subject references, account-scoped bounded metadata, and shared
traffic/deadline/request budgets. Consumers own percentage/rounding and legacy
zero-denominator mapping. See contracts/attendance.md.

305 portable tests pass on source Python 3.13/3.14, the separately installed wheel
on Python 3.14, and separately installed sdist on Python 3.13. The four optional
consumer/performance cases remain deselected. Installed runs start outside the
checkout with import-location guards; metadata/license/typing and dependency
consistency pass. Ruff, formatting, strict mypy, eighteen-operation contracts,
lock checks, repository hooks, redacted secret scans, dependency audit, and diff
checks pass. No known locked-dependency vulnerabilities were reported at this
check, not a security guarantee.

The original offline suite protects separate overall/
subject denominators, unknown and zero states, strict JSON/dates/references,
duplicate IDs, metadata response-ID matching, real HTTP details/gateway/resolution,
login isolation, session/TTL invalidation, cache capacity and budget exhaustion.
The boolean-semester case failed before an explicit validator because strict
Pydantic Literal validation still accepted True as 1. Existing shared transport/
scheduler and collection cancellation/non-replay proof remains in place.

Bounded installed checks used one approved context only. Three stopped native
attempts cost 10, 13, and 13 requests. Original regressions then protected numeric
`Okres 1/2` headings and full-width detail text. A guessed close-button-only
exception still failed: the correct contract preserves ancillary text as separate
notes rather than guessing captions or omitting non-field content. No school
capture or identifiable fixture was incorporated.

Two authorized baseline runs completed at 29 requests each; the final installed
native run completed at 25. The successful final pair therefore used 54 requests.
Total qualification/diagnostics used 119 of the explicitly revised cumulative
160-request ceiling. Each fresh client run was capped at 32 requests, credentials
were submitted once per run, and every failed run stopped rather than replaying
login/view requests. Baseline token refresh and asynchronous metadata calls were
included in the guard counts. No read-once, send, other-account, or consumer call
was allowed.

All/week populated attendance and populated detail fields matched the declared
legacy projection. Last-login matched but was empty, not populated qualification.
Overall frequency and populated per-subject frequency for one observed civil day
matched. The comparison converted native ratios to legacy rounded percentages,
used legacy optional defaults only in the projection, and mapped one observed
zero-denominator unavailable semester to the baseline's full-attendance marker.
Native domain results retained unknown/unavailable states and detail notes.
Sequential authentication changes historical-login state, so filter equality is
not proof of identical historical state. Full-year subject resolution, custom
types, second-semester populated layouts, and wider roles remain unqualified.

Private comparison records crossed only process pipes/local restricted memory IPC.
The helper was closed and discarded them after comparison; only redacted metrics
remain. The full updated installed runtime, not parser replay alone, completed.
BENCHMARKS.md records the successful pair, non-wins, incomplete baseline connection
instrumentation, and policy/sample limits. No PyPI publication, live CI, consumer
modification, or merge of the attendance PR is implied.

## Explicitly pending

- Independently observed live authentication, callback/account variants, and
  populated JSON/HTML/profile encoding/layout compatibility. The conservative
  route/label allowlist can reject real variants until they are independently
  evidenced. Third-party flow requirements are not live qualification.
- Interactive CAPTCHA/2FA, multi-child switching, and unavailable lucky-number
  legacy marker parity. No fabricated civil date or unavailable string is returned.
- macOS/Windows installed-artifact/platform qualification.
- Owner-configured bounded daily credentialed CI, PyPI publication beginning at
  1.0.0rc1, complete consumer migration, and a production backend default switch.
- Populated grade variants, the failed context's full runtime rerun, and other academic, messaging,
  attachments, send, and read-once event operation slices.

The six local-first 0.1.0 gates are satisfied for the documented Linux scope.
Library PR #1 is merged. Consumer experiment PR #38 is closed, unmerged; no package or
consumer release has been published. GitHub CI is defined in
`.github/workflows/ci.yml`; its remote run results are separate from the local
0.1.0 evidence above. Credentialed compatibility and publishing remain deferred.
