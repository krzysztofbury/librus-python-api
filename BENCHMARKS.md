# Grade comparisons

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

## Installed inline-grade comparison

The next increment was compared with unmodified librus-apix 1.5.3's own
`get_grades`, without the consumer summary parser. Explicit authorization covered
one account, one login and three all-view POSTs per implementation, 16 requests
each/32 combined, with no retries. Both completed all three reads and dispatched
12 requests each, 24 combined. Numeric subject/symbol/day/semester/category/teacher
fields matched. Full record parity is not claimed: native preserves missing
metadata and raw/unavailable averages where legacy substitutes defaults. Neither
sample contained descriptive entries or populated numeric averages. The business
coverage matrix in contracts/grades.md remains the feature-completion gate.

Both isolated workers used Python 3.14.7. Native used the installed development
wheel and unchanged default shared scheduler. Apix remained unthrottled. Imports,
two-second pacing between reads, and the three-second between-backend pause are
outside retrieval timing. This is a small sequential default-behavior sample,
not a matched-policy load test or full-family equivalent-output benchmark.

| Metric | Native grade collection | Unmodified apix 1.5.3 |
| --- | ---: | ---: |
| Cold elapsed | 871 ms | 1419 ms |
| Cold client CPU | 23.1 ms | 54.3 ms |
| Cold scheduler admission wait | 0.4 ms | None |
| Cold HTTP requests | 10 | 10 |
| Mean of two warm fresh reads | 160 ms | 221 ms |
| Mean warm client CPU | 7.89 ms | 25.66 ms |
| HTTP requests per warm read | 1 | 1 |
| New connections per warm read | 0 | 1 |
| Connections across all three reads | 2 | 5 |
| Whole-process peak RSS across retrieval | 61.3 MiB | 50.4 MiB |
| Process RSS before retrieval | 55.9 MiB | 39.2 MiB |

A cached native date-window check dispatched no further HTTP requests. Native
still uses more whole-process memory. The measured wall times do not establish
statistical cold superiority, sustained capacity, or broader layout compatibility.
Apix response-byte totals were not instrumented in this run, not measured zero.

Before the live run, the installed native parser and unmodified apix grade parser
also replayed the exact discovery page held only in memory. Twenty timed parses
per backend averaged 5.70 ms versus 18.20 ms CPU, about 3.2x lower native CPU.
A separate traced parse peaked at 217 KiB versus 1743 KiB Python allocations,
about 8x lower. Common numeric-field parity passed. No extra school requests were
made; no capture or normalized school record was retained. Tracing excludes some
native allocations and these figures are not total RSS or full-layout coverage.

## Grade views: expanded bounded account comparison

The next approved qualification used four independent login contexts and
all/week/last-login POSTs, one login per implementation/context, paced sequentially
with no replay. The combined count was 94 of 128 allowed requests: three completed
native/apix pairs (12 each), one native parser failure (10), and its remaining
approved apix path (12). It was an installed development artifact before the final
0.2.0 version bump. All live school responses/records were discarded.

The following means cover only the three completed runtime pairs, one observation
per view/context. The failed context is excluded, not converted into a successful
timing sample. Authentication is included in all-view cold reads; each following
view makes one request. These are sparse sequential samples, not matched-policy
multi-account load or throughput evidence.

| View | Native wall / CPU | apix wall / CPU | Requests native / apix | New connections native / apix |
| --- | --- | --- | --- | --- |
| All, cold | 1097 / 23.8 ms | 938 / 53.8 ms | 10 / 10 | 2 / 3 |
| Week, warm session | 198 / 5.86 ms | 226 / 22.3 ms | 1 / 1 | 0 / 1 |
| Last-login, warm session | 142 / 5.64 ms | 220 / 20.3 ms | 1 / 1 | 0 / 1 |

Native cold latency is a non-win here; one native week sample was also slower.
Native scheduler wait averaged 0.43 ms cold and 0.03 ms per warm view. Lower CPU
and connection churn do not establish lower upstream latency or traffic volume.
Each completed run dispatched twelve requests in both implementations. Whole-process
peak RSS was about 60.9-61.3 MiB native versus 48.9-49.2 MiB apix after the final
view, again a native non-win. Fixed-startup attribution remains separate work.

The three completed pairs matched the private legacy numeric projection in all
views. No populated numeric averages or dated descriptive/publication/correction/
period variants were exercised. The updated fourth-context native runtime preserved
undated descriptive summaries omitted by apix. Independent authentication changes
last-login state; equality does not prove historical-login equivalence.

After original regressions and fixes, installed native parser replay of the failed
context's memory-only apix response bodies passed all views with common numeric
parity and final-summary parsing. Twenty all-view parses averaged 3.46 ms CPU,
with 168 KiB peak traced allocations. This was zero extra upstream traffic and
is not a successful full-runtime rerun. Tracing excludes native allocations.

## Attendance: completed installed comparison

