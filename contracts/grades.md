# Grade contracts and provenance

The development increments implement `AccountClient.final_grades()`, `grades()`,
and `grades_window()`. Delivery and qualification status are recorded in
VERIFICATION.md.

## Research boundary

The existing consumer's `get_final_grades` contract requires subject, midterm,
predicted annual, and annual summary strings. It maps an absent optional column
to `-`, retains unassigned subjects and descriptive values, and expects behaviour
summaries with merged body cells. Its existing parser/schema were inspected as
requirements references, not incorporated into this MIT library.

The fixed GET route was established by inspecting the reference client's URL definitions. No third-party implementation, fixture, or
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

The installed reference client metadata advertises MIT, but its bundled license
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

A guarded structure-only capture on 2026-10-12 established `nd.` as another
Sunday tooltip suffix. Civil-date parsing now accepts it alongside `ndz.`;
original metadata remains unchanged and unknown suffixes still fail. Synthetic
regressions exercise both spellings without retaining school values.

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

The behaviour row (`GRADE_MERGED_SUBJECTS`) may hold behaviour points in its
current-grade cells: one tooltip span whose only content is an integer (starting
points or a running total; the title is not interpreted), then optional point
entries in grade boxes whose only child links to a behaviour-points detail
(`BEHAVIOUR_POINTS_DETAIL_PATH_PREFIX`) with an integer label. Their tooltips
open with an unlabelled line and use `Data wystawienia`, not `Data`. Points are
not grades: such a cell is validated and contributes no records. Any other
content beside the points tooltip, or the points tooltip outside the behaviour
row, fails. Behaviour cells without a points tooltip keep the ordinary grade
rules. Observed offline on 2026-10-18 in two schools' pages, one with starting
points and entries and one with a running total alone; the guarded live gate is
pending.

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
for another. Date windows default to all-view and now accept an explicit view,
either missing boundary, and supplied dates at most 370 days apart. The result
retains its view and reuses only that view's collection. Publication blocks
preserve date, teacher, and paragraphs; multiple blocks are retained. Semester
stays unknown unless explicitly established by the title, unlike the baseline's
implicit first-period default. Unknown layouts fail closed.

`tests/test_grade_records.py` owns numeric/descriptive/average/window semantics,
metadata/date/bounds failures, unsupported-layout detection, fixed form delivery,
no POST recovery, shared default-policy four-login traffic, coalescing/cache reuse,
and cancellation. Common transport/identity/scheduler tests retain their
existing guarantees. Numeric populated discovery is observed; populated
descriptive and numeric-average live coverage is not claimed by synthetic tests.

## Business comparison with the reference client

This is the current business baseline, not a specification copied into the new
library. Live checks used the unmodified reference client with the same selected account and
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
| Date windows | Consumer extension, not a standalone reference-client operation | Inclusive civil-date filtering, shared collection cache, original offline boundaries and installed live cache check |
| Hrefs and rich descriptions | Raw link/description fields | Library preserves inert numeric hrefs and structured metadata, never dispatches a scraped URL; legacy formatting belongs to a future consumer mapping |
| No entries / unavailable columns | Empty maps and fallback values vary by layout | Valid subject rows with blank/Brak ocen current cells are empty; absent averages remain unavailable; unknown markup fails |

Grade-family completion is gated on implementing these declared contracts and
explicitly recording supported limits and qualification gaps,
not on a green numeric comparison or parser speedup. Later feature families need
the same business review, even where the reference client covers only part of the desired scope.

## Revised 0.2.0 acceptance and qualification

The declared grade contracts above are implemented and tested with original fixtures.
Source-informed support for dated descriptions, publication blocks, corrections, and
populated averages is not independently observed live qualification. These limits
remain explicit, not treated as populated checks passing on empty samples.

A separately approved four-context comparison dispatched 94 requests under a
128-request combined cap, at most 16 per implementation/context. Each implementation
was limited to one login and all/week/last-login view POSTs, with no automatic retry.
Three contexts completed the installed native/reference-client paths and matched the legacy
numeric projection (missing native metadata projected to baseline defaults only
in the private comparison). Dated descriptive collections were empty; populated
numeric averages, publications, dated period marks, and corrections were absent.

The second context failed native parsing after ten requests. Its remaining authorized
reference-client run completed the three views; all response bytes stayed in memory/private pipes.
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

