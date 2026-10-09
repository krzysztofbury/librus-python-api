# Class free days

`AccountClient.class_free_days(*, budget=None, max_age_seconds=0.0)` performs one
read-only gateway GET after authentication. It returns frozen `ClassFreeDays`
(`identity`, `items`, `observation`) and frozen `ClassFreeDay` records:

- `identifier`, `class_id`, `type_id`: opaque decimal strings from integer IDs.
- `date_from`, `date_to`: ordered civil `datetime.date` values, without timezone
  conversion or expansion into individual days.
- `lesson_no_from`, `lesson_no_to`: both absent (`None`) or both integer bounds.
  Their upstream values are retained. No all-day interpretation is inferred.

The parser accepts only an explicit `ClassFreeDays` array, including `[]`.
Missing arrays, malformed records, duplicate IDs, invalid/reversed dates,
partial/null lesson bounds and booleans in integer fields fail the whole read.
The collection is capped at 4096 records, IDs at 64 digits, and lesson bounds
at 0..99. These are local safety limits, not claims about upstream maxima.
Transport byte/deadline limits and the shared bounded parser pool also apply.
Envelope metadata and reference URLs are inert; no extra resource is fetched.
Type references are not translated into invented holiday names.

Sessions, caches, coalescing and budgets follow the shared account read contract.
The route is retry-safe only under the existing proven-session-expiry policy;
the guarded live checker forbids reauthentication. The weekly profile includes
this read. Its dedicated slot expectation is `any` (populated or empty), not
copied from a different independent login.

## Provenance and evidence

On 2026-10-09, an owner-authorized, guarded, structure-only capture returned a
populated array. Each item had integer `Id`, `Class.Id`, `Type.Id` and civil-date
strings `DateFrom`/`DateTo`; some items additionally had integer `LessonNoFrom`
and `LessonNoTo`. Reference `Url` fields, envelope `Url` and `Resources` were
observed but not followed. Only keys, types and counts were emitted. The
fixtures are independently authored with invented IDs, dates and inert URLs.

The branch's built wheel, installed outside its source directory, passed the
identity and class-free-days checks on four independent configured logins:
40 records and 10 requests per login, within a 12-request/90-second budget.
Only authentication, identity and class-free-days routes were allowed. This
qualifies these observed responses, not universal school/role coverage. Empty
collections and malformed shapes have offline evidence only.
