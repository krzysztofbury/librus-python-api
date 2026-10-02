# Grade contracts and provenance

The development increments implement `AccountClient.final_grades()`, `grades()`,
and `grades_window()`. The revised 0.2.0 release scope is grades-only; other
academic/school-read families move to 0.3.0. Delivery and qualification status
are recorded in VERIFICATION.md.

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
is replaced by arithmetic on grade symbols.

## Final-summary behaviour

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
- An empty single-cell, full-width spacer is ignored; nonempty or incorrectly
  spanned rows still fail. Shared HTML parsing accepts only the observed stray
  closing-tag repair category, not arbitrary recoverable parser errors.
- A valid all-unassigned page retains its subjects. No independently established
  no-subject marker is available, so missing subject rows fail instead of yielding
  a fabricated empty success. No live call, fallback source, or POST is involved.

The optional consumer adapter maps these library records to the unchanged four
legacy summary fields. The consumer alone maps unavailable columns to `-`; the
library preserves the distinction. Backend selection is programmatic, lifecycle
ownership is explicit, and native failures never trigger legacy HTTP fallback.

## Verification owners

`tests/test_final_grades.py` owns summary parsing, malformed, unassigned and
variant fixtures, bounds, scoped denial cooldowns and cache invalidation after a
re-login. `tests/test_account_reads.py` owns the shared read guarantees for every
operation: isolation, coalescing, caching, budgets, expiry recovery and wire
forms. The MCP stdio experiment from closed PR #38 was retired with that branch;
MCP serialization is proven again during the consumer migration.
All committed fixtures are synthetic. A bounded authorized summary observation
and in-memory parity check qualified a narrow layout, not all accounts. See
BENCHMARKS.md for measured gains, non-wins, and methodological limits.

## Inline grade collection increment

The installed `librus-apix` 1.5.3 metadata advertises MIT, but its bundled license
file is GPLv3. Treat its implementation as a requirements reference only, not a
source for MIT code, tests, fixtures, or documentation. The numeric/descriptive
concepts, filter field, and tooltip labels were reviewed as source-informed
requirements. No third-party material is incorporated. `grade_records.py` and
`tests/grade_records_support.py` are original implementations and examples.

An explicitly authorized bounded discovery used one login and one all-view POST,
with a 20-request cap; ten requests were dispatched. The POST changes the view
filter, not school records. The raw response stayed in process memory. Structural
diagnostics established two current-grade columns, inline dated metadata,
optional missing count/weight, and dates with a display weekday suffix. The
first ISO-only parser failed on that suffix; an original failing regression
preceded the narrow date fix. In-memory replay also established HTML comments
and the `Brak ocen` empty-cell marker; original regressions protect both. No
private capture or school value is a fixture.

The parser requires the summary table alignment contract plus exactly two
`Oceny bieżące` headers, assigning semester 1/2 in displayed order. Average title
labels and bounds live in config.py. Inline grade-box anchors preserve symbolic
grades and tooltip fields. Direct linkless `span.ocena` children use the parent
box metadata for descriptive entries. Expanded details are not counted twice;
revised inline entries remain distinct. Empty valid subject tables yield empty
grade tuples, but unknown nonempty grade markup is a parse failure. Descriptive-only
rows support expander, subject, two semester cells, and optional undated summary
columns. Nested descriptive anchors retain inline metadata; script links are removed.
Dated period/annual columns produce records with explicit kinds and metadata.
Predicted period and annual columns use their own kinds. Undated final values remain summaries,
not invented dated entries. Plain undated descriptive semester text is preserved
as `DescriptiveGradeSummary`, excluded from dated windows. A subject can appear
in both families; duplicate rows within a family still fail. Numeric averages are
not overwritten or duplicated by the descriptive family's unavailable columns.
Predicted-period labels extend the established semantic summary vocabulary in
original synthetic fixtures; they are not independently observed live layouts.

Missing metadata remains `None`. Raw school averages have explicit column
availability; empty/unassigned values do not become zero. Numeric weights require
explicit bounded nonnegative integers. Unknown metadata fields are preserved,
duplicates/malformed fields fail, and invalid dates are not skipped. Hrefs are
inert bounded data and are never fetched. No per-grade metadata requests are
needed for this supported layout; cache reuse uses the full collection's TTL and
session isolation. Bounds: 2048 entries, 8192 tooltip/href characters, 32 tooltip
fields, plus shared subject/column/text/tree/byte/deadline limits.

The service uses one fixed-form all/week/last-login POST per fresh collection. The operation is
classified `select_view`, not retry-safe; 401/login redirect and every ambiguous
failure must not replay it or credentials. Date windows validate before login,
filter inclusive civil dates over the same collection/cache, and exclude averages.
No last-login time, timezone-based week, grade arithmetic, or publication date is
inferred. View-specific caches and coalescing keys never substitute one selection
for another. Date windows always use the all-view collection. Publication blocks
preserve date, teacher, and paragraphs; multiple blocks are retained. Semester
stays unknown unless explicitly established by the title, unlike the baseline's
implicit first-period default. Unknown layouts fail closed.

