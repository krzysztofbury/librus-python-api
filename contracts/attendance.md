# Attendance (0.3.0)

This 0.3 development increment enables attendance collections/views/windows,
numeric detail reads with fields/notes, gateway records, overall/semester ratios,
and per-subject ratios with bounded metadata resolution. A populated installed
native/reference-client pair completed on one context. Wider role/layout coverage, custom-type
semantics, populated last-login, and the remaining school families remain pending.
This is not a completed 0.3.0 release or general compatibility claim.

## Baseline and provenance

Unreleased detail-key semantics are documented in [detail fields](detail-fields.md).
Only the established date/topic detail labels are normalized; unknown fields
remain explicit. This adds no upstream route or expanded live-evidence claim.

The business reference is installed, unmodified reference client and the existing
consumer's attendance, window, detail, and frequency requirements. Those references
were reviewed read-only. No implementation, documentation, fixtures, or captures
were incorporated. All parser and HTTP fixtures here are independently authored.
The reference distribution advertises MIT metadata but bundles a GPLv3 license;
it remains a requirements reference, not a dependency or source of code.

The grid classes, section concepts, tooltip labels, and view forms are
source-informed, with narrow independent live evidence recorded in VERIFICATION.md.
The numeric `Okres 1` heading, full-width detail content, gateway references, and
one-day subject resolution were observed during bounded installed checks. Other
supported labels/layouts remain synthetic contracts, not populated qualification.

## Business matrix

| Flow | Baseline/consumer requirement | Native contract and status |
| --- | --- | --- |
| Collection | Inline attendance symbols and metadata from a semester grid | Immutable identity-bearing `Attendance`; populated all/week projection matches on one context, last-login matched empty only |
| Semesters | Baseline derives zero-based semester values from section order/reversal | Intentional difference: explicit labels map to 1/2, independent of position; reversed and single-second-semester fixtures supported. A consumer needing zero-based values must map explicitly, never use row position |
| All/week/last-login | Three upstream selections with attendance-specific form values | Strict `AttendanceView`; each selection has its own cache/coalescing key. Week/last-login are not locally inferred date windows |
| Civil dates | Dates may carry weekday suffixes | Required `date`, optional recognized Polish weekday suffix; malformed or missing dates fail. No guessed timestamp/timezone |
| Date windows | Consumer filters attendance inclusively | `attendance_window(start=None, end=None, view=AttendanceView.ALL)` validates optional plain dates, at most 370 days apart when both supplied; filters the explicit view, preserves order/observation/view, and adds no per-window cache |
| Metadata | Type, teacher, period, excursion, subject, topic | Raw labels and complete parsed tooltip metadata retained. Missing fields remain `None`; explicit empty raw strings remain empty, not invented defaults |
| Custom types | Baseline enum conversion can reject custom type IDs | Intentional difference: retain unknown raw labels. No numeric type ID or presence classification is invented from a symbol/label |
| Tooltips | BR-delimited fields or consecutive complete bold blocks | Both independently authored variants supported; topic colons preserved. Duplicate fields and invalid periods/booleans fail |
| Detail reference | Consumer expects a numeric legacy detail reference | Inert `detail_id` from approved-shaped literal calls; no script execution or eager lookup. Explicit detail reads validate numeric IDs. Consumer output shape/labels belong to its adapter |
| Empty data | Recognized semester sections may contain no records | Empty supported grids return an empty tuple; missing/ambiguous tables or headings fail, not empty success |
| Unknown layouts | Consumer must not lose records silently | Unknown headings/nonempty center cells, untitled anchors, and dated anchors outside the grid fail. Nested tables are unsupported, not double-counted |
| Session and traffic | Independent login permissions and bounded retrieval | One isolated session per login; all login hops and POSTs share service budgets. Identical concurrent reads coalesce only within one account/view and compatible budget |
| Side effects | Selection changes the upstream filter; login changes last-login state | One fixed POST per fresh collection, never automatically replayed, including expiry/denial/throttling/maintenance. Cache hits make no POST |
| Detail read | Separate detail page and consumer detail maps | `attendance_detail()` returns ordered fields and separately preserved full-width notes. Labels omit trailing colons; rendered word boundaries remain. Populated field projection matches on one context. Native notes are an intentional addition; baseline omits them |
| Gateway records | Typed numeric type/lesson references, civil date, semester, optional period/record ID | `gateway_attendance()` returns frozen records and strict `AttendanceKind`; duplicate supplied IDs, mismatched metadata IDs, malformed dates/references, and boolean semesters fail. Unknown type IDs remain raw/unknown |
| Overall frequency | Baseline counts excursion/presence/lateness over all attendance records | `attendance_frequency()` exposes first/second/overall counts and unrounded 0..1 ratios under explicit `overall` policy. Known-type calculation matches; any unknown type or zero denominator produces no ratio |
| Subject frequency | Baseline/consumer count presence/lateness over known presence/absence/excused/exemption; known other types excluded | `subject_frequency()` uses inclusive date selection before deduplicated numeric lesson/subject lookups. Ratios are unrounded 0..1; consumer converts to percentage/rounding. One populated civil day matches the baseline projection; full-year resolution remains budget-dependent/unqualified |
| Zero denominator | Baseline returns ratio 1 or percentage 100 even with no eligible records | Intentional difference: native returns `ratio=None` and counts, not invented attendance. Legacy projection is a consumer mapping choice only when unknown_count is zero. One empty-semester mapping was exercised |
| Type metadata | Baseline hardcodes familiar type IDs and can fail on custom IDs | Native preserves explicit raw IDs and uses a documented source-informed standard-kind policy. No separate custom-label metadata endpoint or guessed custom classification. Custom type frequency remains unavailable and live-unqualified |

## Bounds and owning proof

- At most 2048 entries, 8192 tooltip/script characters, 32 metadata chunks,
  and 1024 characters per rendered metadata key/value or symbol.
- Shared document byte/node/depth and parser-worker limits remain in force.
- A 64-entry account result cache bounds fixed collections, numeric details, and
  subject-frequency selections. A separate 256-entry lesson/subject metadata
  cache has a one-hour TTL; session invalidation clears both. Unique resolution
  is limited to 256 lessons/subjects per selection and the original request budget.
  HTML date windows add no cache entries; fresh gateway records remain fresh even
  when metadata is reused. Neither cache merges login contexts.
- Detail responses contain at most 32 fields/notes, 1024 rendered characters each.
- `tests/test_attendance.py` owns parser completeness, semester/unknown-value
  behavior, inert reference validation, form dispatch, view/window caching,
  four-login isolation/coalescing, request exhaustion, non-replay, and last-waiter
  cancellation through actual loopback HTTP. Common transport/scheduler tests
  continue to own the shared traffic envelope and lower-level failures.
- `contracts/upstream.openapi.yaml` describes the enabled POST's exact forms,
  side effects, evidence, and wire responses for all five attendance operations.
- `tests/test_attendance_frequency.py` owns strict gateway/detail parsing, differing
  numerator/denominator policies, unavailable zero/unknown states, numeric route
  guards, response-reference matching, actual detail/metadata HTTP, login isolation,
  session/TTL invalidation, cache capacity, and resolution budget exhaustion.

The successful comparison uses a declared legacy projection, not full domain
identity: zero-denominator markers and optional metadata defaults are mapped only
for comparison, and detail notes are excluded. Sequential login changes last-login
state. Unknown types, alternative labels/roles, full-year metadata workloads, and
sustained upstream capacity are not qualified. No consumer migration occurred.
Further credentialed work requires fresh bounded authorization.
