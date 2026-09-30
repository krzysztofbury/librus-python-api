# Grade summary contract and provenance

The first 0.2.0 development increment implements `AccountClient.final_grades()`.
It does not implement individual grades, date windows, GPA, or descriptive grade
collections, and is not a completed 0.2.0 release.

## Research boundary

The existing consumer's `get_final_grades` contract requires subject, midterm,
predicted annual, and annual summary strings. It maps an absent optional column
to `-`, retains unassigned subjects and descriptive values, and expects behaviour
summaries with merged body cells. Its existing parser/schema were inspected as
requirements references, not incorporated into this MIT library.

The fixed GET route was established by inspecting the installed MIT-licensed
`librus-apix` 1.5.2 URL definition. No third-party implementation, fixture, or
documentation was copied. This is source-informed work, not a clean-room or
independently observed live-behaviour claim. `grade_parsers.py`, test markup, and
wire tests are original. The synthetic layout deliberately uses different column
ordering, element types, values, and noise than the research material.

JSON remains a candidate for individual records and metadata. No JSON field or
endpoint is enabled here based on a guessed schema, and no school-provided average
is replaced by arithmetic on grade symbols. Numeric/descriptive collections and
their scope/date rules need their own contract/evidence increment.

## Enabled behaviour

- One GET under the existing shared scheduler, operation budget, parser pool,
  session recovery, coalescing, freshness, and login isolation.
- One unique semantic header row with the annual column; header widths include
  colspans and the two leading body-only cells. Optional midterm/predicted columns
  report unavailable rather than inventing values. Header labels and limits live
  in `config.py`; the matching raw HTML operation lives in `upstream.openapi.yaml`.
- Available empty strings, `-`, numeric symbols, and descriptive labels are
  preserved as whitespace-normalized text. There is no grade calculation or
  fabricated publication date, subject ID, or detail reference.
- At most 128 unique subject labels, 64 expanded columns, and 1024 characters per
  summary/subject/header title. Common HTML node/depth and transport/parser byte
  bounds still apply. These are conservative client limits, not school guarantees.
- Body colspans are accepted only for the evidenced behaviour subject. A merged
  cell cannot stand for multiple different summary fields. Unsupported rowspans,
  short/long rows, duplicate labels, and ambiguous tables fail explicitly.
- Nested expanded-detail wrappers and the narrow inline `Ocena` label variant
  do not become subjects. Unexpected content in a nested subject row is rejected.
- A valid all-unassigned page retains its subjects. No independently established
  no-subject marker is available, so missing subject rows fail instead of yielding
  a fabricated empty success. No live call, fallback source, or POST is involved.

The optional consumer adapter maps these library records to the unchanged four
legacy summary fields. The consumer alone maps unavailable columns to `-`; the
library preserves the distinction. Backend selection is programmatic, lifecycle
ownership is explicit, and native failures never trigger legacy HTTP fallback.

## Verification owners

`tests/test_final_grades.py` owns summary parsing, malformed/unassigned/variant
fixtures, bounds, public wire requests, account isolation, scoped denials, cache
reuse, and shared-budget expiry recovery. Existing transport/scheduler/identity
tests continue to own common lifecycle, cancellation, decompression, and rate
guarantees rather than duplicating them for each endpoint.

The opt-in `tests/integration/test_mcp_reads.py` workload is parameterized for
identity and final summaries. It owns real MCP stdio serialization, legacy optional
column mapping, four independent logins for the same represented student, and
one scoped denial. Ordinary GitHub CI remains independent of the consumer checkout.
All fixtures are synthetic; live layout/account compatibility remains unverified.
