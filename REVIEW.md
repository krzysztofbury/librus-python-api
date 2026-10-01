# Delivery reviews and retrospective

The initial phase review below is historical offline evidence. Current live
qualification and performance evidence are in VERIFICATION.md and BENCHMARKS.md.

## Retrospective: offline confidence before live compatibility

### What failed

The implementing agent built and reviewed several increments before establishing
that the native installed client could complete the intended credentialed read.
The first live comparison failed in authentication; offline replay also rejected
the actual summary page. Fixing redirects then exposed an identity-contract gap.
Green CI, installed-artifact fixture tests, and repeated self-review had not tested
those real upstream boundaries. The failure was not a lack of tests in general:
the fixtures encoded unverified assumptions, so passing them could not validate
the assumptions themselves. Confidence and delivery framing outpaced evidence.

Confirmed compatibility gaps, not hypothetical explanations:

- Exact PerformLogin/Grant continuation destinations were missing from the native
  catalogue. Strict destination validation correctly rejected the unsupported flow.
- The identity wire contract required User.Id, while the observed gateway variant
  used the explicit Account.UserId reference and a names-only User object.
- The HTML parser rejected stray closing tags, and summary parsing treated an
  empty full-width spacer as a malformed subject. Synthetic valid markup omitted
  both structural conditions.
- The one-request/second, burst-one default imposed about eight seconds of cold
  admission wait. Fast fixture policies hid that default-path latency. The numeric
  limit was provisional, not grounded in a published upstream allowance.

### Process mistakes

- Authorization for live access was necessary and must never be assumed. However,
  once obtained, the smallest installed-client smoke should have been prioritized
  before expanding the feature work or treating the integration as usable.
- Implementing-agent self-review checked code safety and internal contracts, but
  did not supply independent upstream evidence. More passing tests or another
  self-review could not close that gap.
- Performance comparison started before the native workload could complete. Failed
  and successful workloads have different outputs and cannot establish speedups.
  Only completed, equivalent results support the later comparative measurements.
- Successive missing contracts required more credentialed diagnostic attempts.
  Private in-memory replay and allowlisted structural metadata should be planned
  up front, with cumulative traffic budgets, to avoid unnecessary relogins.

These were committed development checkpoints, not a PyPI publication or a completed
0.2.0 production migration. That boundary reduced deployment impact; it does not
excuse the compatibility blind spots or overconfidence. Historical evidence must
remain visibly labeled rather than silently promoted after one successful run.

### What helped and what changed

Exact route allowlisting prevented unapproved destinations; explicit parse errors
prevented fabricated partial output. Original regressions captured the independently
established redirect, identity-reference, and HTML requirements without committing
private captures. Bounded replay established summary parity; the installed live
path then completed. The revised five-request/second, burst-ten policy removed
artificial cold-login pacing while preserving shared budgets and cooldown handling.

Repository changes from this retro:

- CONTRIBUTING.md now distinguishes offline checkpoints from live qualification,
  requires an early authorized installed-path smoke, and documents evidence,
  diagnostic-budget, privacy, and benchmark rules.
- TODO.md records the narrow completed qualification separately from open account,
  layout, drift-check, and matched-policy multi-account gates.
- This retrospective documents confirmed failures and implementing-agent process
  responsibility. No global skills, harness configuration, or personal notes change.

The new bounded live sample is not a sustained-load test. Full academic coverage,
production backend migration, and broader compatibility remain pending.

Historical 0.1.0 review method: the shared pair-programmer/TigerStyle and test-audit
checklists, applied by the implementing agent, not an independent reviewer approval.
No live Librus request was made during that original review. Fixtures and
implementation are original and source-informed, not copied upstream material.

## Inline-grade checkpoint review

This is implementing-agent review, not independent approval. The current scope
is numeric/current grades, inline descriptive markers, raw school averages, and
inclusive windows, with grade-family gaps explicitly open in contracts/grades.md.
Unmodified librus-apix is the business baseline, not only a speed comparison.

- Safety: the new catalogue-bound POST selects a view and is not retry-safe.
  Credential form submission is rejected on this route; failure/expiry never
  automatically replays the view or credentials. All calls retain common budgets,
  default shared admission, isolated sessions/caches, and joined cancellation.
  Unknown metadata stays unknown, absent averages stay unavailable, and unsupported
  layouts fail instead of silently dropping data. No raw school capture is committed.