## School-year archive (1.3.0)

`AccountClient.school_year_archive(*, budget=None, max_age_seconds=0.0)` reads
the fixed GET `/archiwum`. All earlier years are rendered on one page; there is
no year-selection request or session-view mutation. The parser ignores the
student-name header, chart containers and scripts. It never calls the chart AJAX
route or follows page links. Config and OpenAPI classify the read as retry-safe,
`SideEffect.NONE`; authentication still has its ordinary last-login effects.
Account identity, cache/coalescing, parser admission and original request/body/
deadline budgets are inherited from the shared read path.

The evidence is an owner-authorized read-only browser observation on 2026-10-07
of one early-education parent account. The page showed three earlier years;
menu counters were unchanged. A subsequent owner-authorized installed-wheel
check on two independent parent logins confirmed populated and explicit empty
archives, with notification counters unchanged. It also established the
post-footer chart-table repair described below. Fixtures and all record values
are independently authored synthetic examples. Older numeric layouts, populated
behaviour, more than three years and broader school coverage remain unqualified.

For a populated archive the parser requires one decorated archive table and one
achievement table, located by their semantic first-row headers. Ancestor/nested
tables fail with `PARSE`, except the observed trailing chart container below.
The archive has an empty leading TD plus one colspan-3 TD per year,
with span/b header markup; each year is a unique consecutive `YYYY/YYYY+1` pair
with a nonempty class name. An empty leading period cell precedes repeated
`okres 1`, `okres 2`, `koniec roku` columns. In order, the body contains:

1. Subject rows (TH label, three TD marks per year) and descriptive rows (TH
   label, one colspan-3 TD per year), with unique labels across both families.
2. One `Zachowanie` heading and one row with an empty TH, then a TD and a
   colspan-2 TD per year.
3. One `Nieobecności` heading, then exactly one row for each upstream label:
   `nieusprawiedlione`, `usprawiedlione`, `spóźnienia`. Spelling is intentional;
   case is ignored. Each count is one to six ASCII digits, not a computed sum.
4. One empty full-width footer row, with no subsequent archive rows.

Achievement headers are `Data`, `Klasa`, `Kategoria`, `Osiągnięcie`; rows hold
four TD cells with civil dates. A header-only table is an explicit empty list.
An optional footer must be a single empty full-width TD and the final row.
The live HTML leaves one bare nested table directly after the achievements
TFOOT, containing charts/scripts. This final sibling is ignored only when it
has no attributes, nested tables, rows, cells or table sections. Other nested
tables still fail. Scripts are never executed or chart endpoints requested.
Data cells allow plain text, with BR additionally allowed in descriptive and
achievement text. Tooltips, event handlers and other child markup are unsupported
rather than silently discarded. Whitespace is normalized; explicit BR boundaries
remain newlines. Missing tables, an unfinished section sequence, duplicate
years/labels, invalid dates/counts and contradictory footers fail with `PARSE`;
unexpected section rows, unknown labels, markup and geometry fail with
`UNSUPPORTED_CAPABILITY`.

`SchoolYearArchive` carries identity, observation, per-year `ArchiveYear` records
and `ArchiveAchievement` records. All school text and record containers are
excluded from reprs. Empty marks and `-` stay unchanged. The archive's `year_end`
mark is not asserted to be the same as `SubjectGradeSummary.annual`. Raw
`behaviour_first_semester` and `behaviour_second_semester_and_year_end` preserve
position without claiming populated semantics. Unlike current-grade parsing,
these explicitly named raw fields do not infer grade kinds from their contents.

The observed empty layout is a `warning-box information medium` DIV directly
inside `container-background`, with a `warning-head` DIV containing one
`warning-title` SPAN reading exactly `Brak danych` after normalization. With no
archive/achievement or decorated data tables, it returns empty tuples for both
collections. Duplicate notices and contradictions with data tables fail; a
missing table without that marker still fails with `PARSE`. Repeated school
years, including class changes, also fail with `PARSE`; no data is merged or
silently dropped.
Bounds are 16 years, 128 subjects, 32 descriptive rows, 256 achievements, 1024
characters per label/mark/class/category, 65536 per long text cell and 262144
rendered characters shared across both tables. Exceeding a bound raises `LIMIT`.
Shared HTML byte/node/depth and transport limits remain in force.

