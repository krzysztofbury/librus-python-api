# Targeted quality evidence

These commands use original loopback fixtures only. They do not contact Librus.
They are opt-in diagnostics, separate from the portable functional suite.

## Guard mutations

Run using the development environment, with an owned temporary directory:

```sh
uv run python scripts/mutation_guards.py
```

The script creates and cleans one unique temporary directory, copies the source,
tests and their contracts there, and mutates only that disposable copy. Each
named mutation has a passing focused pytest baseline before its altered run.
The copy is explicitly first on `PYTHONPATH`; bytecode writes are disabled.
Anchors must match exactly once. A pytest test failure is required, with JUnit
evidence printed as JSON. Collection/setup errors, subprocess timeouts and test
timeouts are harness failures, not killed mutants. Surviving mutants fail the
command and must be investigated for equivalence, without a score target.

| Guard | Weakening | Owning test / expected failing contract |
| --- | --- | --- |
| Account isolation | Remove the cursor account check | `test_foreign_folder_account_and_invalid_history_fail_before_any_login`: foreign cursor reaches wire/continuation instead of failing before login |
| Account queue | Remove per-account queue bound | `test_global_and_account_queue_limits_reject_without_dispatch`: rejection must be immediate |
| Global queue | Remove shared queue bound | Same test: shared capacity must reject immediately |
| Response bodies | Remove decoded-body bound | `test_body_limits_apply_before_decoding_or_parsing[compressed]`: the configured byte limit must win before gzip completion/parsing |
| Pages | Remove maximum page-count check | `test_page_and_row_actual_maximum_boundaries`: 1001 pages must fail with `LimitError` |
| Send non-retry | Allow session recovery for a non-retry-safe operation | `test_dispatched_failure_or_response_has_one_attempt_and_explicit_outcome[401]`: exactly one login and one send; the lower dispatch guard still prevents a duplicate write |
| Checkpoint ordering | Decode before checkpoint | `test_encoded_payload_is_durable_before_decoding_or_parser_failure[markup]`: malformed content must already be durable before parsing fails |
| Redirect rejection | Accept non-login/non-module redirects | `test_module_redirect_is_typed_without_following_or_reauthenticating`: redirect classification must remain access denied |

The initial combined queue mutation produced only a timeout. The existing
owner test was strengthened to assert synchronous rejection after admission,
with task cleanup on failure. It now detects the weakened bound directly. The
cursor test now uses a real loopback server, so its mutant cannot fail merely
because an unrelated local port is closed. No production testing seams were
added.

On 2026-10-09 all eight mutations produced test failures after their individual
passing baselines. There were no surviving or equivalent mutants. Queue failures
were direct assertion failures, not timeouts. This is evidence for these named
weakening operations only, not exhaustive mutation coverage.

## Representative load

```sh
uv run pytest tests/performance/test_fixture_load.py -m performance -s
```

Three repetitions use four independent accounts representing the same fixture
student. Each mailbox has five full pages of 50 messages (1000 records across
accounts). The shared scheduler allows two active requests, one per account,
four queued globally, one per account, and a fixture-only 1000 requests/second
rate with a 16-token burst. This measures local contention, not public-service
rate capacity. Each repetition checks:

- Cold login plus full mailbox reads: exactly 40 requests under one shared
  60-request budget (20 authentication/identity and 20 mailbox requests).
- Warm cached results: zero additional requests, preserving account ownership.
- Explicit fresh reads: exactly 20 additional requests, exhausting that budget.
- Changing pages: four one-item reads followed by four resumed reads, exactly
  eight requests; each changed fingerprint raises `StaleCursorError`.
- Slow chunked bodies: two active and two queued operations before cancellation.
  Only the two admitted requests spend budget. All four tasks are joined and
  scheduler active/queued counts return to zero.
- Recovery: four successful slow-body reads, exactly four requests, proving
  released capacity/connectors remain usable. The server delays completion by
  20 ms per request.

The test prints request counts, per-operation p50/p95/max latency (12 samples
per phase), overall elapsed time, maximum sampled scheduler activity/queueing,
and peak Python memory from `tracemalloc`. Native allocations and process RSS
are outside that memory metric. Sampling may miss brief peaks; saturation is
also checked explicitly before cancellation.

### Baseline and thresholds

Initial successful Linux x86-64 / CPython 3.14.7 baseline on 2026-10-09:
2.12 seconds total, 3,135,087 traced peak bytes, two active and two queued.
Maximum seconds per phase: cold 0.278, fresh 0.258, warm 0.00036,
changing-page 0.050, cancellation 0.0019, slow recovery 0.050.

Coarse regression ceilings chosen with roughly tenfold headroom (larger for
sub-millisecond warm/cache work) are:

| Measurement | Acceptance ceiling |
| --- | --- |
| Three repetitions total | 25 seconds |
| Traced Python peak | 32 MiB |
| Cold or fresh operation | 3 seconds |
| Warm cached operation | 0.05 seconds |
| Changing page, cancellation or slow recovery operation | 0.5 seconds |
| Active requests | Exactly two observed, never more than two |
| Queued requests | At least two observed, never more than four |
| Final active/queued | Zero |

These thresholds apply only to this fixture workload. They establish no
production latency, upstream availability, native-memory or universal hardware
performance guarantee. Existing parser resource checks retain their separate
thresholds in `tests/performance/test_parser_resources.py`.