- Evidence: source discovery was deliberately distinguished from installed runtime
  qualification. In-memory replay exposed date weekday suffixes, HTML comments, and
  the empty-cell marker; original failing regressions preceded fixes. The later
  installed public grade path completed under separately approved caps and matched
  common numeric fields against unmodified apix. Empty descriptive/average samples
  cannot qualify populated variants or establish full business parity.
- Performance: inline metadata avoids per-grade requests. Four independent logins
  share default-policy scheduling, but not sessions or cached records. Window reads
  reuse the same collection, not an unbounded per-range cache. The small sequential
  live sample showed lower warm CPU/latency and reused connections, but higher RSS.
  Sustained upstream capacity and full-family equivalent performance remain open.
- Delivery: consumer PR #38 stays closed and its source remains read-only. Migration
  is a separate task; no production backend, dependency pin, package publication,
  or remote library delivery was changed by this checkpoint.

## 0.2.0.dev0 increment self-review

- Safety, TigerStyle #2 and #6: One catalogue-bound summary GET uses the existing
  operation budget and parser pool. Subject/column/value limits and exact expanded
  row widths prevent partial success. Absent columns differ from available empty
  or unassigned values; duplicates, unsupported spans, and ambiguous layouts fail.
- Safety, TigerStyle #12: Existing typed errors/recovery/cooldowns are reused.
  The native consumer adapter never falls back to legacy HTTP. Original tests
  reproduced BR/paragraph word concatenation before the rendering fix and retain
  inline symbol composition. Observations/results/diagnostics omit personal reprs.
- Performance, TigerStyle #14: One page is parsed once per coalesced flight, with
  bounded account/session cache reuse and no per-subject metadata/detail traffic.
  Four-login stdio measurements remain 28 cold and three warm requests. No live
  performance improvement is claimed.
- DX, TigerStyle #16: Shared summary records are in models.py, labels/routes/bounds
  in config.py, and behaviour in grade_parsers.py/service.py. The package is marked
  0.2.0.dev0, not released as complete academic coverage. Research provenance and
  parser/consumer test ownership are documented in contracts/grades.md.
- Remaining: numeric/descriptive grade collections, GPA, scope/date windows,
  other academic reads, and independently observed summary/account layouts.

## Safety

### Compatibility and measurement follow-up

- TigerStyle #13: Revise the explicit shared defaults to five requests/second,
  burst ten, without changing active/queue/operation limits or exempting login.
  A failing-before-fix token-clock regression protects burst/refill/idle-credit
  behavior; four-account HTTP saturation protects shared admission and unchanged
  concurrency. Default-policy service tests retain 429/503 cooldown/no-replay proof.
  Public rate-limiting guidance supports the pattern, not a numeric Librus quota.

- TigerStyle #6: Keep exact origin/path allowlisting for the newly observed login
  routes. User identity may use explicit Account.UserId but never owner ID or name
  matching. Conflicting references and booleans remain parse failures.
- TigerStyle #12: Accept only stray closing-tag repairs and a narrowly identified
  empty spacer; preserve strict semantic width/subject/table checks. Original
  failing regressions precede the fixes. No school capture is committed.
- TigerStyle #14: Eliminate a redundant authorization GET; keep connection reuse
  and coalescing. Optional logging initialization is deferred until enabled.
- Measurement honesty: report traffic policy wait separately; retain slower cold
  latency/higher RSS alongside faster warm reads, and distinguish traced Python
  allocations from total RSS. This remains implementing-agent self-review.

- TigerStyle #12: Full error handling. Repeated caller cancellation could interrupt
  scheduler worker cleanup, and a repeatedly canceled closer could return early.
  Both failures were reproduced in scheduler tests before the fix. Owned work is
  shielded, canceled once, and joined before slots are released. Parser cancellation
  also joins actual thread completion, since Python cannot preempt those workers.
- TigerStyle #6: Positive and negative space. A foreign redirect or unexpected HTML
  is not evidence of session expiry. Only 401 or an exact approved Synergia login
  redirect permits recovery. Required JSON fields/IDs, semantic HTML fields,
  duplicate envelopes/tables, media types, and expected identities fail closed.