`tests/test_school_year_archive.py` owns parser values, geometry, malformed
layouts, limits and header-name exclusion. `tests/test_account_reads.py` owns
account isolation, coalescing, freshness, budgets, view-disabled handling,
safe-read recovery and exact GET-without-body delivery. Weekly fixtures cover
redaction and no-effect traffic. The weekly check reports only year counts and
uses a method-availability guard for older pinned library releases. Its committed
slot-0 expectation is empty, matching the dedicated live-check account rather
than assuming another independent login's populated history applies. The focused
installed live check passed on both layouts; a full weekly-profile run including
the new read remains separate.

### Per-grade detail finding (#40)

In the same recorded browser observation, the per-grade detail page contained
the mark, category, dates, teacher, subject, optional count flag, added-by field
and full comment already present in the list tooltip. A correction row used
TD/TD rather than TH/TD. No additional public field was established, so no new
route or per-grade read is enabled. This closes that discovery question for the
observed layout only; it does not establish every school's detail fields. The
observation card is covered in the formative section below (#26).

## Formative grades and the observation card (1.4.0)

Observed on 2026-10-08 on one parent login (owner-authorized, read-only,
structure only; notification counters unchanged). The grades page has an H3
"Oceny kształtujące" section with a `stretch decorated` table whose THEAD row
holds TD labels Przedmiot, Ocena kształtująca, Kategoria, Okres, Data and Typ.
Body rows have a subject TH, a cell with one formative detail link
(`/przegladaj_oceny/szczegoly/ksztaltujace/<id>`, link text is the full
assessment text) plus an empty `span.grade-box` marker, the category, the
period, an ISO date and the type; the footer is one empty cell.

"KARTA SPOSTRZEŻEŃ" (observation card) is a pseudo-subject: it is the
Przedmiot of formative rows and a subject row of the grade grid. Real subjects
carry formative items too. This corrects the 2026-10-02 note recorded here
for two student contexts, which read that subject cell as a table heading and
the integer column as points; the observed header is "Okres" (period).
Student-login rendering is not re-verified.

`GradeRecords.formative` returns `FormativeGrade` records from this table, and
`GradeWindow.formative` filters them by date. The grid already returned the
same items as ordinary records (same IDs); they are unchanged. Their computed
`formative_id` property identifies them. It is deliberately not a dataclass
field: grade notification identities hash the record's fields, and a new field
would change every stored identity.

Rules: exact header labels; a subject TH may span its group with `rowspan`
(only rowspan 1 was observed; grouping is synthetic coverage); exactly the
observed cell vocabulary; a hidden template row with ID `000000` is skipped.
Unknown markup, foreign links and formative links outside both known tables
are unsupported. Duplicate IDs, broken groups, periods other than 1 or 2,
invalid dates and nonempty footers fail. Formative rows count toward the
2048-record bound; assessment text is bounded at 65536 characters.

Compatibility note: 1.3.0 ignored this table. From 1.4.0 a recognised but
unknown formative layout (an empty-state row, markup inside the assessment
text, category-sort grouping beyond the supported rowspan form) fails the
whole grades read instead of returning partial output. The observed template
box is an ordinary grade link to detail ID `000000` in a separate hidden table
without THEAD; it is not formative and is still ignored.

Choices: a page without the section yields no formative items, because the
week and last-login views may not render it; the parser does not cross-check
the grid against the table. The view semantics of the table are not
established, so `formative` may include items outside the selected view. The
formative detail page added only "Widoczność" (visibility) beyond the table
and tooltip, so no detail request is enabled.

## Point grades (1.7.0)

Evidence: a parent account at a point-grade school returned `PARSE` from both
grade reads (relayed 2026-10-27, with a screenshot of the "Oceny punktowe"
table). A public issue report on another Librus client quoted one subject row
of that table, including the row expander ID, the tooltip labels and the
`/przegladaj_oceny_punktowe/szczegoly/<id>` entry link; two public browser
extensions refer to the same row IDs. The screenshot shows the current-grade
and "Wyn.I" header labels, percentage entries (90 and 44) and their
first-period result (67). No page was captured and no third-party code or
fixture is incorporated; the fixtures are original.

Cause: the table is a second `decorated stretch` table with two "Oceny bieżące"
headers. `grades()` requires exactly one such table and `final_grades()`
exactly one table with an annual summary title, so its presence made both
reads ambiguous.

Rules: a point table is a `decorated stretch` table whose subject rows carry an
expander image with ID `przedmioty_OP_<id>_node`. At most one is accepted. It
aligns on its single current-grade header row, not on an annual column, and
needs no ordinary table beside it. An ordinary grade table beside it still
needs its annual column. Point rows use the ordinary width, colspan,
nested-detail and behaviour rules; hidden detail rows mirror the entries and
are skipped. Entries keep their raw score and tooltip fields; "Licz do wyniku"
stays metadata and is not mapped to `counts_toward_average`. Every current
point entry must link to a point-grade detail, which is never requested, so an
unseen link layout fails instead of passing as a grade symbol. The computed
`point_grade_id` holds that detail ID; like `formative_id` it is not a field,
so notification identities stay unchanged. A period grade both tables show is
one record.

"Wyn.I", "Wyn.II" and "Wyn.R" header text (optionally with a space after the
dot) marks the period results, reported as `point_results`. They are on the
score scale, so they are never merged with the ordinary `averages`, even for a
subject both tables list. Only "Wyn.I" was observed; schools differ in which
result columns they show. In `final_grades()` a point table contributes
subjects when it has titled summary columns, and an absent column is
unavailable. For a subject in both tables each summary value is merged on its
own: an assigned value fills an unassigned one, equal values are one value and
two different assigned values fail. The subject bound counts ordinary and point
rows separately in `grades()` and unique subjects in `final_grades()`.

Observed page (1.7.1): the affected account's point table, relayed as HTML on
2026-10-27, has all eight titled columns (current grades, "Wyn." result and
period grade per period, "Wyn.R" and "R"), results as links whose tooltip
holds the point sums, hidden detail rows with nested tables, a merged
behaviour row and an empty footer cell spanning 20 columns. 1.7.0 failed it in
three places, each fixed for point tables only:

- A formative entry (`/przegladaj_oceny/szczegoly/ksztaltujace/<id>`) sits
  among the point entries; it is the mirror of its formative-table row and
  keeps `formative_id`.
- The empty footer row is skipped instead of read as a subject.
- Period titles break their own label with `<br>`, so a point table's title
  is read whole instead of up to its first break.

The same page's formative table holds line breaks in its assessment text,
which the formative reader now accepts in every table. The fixture
`observed_point_page` is original and follows this structure.

Limits: a point table with no subject rows is not recognised and still fails.
Point entries other than percentages (`(0-100)`) are not observed.

## Gateway descriptive grades (unreleased, issue #73)

Evidence: source-informed. The routes and JSON field names come from public
client code and the official grades page script, not from an observed
populated response. A guarded structure-only observation on 2026-10-12 found
the new-schema table (`table.newSchemaGradesByStudentTable`) with empty
`gradesCell` elements, and explicitly authorized, budgeted probes of the
PartialGrades read returned valid JSON with an empty `data` collection and a
pagination member on all four available logins. No populated record has been
observed, so live qualification of the mapping below is pending. No
third-party code, test or fixture is incorporated; the fixtures in
`tests/gateway_grades_support.py` are original and every value is invented.
The owner decided to implement the read from these requirements before a
populated capture; the first populated observation must be compared with
this section.

Page table: rows `tr.studentRow` carry numeric `data-subject_id` and
`data-user_id`, then an expander `td.micro.center.screen-only`, the subject
name and two empty `td.gradesCell` cells with `data-semester` 1 and 2. The
existing parser already reads these rows as descriptive subjects with no
grades and unavailable averages; that result is unchanged. The table's header
was not described; the fixture's header has no "Oceny bieżące" label, which
would make the table an ordinary grade table. In the all view the table must
be unique, have exactly that row geometry (otherwise `UNSUPPORTED_CAPABILITY`),
unique numeric subject IDs, nonblank names, at most 128 rows and one
`data-user_id` (otherwise `PARSE`). A semester cell the page already filled
would duplicate the gateway records, so it is `UNSUPPORTED_CAPABILITY`.

Reads: only `grades(view=GradeView.ALL)` on a page with the table requests,
after the grades POST, under the same session, budget, scheduler, parser pool
and deadline:

1. GET `/gateway/api/2.0/Auth/TokenInfo`: `UserIdentifier`.
2. GET `/gateway/api/2.0/Auth/UserInfo/{UserIdentifier}`: a parent login's
   `IdentifierOfStudentAssignedWithUser`; absent, null or empty means the login
   is the student and its own identifier is used.
3. POST `/gateway/api/2.0/Auth/DescriptiveGradingSystem/PartialGrades/Student/{id}`
   with exactly the JSON body `{}` and `Content-Type: application/json`.
   Callers supply no body; it is classified side-effect free but not
   retry-safe and is never replayed.
4. GET `/gateway/api/3.0/Auth/Subjects` and 5. GET `/gateway/api/2.0/Users`,
   only when step 3 returned records.

A fresh all-view read on such a page therefore makes three more requests, or
five when there are grades. Both identifiers must match `[A-Za-z0-9_-]{1,128}`
(the transport enforces it for these two routes only; every other `{id}` route
stays numeric); an upstream value outside it is a `PARSE` failure. Nothing is
cached beyond the grade collection itself.

Mapping to `DescriptiveGrade` (no new dataclass field, so notification
identities keep their shape):

- `subject`: the page's name for the Subjects row whose `numericIdentifier`
  equals `data-subject_id`, else that row's `name`; an unknown `subjectId` or a
  subject with neither name is `PARSE`.
- `raw`: `scaleValue.value`, else `content`; with neither the read fails
  rather than inventing a symbol. Blank strings count as absent.
- `day`: the first ten characters of `date`, which must be an ISO date or
  date-time. A date-time offset does not move the civil date.
- `semester`: 1 or 2; anything else, including booleans, is `PARSE`.
- `teacher`: "LastName FirstName" from Users for `teacherId`, or `None` when
  the user is not listed. `comment`: `comments`.
- `metadata`: only present fields, in this order: ("Obszar", area name),
  ("Treść", content), ("Dodał", author name for `addedBy`, omitted when not
  listed), ("Komentarz", comments), ("Skala", scale value).
- `kind` is `CURRENT` and `href` is `None`. The records follow the page's
  descriptive records in `GradeRecords.descriptive`, and grade windows filter
  them by `day` from the same cached collection.

Views: the page script narrows the week and last-login views by comparing a
`showGradesSinceDate` with an `addDate` field whose meaning is not
established. Returning every gateway record for those views would be wrong,
so they make no gateway request and contain none of these grades.
Notifications read the last-login view and therefore do not report them.

Failures: gateway HTTP errors propagate as the transport classifies them (401
session expired without a new login or replay, 403 access denied, 429/503
throttle and maintenance, other 4xx/5xx connection), and a non-200 or
non-JSON response is `PARSE`; the grade read never returns without these
grades. An empty `data` array is a valid empty result. Validation is strict:
wrong types, missing required fields, duplicate subject `identifier` or
`numericIdentifier`, and a repeated user `AccountId` with different names are
`PARSE`. Unknown extra keys are ignored.

Pagination: no paginated response was observed and the member's field names
are unknown. Every object beside `data` (to depth three) is checked; any of
these signals fails with `UNSUPPORTED_CAPABILITY` rather than returning a
first page: a total (`total`, `totalCount`, `totalItems`, `totalRecords`,
`totalResults`, `count`, `itemCount`, `itemsCount`, `recordCount`) above the
items received; a page count (`pages`, `totalPages`, `pageCount`,
`pagesCount`, `lastPage`, `numberOfPages`) above one; a non-empty next link
or page (`next`, `nextPage`, `nextUrl`, `nextPageUrl`, `nextLink`); a true
has-more flag (`hasMore`, `hasNext`, `hasNextPage`, `more`); or a page size
(`limit`, `perPage`, `pageSize`, `itemsPerPage`, `pageLimit`) filled by the
items with no total. Key matching ignores case and separators. The same rule
applies to Subjects.

Bounds: 2048 records counted together with the page's records, 8192
characters per text field (longer is `LIMIT`), 1024 subjects, 8192 users,
1024 characters per name, 128 per identifier, plus the shared transport,
body, request and deadline budgets.

`tests/test_gateway_grades.py` owns the table, JSON parsers, mapping,
pagination, wire (routes, methods, body, content type, identifiers), view,
failure, budget and bound behaviour. `tests/test_transport.py` and
`tests/test_attendance_frequency.py` hold the body and identifier rules. The
weekly live check declares the five routes for its grade checks, and
`scripts/live_capture.py` allows them, so a guarded populated capture can
qualify this section.
