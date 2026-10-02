# Ordinary agenda and homework: 0.3.0.dev0

This increment implements `agenda(year, month)`, `agenda_detail(reference)`,
`homework(start, end)` and `homework_detail(reference)`. It does not consume
recent/read-once agenda state, submit assignments, download attachments, send
messages, migrate the consumer or publish a package.

## Business and domain policy

| Concern | apix/consumer reference | Native contract |
| --- | --- | --- |
| Agenda selection | Month/year strings, optional empty days | Explicit integer year 2001..2100 and month 1..12, fixed selection POST; every civil day retained |
| Event text | Positional BR splits, punctuation removal | Full bounded multiline plaintext, explicit span subject, preserved punctuation/order; title follows recognized header/standalone subject, otherwise first line |
| Lesson/time | Loose text matching and `unknown` strings | Only explicit number/time headers become typed values; missing values stay `None` and full text remains available |
| Tooltip | Label/value map, fabricated `unknown` values | Full ordered `metadata_text`, ordered label/value pairs and separate unlabelled notes; no fabricated teacher/description |
| Details | Label/value dictionary | Full bounded values, preserved labels including colons, empty fields, optional heading and ancillary notes |
| Homework window | Consumer defaults, at most 370 days between endpoints | Two explicit plain `date` values, ordered/inclusive, at most 371 civil days; no current-date/timezone default |
| Homework dates | Date/time cells joined into strings | Raw day/clock plus optional typed civil date/time; no UTC instant or inferred timezone |
| References | Agenda prefix/suffix, homework numeric strings | `SchoolReference(kind, identifier, account)` restricted to fixed numeric namespaces and owning account alias |
| Empty data | Calendar/empty-table markup | Complete month or explicit homework empty marker required; missing/ambiguous markup fails |
| Requests | Consumer-owned serialization/session wrapper | Shared bounded traffic, isolated lifecycle, explicit freshness, joined cancellation, no implicit detail fan-out |

`Agenda(identity, year, month, days, observation)` contains ordered `AgendaDay`
values with civil dates and event tuples. Each `AgendaEvent` retains `day`,
`title`, optional `subject`, full `text`, optional `lesson_number`/`at_time`,
tooltip text/fields/notes, and optional reference. Dates refer to the requested
selection, not an inferred timezone/login date. Recognized headers include
lesson/Nr/Numer labels and HH:MM clocks. Unknown headers remain text. Subjectless
multiline text keeps its first line as title unless an explicit header says otherwise.

`Homework(identity, start, end, items, observation)` contains ordered
`HomeworkItem` records: lesson, teacher, subject, category, assigned/due
`SchoolDateTime`, remaining rendered `extra_cells`, and optional reference.
Blank or `-` date/clock cells become `None` while retaining their raw string.
Invalid dates/clocks fail. Later columns are retained, not guessed as statuses.
The window is an upstream selection, not a local assigned/due-date filter.

Details return `SchoolDetail(identity, reference, title, fields, notes,
observation)`. Unknown labels are retained rather than forced into a fixed schema.
Nested tables, ambiguous/duplicate labels and active field content fail. Reprs
omit school text, date selections and resource identifiers.

References are inert typed data, not unforgeable authorization capabilities,
persistent cookies or globally unique student identities. A mismatched account,
kind, URL or nonnumeric identifier fails before credentials or dispatch. Only the
account's own session retrieves the fixed numeric route. Do not merge contexts
by student identity or reference equality. Legacy serialization/defaults and
notification persistence remain consumer responsibilities.

## Wire, bounds and proof ownership

- Four central routes bring the catalogue to 24 operations. Selection POSTs use
  exact `rok/miesiac` and `dataOd/dataDo/przedmiot/status` forms. Homework subject/
  status filters are fixed to `-1`. No arbitrary URL/form/prefix is accepted.
- Selection POSTs never automatically replay, even for proven expiry. Detail GETs
  may recover once within the original budget. Denial, throttle, maintenance and
  parser failures are not automatically retried.
- Calendars require complete unique numbered days and one TD per event row.
  Homework requires its recognized decorated table or exactly one `msgEmptyTable`
  marker, never contradictory populated/empty markup. Details require one table
  in one recognized background container.
- Limits: 2048 collection items, 1024 ordinary-field characters, 65536 full event/
  detail-value characters, 8192 raw/rendered tooltip characters, 32 tooltip chunks,
  64 detail fields/notes, 32 homework columns, 262144 aggregate rendered characters.
  Common body/tree/depth/parser-worker and request/deadline bounds also apply.
  Limit failures never silently truncate.
- Cache/coalescing keys include explicit month/window/reference and owning login.
  The 64-entry result cache and session invalidation apply. Explicit warm cache
  reuse makes no HTTP request; fresh reads remain the default.
- `tests/school_reads_support.py` owns original markup and exact loopback routes.
  `tests/test_school_reads.py` owns calendar/window/detail integrity, full text,
  optional values, unsafe references, bounds, four-login isolation/coalescing,
  form guards, non-replay, detail recovery, failed-parse non-caching, original
  budgets and joined cancellation. Common resource/scheduler proof is reused.

### Subsequent qualification attempt

The 2026-10-02 combined qualification follow-up did not close the live gates. Two
installed attempts stopped in completed lessons before these operations. A third,
reordered attempt dispatched one agenda POST and stopped on browser-projected event
count disagreement, before recording a successful comparison. Previous-month,
detail and homework operations were not reached. Each attempt had separate bounded
authorization and exactly one login; none was automatically retried.