- TigerStyle #2: Bounded loops. Request/operation waiters, authentication hops,
  attempts, wire/inflated bytes, cookies, JSON nesting, HTML node/depth counts, and
  parser workers have explicit limits. Retry-After is capped before timer use.
- TigerStyle #13: Explicit defaults. Tenacity retries only proven session expiry,
  with at most two safe-read attempts and the original shared budget. Login POST,
  connection ambiguity, denials, maintenance, and throttles are not replayed.
  Backpressure stays at the single shared scheduler, not independent retry sleeps.
  Repeated expiry after the single recovery attempt enters an operation cooldown;
  its next-call regression failed before the fix, preventing repeated login pressure.
- TigerStyle #4: Paired assertions. Login success requires a scope-applicable
  session cookie plus parsed identity; configured owner/student expectations and
  identity consistency are checked independently of alias/cache identity.
- Diagnostics use a closed typed event and opt-in Loguru sink. Account aliases,
  credentials, URLs, response excerpts, and exception objects are excluded.
  Shared-budget counters are labelled as budget totals, not per-operation deltas.

## Performance

- TigerStyle #14: Batching. Identical safe reads coalesce within a login and budget
  scope. Caller-requested freshness reuses at most two account/session cache entries.
  Distinct login contexts never merge, even for the same represented student.
- The installed-library MCP stdio workload verifies the existing 24-tool catalogue,
  three concurrent profile callers for each of four logins, one scoped denial,
  28 cold requests, three warm requests, four reused connections, and the combined
  25 requests/second, burst-two envelope. These fixture settings are not approved
  live traffic policy. No speedup versus the old backend is claimed.
- Maximum-body parser probe: eight 262144-byte JSON/HTML jobs, two bounded workers,
  loop heartbeat sampling, and traced peak memory. Coarse local regression gates
  are ten seconds total, 250 ms maximum heartbeat delay, and 32 MiB traced peak.
  This is not a cross-platform latency or process-RSS guarantee.

## DX and remaining qualification

- Tool audit: the transport experiment and its wrapper test were retired after
  preserving scoped duplicate cookies in the real transport test. Contract
  validation is a pytest helper with existing drift/reference regressions, not a
  second CLI. Parser measurements are opt-in performance tests; consumer stdio
  assertions are opt-in integration tests with a minimal subprocess fixture.
  No production seam was added, and no historical experiment remains a release gate.
- Shared data records and wire validators are centralized in models.py, settings/
  route policy in config.py, and the actual exception definitions/factory in
  exceptions.py. Private worker/queue state remains local to its implementation.

- TigerStyle #11: Warning clean. Ruff, formatting, strict mypy, OpenAPI/catalogue
  parity, offline suites, and installed-artifact checks are release gates.
- Public inputs, transport payloads/responses, wire validation, immutable domain
  records, typed exception factory, and diagnostic events have explicit types.
  The consumer owns field translation and its MCP output schema.
- The consumer adapter is opt-in and does not change its dependency pin, default
  CLI, tool schemas, notification state, or other operation backends. No fallback
  after native failure, private session patching, or cookie exchange is introduced.
- Live callback/account variants and profile label/layout compatibility remain
  unverified. Interactive CAPTCHA/2FA is unsupported. A lucky number has no
  fabricated civil date; unavailable data fails the consumer mapping explicitly.
- macOS/Windows, daily credentialed CI, PyPI, production backend migration, and
  broader endpoint coverage remain separate qualification work.

## 0.2.0 grades-only closure self-review

This is implementing-agent self-review, not independent approval. The release scope
is grades only; attendance and the remaining school reads move to 0.3.0 and messaging
to 0.4.0. Public contract/provenance and the apix business matrix are in contracts/grades.md.

- Safety: view selection is a strict enum and a fixed centrally configured form,
  never credential input or a scraped URL. All views remain `select_view` operations
  and never automatically replay after expiry or ambiguous failure. Shared traffic,
  body/metadata/record/subject limits, account isolation, and cancellation remain intact.
- Safety: undated descriptive semester text is a separate summary, not an invented
  dated grade. Publications preserve only explicit semesters, date/teacher/paragraphs;
  multiple blocks are retained. Unknown dated layouts fail. Numeric/descriptive
  families can share a subject without duplicate averages; same-family duplicates fail.