2026-10-01, Linux/Python 3.14. One approved context, installed native 0.3.0.dev0
and unmodified apix 1.5.3. The final pair completed all/week/last-login attendance,
one populated detail, overall frequency, and per-subject frequency for the same
one-day selection. Known-field/ratio projection matched; last-login was empty.
Native unavailable zero-denominator ratios were explicitly projected to legacy
full-attendance markers for comparison only. Notes and unknown optional values
remain native domain additions/differences, not full-record parity.

| Operation | Native wall / CPU (ms) | apix wall / CPU (ms) | Requests native / apix |
| --- | --- | --- | --- |
| All, cold including authentication | 1007.58 / 20.43 | 992.60 / 39.55 | 10 / 10 |
| Week, warm session | 89.01 / 3.32 | 152.26 / 11.02 | 1 / 1 |
| Last-login, empty | 77.03 / 2.76 | 121.67 / 13.88 | 1 / 1 |
| Populated detail | 37.57 / 2.19 | 81.45 / 10.90 | 1 / 1 |
| Overall frequency | 61.19 / 3.80 | 218.06 / 15.59 | 1 / 2 |
| One-day subject frequency | 668.39 / 13.15 | 1227.26 / 32.54 | 11 / 14 |

The final pair used 25 native/29 apix requests, 54 combined. Cumulative authorized
diagnostics used 119 of the revised 160-request ceiling, including three stopped
native attempts and an earlier complete baseline run. Those failed/superseded
attempts are excluded from timing comparisons, not silently called successful.
Private data remained in pipes/restricted local memory IPC and was discarded.

Native cold latency and whole-process RSS remain non-wins. Peak RSS/HWM after
subject retrieval was 64624 KiB native versus 60916 KiB apix. Native observed two
new connections and 23 reuse events. Ten baseline synchronous connection creations
were observed, but its auxiliary aiohttp metadata connections/reuse were not
instrumented: that is a lower bound, not an exact comparable connection total.
Response-byte counts and parser-allocation peaks were not measured for this pair.

Both runs had external safety guards capped at five requests/second, burst ten,
32 requests and one credential submission. Native also used its real default
shared scheduler; baseline business functions and their auxiliary async metadata
workflow were unchanged. Baseline subject timing includes 811.33 ms of external
guard wait; native guard wait was zero because native scheduling/latency already
paced dispatch. Native scheduler wait was not separately measured here. This is
not a clean unguarded client-speed ratio or matched-concurrency sustained benchmark.

Imports and two-second between-view pacing were excluded; authentication and
admission were included in retrieval timings. Extra baseline token refresh and
metadata requests are real completed-workload differences. This is one sequential
sample per operation, not general throughput/capacity or full-year resolution
qualification. Sequential logins change last-login state; empty equality cannot
qualify populated historical-login behavior. Wider roles/layouts and custom types
remain unqualified. No consumer backend or dependency was changed.

## Timetable: completed runtime with unresolved field parity

2026-10-01, Linux/Python 3.14. Installed native 0.3.0.dev0 and unmodified apix 1.5.3
each completed the same two ordinary weeks on one approved context. The explicit
legacy projection matched subject/date/time/weekday/number/recess/change fields,
but combined teacher/classroom differed in 29 periods per week. These are completed
retrieval workloads, not successful full-field parity or interchangeable consumer
output. The remaining difference is not proven to be whitespace-only.

| Retrieval | Native wall / CPU (ms) | apix wall / CPU (ms) | Requests native / apix |
| --- | --- | --- | --- |
| Current week, cold including authentication | 1327.60 / 22.30 | 1369.73 / 52.90 | 10 / 10 |
| Adjacent week, warm session | 546.37 / 6.77 | 830.64 / 22.27 | 1 / 1 |

The final pair used 11 requests per client, 22 combined. Native explicit reuse of
the first cached week made no additional request. Cumulative discovery/diagnosis
cost 74 of the revised 96-request authorization, including three stopped native
attempts, one discovery and a superseded complete baseline. Failed/superseded
attempts are not included in the final pair's timing or called successful parity.

Native observed two new connections and nine reuse events. Baseline observed four
synchronous connection creations; reuse events were not directly instrumented,
not measured zero. This timetable baseline uses synchronous requests only, unlike
the auxiliary aiohttp attendance metadata path. Peak RSS/HWM after the adjacent
week was 64108 KiB native versus 49216 KiB apix: native memory remains a non-win.
Decoded retrieved body bytes were 71737/71076 cold and 55857/55857 warm. Cold bytes
include different authentication/identity flows, not a timetable-byte advantage.
No parser-allocation peak or sustained-load measurement was made.

Imports were excluded; retrieval/authentication/admission and redacted structural
instrumentation were included. Native included the shared default scheduler and
extra in-memory shape diagnosis; baseline business/parser code stayed unchanged.
Both external safety guards used five requests/second, burst ten, finite deadlines
and one credential submission per approved run. Guard wait was zero in this pair;
native scheduler wait was not separately measured. One sequential sample per week
cannot establish general latency/throughput gains or alternative-layout coverage.
Private records were discarded and no consumer default/dependency changed.