Original offline markup with calendar days inside an outer layout table reproduces
the comparator dropping all inner event rows. Its ancestor filter incorrectly
treated layout rows outside each day as nested event rows. The browser projection
now enumerates rows within each day without that filter. This repairs the harness,
not the production agenda parser, and does not retrospectively identify the live
disagreement's cause. That private response had already been discarded.

The new harness retains fixed reason counters and code locations, keeps the failed
response in memory until sanitized diagnostics finish, and runs independent school
families before lessons. These are offline-tested improvements, not a completed
current-build live rerun or resolution of the earlier tooltip discrepancy.

## Provenance and qualification

Unmodified installed apix 1.5.3 and the read-only consumer inform requirements
and comparison, not copied code, fixtures or dependencies. The baseline's
advertised MIT metadata and bundled GPLv3 remain a provenance warning. No private
capture or record is retained in repository fixtures or evidence.

Authorized discovery completed two populated agenda months, two returned details
and an explicitly empty homework window in 14 requests. Initial discovery stopped
after 10 requests on a local HTML-comment scanning error. An original offline
reproduction preceded the guard fix and fresh authorization. Discovery is observed
structure and baseline/browser evidence, not installed public-API qualification.

Installed qualification remains partial. The first installed attempt stopped at
10 requests on reconstructed tooltip comparison. Original intermediate-note and
colon-spacing markup reproduced that helper limitation; the exact private live
cause was not established. Full ordered tooltip plaintext now avoids reconstructing
presentation by appending all notes last. A separately authorized final attempt
verified all five current-month events against same-response network-disabled
Chromium, then stopped after 11 requests on another unclassified baseline tooltip
difference in the previous month. That month parsed successfully, but complete
semantic comparison, installed details and installed homework were not reached.
The final title edge-case fix has offline proof only, not a complete live rerun.

Each attempt used one login and stopped without replay: 10 + 14 + 10 + 11 = 45
requests under the cumulative 48-request ceiling. No further login is authorized
by unused allowance. Comparisons use identical response bytes in memory; page
scripts/external requests are disabled in Chromium. These are not fully styled
interactive sessions or matched network benchmarks. Current-month title/subject/
default differences are not full serialized parity or universally diagnosed
baseline bugs.

Populated live homework/details, full installed live-family rerun, empty live agenda, wider
roles/layouts, alternate headers/dates and maximum-sized workloads remain
unqualified. See VERIFICATION.md and TODO.md. This is a local development increment,
not completed 0.3.0 coverage or production-consumer readiness.

## Offline comparison for variants without populated live data

The opt-in `tests/integration/test_school_reads_apix.py` adds 34 comparisons using
independently authored synthetic responses and an external unmodified apix 1.5.3
installation. No third-party source/fixture or private capture is copied. Baseline
Python files are checked against their distribution RECORD hashes. All comparisons
pass on source Python 3.14, installed wheel Python 3.14 and installed sdist Python
3.13. Ordinary CI remains independent of the external baseline and deselects these
tests. The baseline emits six BeautifulSoup deprecation warnings; its code is not
patched to suppress them.

| Synthetic coverage | Cases | Result |
| --- | ---: | --- |
| Homework common fields, two rows/order, missing clocks/dates, extra columns, explicit empty | 5 | Common legacy projections match. Raw date/clock strings reconstruct legacy strings; typed unavailable values and extra columns remain native additions |
| Homework class order, linkless rows, double-quoted references, BR text, invalid civil date | 5 | Classified departures: apix fails on reordered classes/linkless rows, drops double-quoted references, joins BR-separated words and retains invalid dates; native accepts supported structures or explicitly rejects invalid dates |
| Agenda/homework detail plain, empty, long, BR and paragraph values | 10 | Plain/empty/long common fields match; native preserves rendered boundaries where apix concatenates words. Heading/ancillary notes are native additions |
| Detail duplicate labels, missing container, active content | 6 | Both reject missing containers. Native rejects duplicates/active content; apix overwrites a duplicate or accepts a script-only value as empty |
| Empty agenda, inline/standalone subjects, clock, subjectless multiline title, tooltip notes/trailing break and BR alias | 7 | Counts/declared subjects and explicit number/time meaning match where comparable. Preserve punctuation, proper visible title and optional states rather than reproduce baseline omissions/inference |
| Public collections and returned details over real loopback HTTP | 1 | All four public APIs complete. Baseline consumes the identical returned response bytes and common fields match |

In the original clock case, native `at_time=09:30` corresponds to apix's `hour`
string; neither reports a lesson number. That is a representation difference,
not a reproduced clock bug. Original standalone-subject markup yields a blank
apix title; an inline comma-containing title loses its comma/space in apix. Native
retains the visible title. Tooltip notes and trailing empty chunks become invented
`unknown` entries in apix; a `<br>` alias remains embedded in its field value.
These reproduce synthetic differences, not the precise cause of any discarded
historical live mismatch.

A separate network-disabled Chromium 152 check agrees with installed native text
on 14 original positive cases: six agenda cells/tooltips, six detail pages and two
homework rows. Only markup/inline styles are available; this is rendered-text proof,
not a styled interactive school session. No school requests, real credential submissions,
consumer changes or production-code changes were made for this follow-up.

This closes the synthetic apix comparison and installed offline four-API path,
not the populated live-data/layout gate. The prior live accounting remains 45/48
requests and its approved logins remain exhausted. A new live run still requires
fresh authorization. See CONTRIBUTING.md for the opt-in comparison command.