- Performance: no per-grade detail requests; each view has its own bounded cache and
  coalescing key. Date windows always use all-view data. Original loopback tests protect
  distinct selections, cache hits, and summary exclusion from dated windows.
- DX: immutable shared types distinguish current, period/annual, predicted marks,
  publications, undated summaries, unknown metadata, and unavailable averages.
  Contracts remain library-owned, independent of MCP schemas and notification state.
- Evidence: the approved four-context workload stopped on the first native failure,
  rather than hiding it with retries. Remaining authorized paths completed after
  original failing-before-fix regressions for undated text and overlapping subject
  families. Memory-only installed-parser replay passed the failed context; its full
  runtime qualification remains pending. Unpopulated variants are not called passed.
- Measurement honesty: retain native cold-latency and RSS non-wins, failed-context
  exclusion, last-login state differences, and sparse sequential sampling limits.
  Light traffic is not sustained-capacity qualification. Private responses were
  discarded and no consumer files, pins, defaults, commits, or PRs were changed.

Retrospective lesson: inspect populated and undated business variants early, compare
completed workloads and explicit projections, and preserve missing-state semantics
instead of widening a parser until every unknown page looks like empty success.

## 0.3.0.dev0 attendance checkpoint self-review

Historical collection-only checkpoint; detail/frequency follow-up is recorded below.

Implementing-agent self-review only, not independent approval. The increment
implements collections/views/windows and an explicit business matrix, not
attendance details/frequency or completed 0.3 coverage.

- Reuse account/session/cache/admission ownership; keep grade and attendance view
  forms separately typed and centrally configured. The selection POST is never
  replayed after expiry. Consumer serialization and frequency units stay separate.
- Explicit semester labels prevent positional reversal from fabricating a first
  semester when only the second is displayed. Unknown metadata/types stay raw or
  absent; no zero/false/presence/frequency defaults are invented.
- Original failing regressions exposed partial output outside the recognized grid,
  nested double counting, URL parser control-character normalization, nonliteral
  script calls, and plain tooltip value-bound gaps. Recognized detail references
  remain inert numeric data, not approved transport targets or executable scripts.
- Wire tests use distinct view data and windows with both included and excluded
  records. A fixture returning the same records for every selection would not
  independently protect form mapping or date filtering.
- Installed wheel/sdist runtime checks, not source imports alone, protect the
  public account path. Offline qualification does not establish live layouts.
- Dependabot's lock failure precedes all code checks. A local regenerated lock
  revealed a separate formatter change, so neither manifest widening nor green
  tests alone is a complete upgrade acceptance gate. Keep bot fixes separate.

Retrospective lesson: validate references before URL normalization, and pair each
parser completeness claim with an original failing unsupported-layout example.
Do not turn source-informed semantic labels into observed-upstream claims.

## Attendance detail/frequency qualification retrospective

- The declared missing APIs now have actual public reads and matching centralized
  contracts. Frequency names carry explicit ratio units and separate policies;
  custom types and absent denominators cannot silently become full attendance.
- Numeric references and metadata IDs validate on both request and response.
  Result and metadata caches are bounded, login-scoped, TTL-limited, and cleared
  on invalidation; record freshness is separate from reference reuse.
- Early installed smoke revealed a numeric period label missed by synthetic
  fixtures. An original failing regression protected it before the parser fix.
- The first detail fix guessed a close-control caption from incomplete structural
  evidence and still failed live. Preserve full-width ancillary text explicitly
  as notes rather than guessing its contents or treating it as unlabeled fields.
- Stop on failure, retain cumulative request accounting across authorized diagnostic
  scopes, and do not call parser replay a completed installed runtime. Final runtime
  qualification completed only after the notes model was installed and exercised.
- A completed known-field/ratio projection is not full-domain equivalence: retain
  native optional states/notes, declared zero-denominator differences, empty
  last-login qualification, and one-day subject-resolution limits in the matrix.
- Connection counts must state instrumentation scope. The baseline's synchronous
  requests were counted, but its auxiliary aiohttp connection creation was not;
  do not promote that lower bound into an exact connection-reuse comparison.

This remains implementing-agent self-review, not independent approval. Future
layout diagnostics should capture sufficient nonprivate structural evidence
before closing a failed session, without retaining captures or broadening traffic.