`tests/test_grade_records.py` owns numeric/descriptive/average/window semantics,
metadata/date/bounds failures, unsupported-layout detection, fixed form delivery,
no POST recovery, shared default-policy four-login traffic, coalescing/cache reuse,
and cancellation. `tests/test_grade_view.py` owns credential-form destination
rejection before dispatch. Common transport/identity/scheduler tests retain their
existing guarantees. Numeric populated discovery is observed; populated
descriptive and numeric-average live coverage is not claimed by synthetic tests.

## Business comparison with librus-apix 1.5.3

This is the current business baseline, not a specification copied into the new
library. Live checks used unmodified apix with the same selected account and
completed all-view reads. Subject, raw grade, civil date, semester, category, and
teacher matched for the populated numeric variant. Both returned no descriptive
entries; that is not descriptive qualification. Full record parity is not claimed.

| Business flow | Baseline behavior | Library status / gap |
| --- | --- | --- |
| All-grade selection | POST selects all view | Fixed form, explicit side effect, no automatic replay; installed live path exercised |
| Semester/subject grouping | Two per-subject semester maps | Typed semester fields plus subject averages; consumer grouping stays outside the library |
| Symbolic marks | Raw strings, including nonnumeric marks | Original symbolic fixtures; populated common fields match live |
| Revised grades | Nested inline boxes can retain multiple entries | Original revised-entry fixture preserves both, avoiding expanded-detail duplicates; live corrected-entry variant pending |
| Count/weight/category/teacher | Inline tooltip metadata with defaults for missing fields | Present fields preserved; absent count/weight/category/teacher remain None rather than fabricated false/zero/empty |
| GPA / school averages | Reads school average cells, falls back to zero | Raw school text and column availability retained; populated numeric averages remain live-unqualified |
| Linkless descriptive entries | Parent-box metadata and descriptive spans | Inline and descriptive-only fixtures implemented; nested anchors supported; live population evidence required |
| Undated descriptive semester text | Non-grade-box text is omitted | Preserved as separate typed summaries; independently observed and offline verified; not an invented dated record |
| Separate semester descriptions | Publication header plus following description | Multiple blocks and paragraph boundaries preserved; missing semester remains unknown rather than first-period default; offline verified |
| Dated midterm/end-period marks | Baseline scans cells beyond current grades | Explicit dated period/annual and predicted kinds retain metadata; undated summaries stay separate; annual semester zero is a documented superset |
| Week / last-login filters | Upstream view-selection POSTs | Strict view enum, fixed forms, isolated cache/coalescing, no local timestamp inference; installed qualification recorded separately |
| Date windows | Consumer extension, not standalone apix operation | Inclusive civil-date filtering, shared collection cache, original offline boundaries and installed live cache check |
| Hrefs and rich descriptions | Raw link/description fields | Library preserves inert numeric hrefs and structured metadata, never dispatches a scraped URL; legacy formatting belongs to a future consumer mapping |
| No entries / unavailable columns | Empty maps and fallback values vary by layout | Valid subject rows with blank/Brak ocen current cells are empty; absent averages remain unavailable; unknown markup fails |

Grade-family completion is gated on implementing these declared contracts and
explicitly recording supported limits and qualification gaps,
not on a green numeric comparison or parser speedup. Later feature families need
the same business review, even where apix covers only part of the desired scope.

## Revised 0.2.0 acceptance and qualification

The declared grade contracts above are implemented and tested with original fixtures.
Source-informed support for dated descriptions, publication blocks, corrections, and
populated averages is not independently observed live qualification. These limits
remain explicit, not treated as populated checks passing on empty samples.

A separately approved four-context comparison dispatched 94 requests under a
128-request combined cap, at most 16 per implementation/context. Each implementation
was limited to one login and all/week/last-login view POSTs, with no automatic retry.
Three contexts completed the installed native/apix paths and matched the legacy
numeric projection (missing native metadata projected to baseline defaults only
in the private comparison). Dated descriptive collections were empty; populated
numeric averages, publications, dated period marks, and corrections were absent.

The second context failed native parsing after ten requests. Its remaining authorized
apix run completed the three views; all response bytes stayed in memory/private pipes.
Original regressions exposed undated descriptive text and the same subject in both
families before the fixes. Installed native parser replay then passed all views with
common numeric parity; the final-summary parser also passed those response bodies.
The fourth context independently completed the updated installed-client path with
populated undated descriptive summaries. This does not turn the second context's
failed full runtime run into a passed run. Its installed-client rerun needs new
authorization. The replay process was closed and private response data discarded.

Week/last-login forms were independently exercised. Last-login state is changed by
each authentication; sequential equality is sample evidence, not proof of identical
historical-login semantics. View caches never claim that upstream state is immutable.
This is a documented local-first grade delivery, not complete account/layout or
sustained-load qualification. Other school reads are outside 0.2.0.

## Observation card (not read)

Observed on 2026-10-02 on both student contexts: the grades page can contain a
separate table headed "KARTA SPOSTRZEŻEŃ". Each row has a coloured marker, a
free-text observation, an area (for example "OBSZAR I POZYTYWNE"), points, a
date and a type such as "Bieżąca". Detail links use
`/przegladaj_oceny/szczegoly/ksztaltujace/<id>`. `grades()` does not read this
table, and apix does not either. Every real grade box on those pages became a
record. The page also contains one hidden template box (detail ID `000000`),
which is correctly ignored.
