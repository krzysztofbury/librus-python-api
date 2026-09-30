# Final-summary comparison

The development library was compared with `librus-apix` 1.5.3 plus the existing
consumer's final-summary parser. Apix alone does not expose that summary operation.
This is not a comparison with the consumer's optimized persistent Requests
session or with its broader individual-grade operation.

## Rerun with the revised default: 5 requests/second, burst 10

The same bounded workload was repeated using the installed development wheel,
the default shared scheduler, and unmodified apix 1.5.3 plus the consumer summary
parser. Both isolated processes used Python 3.14.7, one credential submission,
and three fresh summary reads. Two-second pacing between reads and imports remain
outside timing. Summary outputs matched and no 429/503 response occurred.

| Metric | Native development API | apix 1.5.3 + summary parser |
| --- | ---: | ---: |
| Cold elapsed | 949 ms | 973 ms |
| Cold scheduler admission wait | 0.4 ms | None |
| Cold client CPU | 20.8 ms | 48.1 ms |
| Cold HTTP requests | 10 | 10 |
| Mean of two warm fresh reads | 132 ms | 242 ms |
| Mean warm client CPU | 4.46 ms | 21.18 ms |
| HTTP requests per warm read | 1 | 1 |
| New connections per warm read | 0 | 1 |
| Connections opened across all three reads | 2 | 5 |
| Whole-process peak RSS across retrieval | 59.5 MiB | 51.1 MiB |

Cold retrieval no longer has the previous eight-second token wait. Its latency
is effectively comparable in this single sample, not proof of a cold-speed win.
Warm elapsed was approximately 45% lower and warm CPU approximately 79% lower.
Both implementations dispatched 12 HTTP requests overall. Native still has a
higher fixed RSS footprint. Shared throttling is retained: the short sequential
login fits within burst credit; continued multi-account traffic still consumes
the same bucket. Apix remains unthrottled, so these are real default-behavior
results, not a matched-policy sustained-load benchmark or a Librus-approved quota.
A successful light sample does not qualify upstream capacity under load.

## Historical bounded live sample: previous 1 request/second, burst 1 policy

Both isolated processes used the same Python 3.14 environment, one credential
submission and three fresh summary reads. Imports and two-second between-read
pacing were excluded. Native's then-default one-request/second shared limiter stayed
enabled; apix has no corresponding limiter. Consumer-mapped summary fields matched.
No credential, cookie, account detail, or response capture is retained here.
The default is now five requests/second with a shared burst of ten. These timings
are historical, not measurements of the revised default.

| Metric | Native development API | apix 1.5.3 + summary parser |
| --- | ---: | ---: |
| Cold elapsed, including traffic policy | 9.18 s | 0.90 s |
| Cold scheduler wait | 8.16 s | None |
| Cold client CPU | 24.4 ms | 55.9 ms |
| Cold HTTP requests | 10 | 10 |
| Mean of two warm fresh reads | 128 ms | 208 ms |
| Mean warm client CPU | 4.9 ms | 24.6 ms |
| HTTP requests per warm read | 1 | 1 |
| New connections per warm read | 0 | 1 |
| Connections opened across all three reads | 2 | 5 |
| Whole-process peak RSS across retrieval | 59.9 MiB | 51.0 MiB |

Warm elapsed was approximately 38% lower and warm CPU approximately 80% lower
in this small sample. There is no request-count reduction for a single fresh
read. Cold elapsed and total RSS were not wins: the previous traffic policy
increased cold latency, and native imports/configuration carry a higher fixed footprint.
Removing the limiter merely to improve the table is not an acceptable optimization.
These few network samples are not statistical latency guarantees or proof of live
performance under multi-account load. The actual pages contain session-specific
markup; equivalent summaries do not mean byte-identical HTTP responses.

## Same-page offline replay

In the revised-policy rerun, both pure parsers consumed the exact same page
retained only in process memory.
Timing used 100 parses without tracing; a separate ten-parse pass measured Python
allocations. No additional upstream requests were made for replay.

| Metric | Native parser | Consumer summary parser |
| --- | ---: | ---: |
| CPU per parse | 2.81 ms | 14.51 ms |
| Traced Python allocation peak | 232 KiB | 7,335 KiB |

This sample shows approximately 5.2x faster parsing and 32x lower traced Python
allocation peak. Tracemalloc does not measure all native lxml allocations and is
not total RSS. These results do not imply every grade layout or parser is faster.

`tests/performance/test_grade_comparison.py` provides a reproducible, entirely
synthetic paired parser workload with explicit output parity. It imports the
consumer parser from an opt-in checkout, never copies its source or fixtures.
It alternates order, separates CPU timing from tracing, and records metrics without
imposing machine-dependent speed ratios as functional test gates. See CONTRIBUTING.md.

## Remaining work

Measured benefits are lower warm CPU/latency, persistent connections, and much
lower parser allocation pressure. Synthetic four-login tests additionally prove
coalescing, isolated caches/sessions, and shared traffic budgets; the simplified
fixture's cold workload is now 24 requests instead of 28. These features matter
under concurrent callers, but do not replace comparison with the optimized
consumer backend using identical freshness and traffic policies.

Further performance work should target fixed RSS overhead and realistic
multi-account comparisons. Other account variants remain unqualified.
