# Timetable business contract: 0.3.0.dev0

This local development increment provides explicit civil-week timetable reads.
It is not completed 0.3.0 school coverage or a consumer migration. Discovery and
installed evidence are recorded separately in VERIFICATION.md.

## Requirements and provenance

The business reference is the installed, unmodified librus-apix 1.5.3 timetable
function and the read-only consumer's Monday-week selection and nested-day output.
No reference code, docs, fixture markup, or school capture was incorporated. That
distribution advertises MIT metadata but bundles GPLv3; it remains a requirements
reference, not a dependency. All fixtures and parsing here are independently authored.

Bounded discovery on one approved context established the named civil-date/time
attributes, seven-day grid, repeated slot ID, period/recess row shapes, populated
lesson blocks, and change notices without tooltip metadata for two weeks.
Focused baseline diagnosis established two numeric prefix markers around the
time header. Mirrored values must agree; conflicting period markers fail.
Multi-group entries and populated replacement tooltips remain source-informed
offline contracts until independently observed in a completed runtime workload.

## Business compatibility matrix

| Capability | Baseline/consumer behavior | Native contract and deliberate differences |
| --- | --- | --- |
| Week | Consumer accepts a Monday string or infers current week in its school timezone | `timetable(monday: date)` requires an explicit plain Monday with representable Sunday. String parsing and default-week timezone policy stay consumer-owned |
| Selection | One fixed week-selection POST | Central route and exact `tydzien=YYYY-MM-DD_YYYY-MM-DD` form; `select_view` side effect, never replayed automatically |
| Days/slots | Seven nested day lists, including blank slots | Identity-bearing `Timetable` with seven explicit `TimetableDay` dates and immutable periods; no dropped weekend or empty slot |
| Period/time | Number, raw date/from/to strings, locale weekday string | Explicit numeric period, `datetime.time` interval and owning civil day; no invented timezone/weekday text. Consumers render civil/time strings and weekday labels |
| Lessons | Multiple subject/teacher blocks joined with slash delimiters | Ordered distinct `TimetableLesson` entries preserve grouping and subject hyphens; teacher/classroom remains combined rendered text with normalized whitespace, absent as None, not guessed identities/rooms. Same-response Chromium validation confirms native values: baseline differs in whitespace and one incorrect string per week. Do not reproduce that baseline string for exact parity |
| Changes | Raw notice labels with empty marker or mapped replacement fields | Ordered `TimetableChange` raw labels and complete optional label/value metadata, including unknown labels. No guessed cancellation/substitution enum. Consumers own legacy dictionary/key mapping and empty defaults |
| Recess | Optional next-recess raw from/to values | Optional typed clock pair associated with its preceding period, preserving valid reported clocks including zero/inverted pairs. No inferred duration or constraint on lesson ordering. Absence remains None |
| Attribute order | Baseline assumes date/from/to attribute insertion order | Native reads named attributes and checks explicit date coverage, independent of insertion order |
| Unsupported layout | Baseline has positional assumptions and exceptions | Missing/ambiguous grids, dates outside requested week, repeated weekdays/periods, overlaps, malformed metadata, nested tables and unconsumed slot text fail without partial/empty fabrication |
| Recovery/cache | Existing client session and mutable selection | Shared service budgets, isolated sessions, coalescing/cache keys include Monday. Explicit bounded reuse avoids POSTs. Expiry invalidates but does not replay a selection |

## Bounds and proof ownership

- Shared transport byte limits, finite request/deadline budgets, global rate/
  concurrency/queue limits and parser node/depth limits remain in force.
- At most 32 periods, seven unique dated slots per period, 16 lessons and 16
  notices per slot. Rendered fields are at most 1024 characters; existing bounded
  tooltip parsing preserves metadata with finite raw-size/field limits.
- Week results use the existing 64-entry account/session result cache. Date
  identity, TTL, admission, cancellation and invalidation are service-owned.
- The upstream reuses `timetableEntryBox` as an ID for all slots. Only that exact
  duplicate-ID parser error is permitted for timetable input. Other IDs and
  unsafe HTML repairs remain rejected; semantic slot/date uniqueness is separate.
- No arbitrary authenticated URL, script evaluation, timetable detail retrieval,
  read-once agenda consumption, account switching, or metadata fan-out exists.
- `tests/timetable_support.py` owns original markup and exact-form loopback HTTP;
  `tests/test_timetable.py` owns grouping, notices, blanks/recesses, validation,
  limits, four-login coalescing/isolation, distinct-week cache behavior, budgets,
  credential/form guards, expiry/denial/throttle/maintenance non-replay, and cleanup.
- The nineteenth OpenAPI operation documents the matching raw upstream HTML
  request/response, side effect, policy, provenance and evidence limits.

## Qualification limits

The final installed native/apix pair completed two populated weeks and native
cached-week reuse. Dates/times/numbers/recesses/subjects/notices match the legacy
projection. Fresh same-response diagnostics classify combined teacher/classroom
differences as 28 whitespace-only strings plus one baseline/rendered-text disagreement
per week. Native agrees with normalized Chromium text in all 91 slots per week;
no native teacher/classroom defect was observed. Preserve that output, not exact
baseline strings. Three original lesson-boundary cases protect whitespace, line
breaks, nonbreaking spaces and subject/teacher/room hyphens. An original synthetic
replay separately demonstrates apix subject-hyphen contamination; the exact cause
of its one live non-whitespace error is not established and must not be inferred.
The resolved native-correctness gate is distinct from exact baseline parity.
Browser checks used captured markup and inline styles only, disabled page scripts
and blocked external requests, not a separate interactive login or full styled UI.
Installed qualification status belongs to VERIFICATION.md. Alternative roles,
multi-group/replacement metadata, wholly empty upstream weeks, changed cell order,
locale/encoding variants and sustained load require separate evidence. Pure civil
times are not UTC instants and cannot silently imply daylight-saving conversions.
No consumer changes or PyPI publication are part of this increment.
