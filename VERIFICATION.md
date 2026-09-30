# Local-first 0.1.0 verification

Date: 2026-09-30. Platform: Linux. No live Librus requests were made. Fixtures are
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
- Individual grades/GPA/windows and other remaining academic, messaging,
  attachments, send, and read-once event operation slices.

The six local-first 0.1.0 gates are satisfied for the documented Linux scope.
Library PR #1 is merged. The consumer adapter remains a draft; no package or
consumer release has been published. GitHub CI is defined in
`.github/workflows/ci.yml`; its remote run results are separate from the local
0.1.0 evidence above. Credentialed compatibility and publishing remain deferred.
