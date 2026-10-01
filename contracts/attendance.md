# Attendance business contract: 0.3.0.dev0

This first 0.3 increment enables attendance collections, fixed upstream views,
and inclusive civil-date windows. Detail retrieval, attendance-type metadata,
overall/subject frequency, and the remaining school-read families are pending.
This is a local development build, not a completed 0.3.0 release or live-qualified
attendance client.

## Baseline and provenance

The business reference is installed, unmodified librus-apix 1.5.3 and the existing
consumer's attendance, window, detail, and frequency requirements. Those references
were reviewed read-only. No implementation, documentation, fixtures, or captures
were incorporated. All parser and HTTP fixtures here are independently authored.
The reference distribution advertises MIT metadata but bundles a GPLv3 license;
it remains a requirements reference, not a dependency or source of code.

The grid classes, section concepts, tooltip labels, and view forms are
source-informed. Supported semantic semester labels are an explicit synthetic
contract, not an independently observed Librus layout. No attendance live request
was made for this increment. Authentication/grades evidence does not qualify it.

## Business matrix

| Flow | Baseline/consumer requirement | Native contract and status |
| --- | --- | --- |
| Collection | Inline attendance symbols and metadata from a semester grid | Immutable `Attendance` with identity, observation, items, displayed semesters, and selected view; offline runtime supported |
| Semesters | Baseline derives zero-based semester values from section order/reversal | Intentional difference: explicit labels map to 1/2, independent of position; reversed and single-second-semester fixtures supported. A consumer needing zero-based values must map explicitly, never use row position |
| All/week/last-login | Three upstream selections with attendance-specific form values | Strict `AttendanceView`; each selection has its own cache/coalescing key. Week/last-login are not locally inferred date windows |
| Civil dates | Dates may carry weekday suffixes | Required `date`, optional recognized Polish weekday suffix; malformed or missing dates fail. No guessed timestamp/timezone |
| Date windows | Consumer filters attendance inclusively | `attendance_window(start, end)` validates plain dates and at most 366 inclusive days before I/O, filters ALL, preserves order/observation, and adds no per-window cache |
| Metadata | Type, teacher, period, excursion, subject, topic | Raw labels and complete parsed tooltip metadata retained. Missing fields remain `None`; explicit empty raw strings remain empty, not invented defaults |
| Custom types | Baseline enum conversion can reject custom type IDs | Intentional difference: retain unknown raw labels. No numeric type ID or presence classification is invented from a symbol/label |
| Tooltips | BR-delimited fields or consecutive complete bold blocks | Both independently authored variants supported; topic colons preserved. Duplicate fields and invalid periods/booleans fail |
| Detail reference | Consumer expects a numeric legacy detail reference | Inert `detail_id` only for an exact approved-origin/root-relative numeric path in a recognized literal window call. No script execution or detail HTTP lookup. Consumer output shape/labels belong to its adapter |
| Empty data | Recognized semester sections may contain no records | Empty supported grids return an empty tuple; missing/ambiguous tables or headings fail, not empty success |
| Unknown layouts | Consumer must not lose records silently | Unknown headings/nonempty center cells, untitled anchors, and dated anchors outside the grid fail. Nested tables are unsupported, not double-counted |
| Session and traffic | Independent login permissions and bounded retrieval | One isolated session per login; all login hops and POSTs share service budgets. Identical concurrent reads coalesce only within one account/view and compatible budget |
| Side effects | Selection changes the upstream filter; login changes last-login state | One fixed POST per fresh collection, never automatically replayed, including expiry/denial/throttling/maintenance. Cache hits make no POST |
| Detail read | Separate detail page and consumer detail maps | Unresolved gate: no enabled detail route or public detail method |
| Overall frequency | Baseline counts excursion/presence/lateness over all attendance records | Unresolved gate: no native frequency method. Denominator, unknown-type policy, and ratio units require an explicit contract before enabling |
| Subject frequency | Consumer counts presence/lateness over selected known presence/absence/excused/exemption classes; zero denominator yields 100% | Unresolved gate: metadata-backed classification and explicit unavailable/zero-denominator behavior required. Native does not infer 100% from missing evidence |

## Bounds and owning proof

- At most 2048 entries, 8192 tooltip/script characters, 32 metadata chunks,
  and 1024 characters per rendered metadata key/value or symbol.
- Shared document byte/node/depth and parser-worker limits remain in force.
- At most three attendance collection cache entries per account, with the same
  explicit TTL, session invalidation, admission, deadline, and cancellation rules
  as existing grade reads. Date windows do not multiply cache entries.
- `tests/test_attendance.py` owns parser completeness, semester/unknown-value
  behavior, inert reference validation, form dispatch, view/window caching,
  four-login isolation/coalescing, request exhaustion, non-replay, and last-waiter
  cancellation through actual loopback HTTP. Common transport/scheduler tests
  continue to own the shared traffic envelope and lower-level failures.
- `contracts/upstream.openapi.yaml` describes the enabled POST's exact forms,
  side effects, evidence, and wire response. Detail-reference recognition alone
  does not enable a detail or gateway operation.

No live parity, performance improvement, sustained upstream capacity, populated
role/layout coverage, or consumer migration is claimed. A bounded installed-client
attendance smoke and equivalent baseline comparison require fresh authorization.
