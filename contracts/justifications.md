# e-Justifications list

`AccountClient.justifications()` reads the list of absence justifications a
parent sent through the Synergia e-Justifications module
(`GET /eusprawiedliwienia`, operation `justifications`). Added for issue #137;
first released in 1.10.0.

## Evidence

Structure-only observation on 2026-11-13 of four owner logins (two parent, two
student, covering two students): tags, classes, attributes, label names and
value shapes, never values. Nothing was submitted, no filter was posted and
nothing beyond the list page was opened. The fixtures in
`tests/justifications_support.py` are original and were written from that
record, not from a captured page; the live check is what catches drift.

## Request

One GET with no query or form, `SideEffect.NONE`, retry-safe. Not used:

- the filter form's POST (`requestkey`, `usprawiedliwienia_filtr`, `data_od`,
  `data_do`, `status`). Its effect on the session was not observed, and it
  would be a `SELECT_VIEW` request;
- `/eusprawiedliwienia/dodaj` or any submission;
- attachments.

## Window

Without a POST the page filled `data_od`/`data_do` with the last month and
selected no status, on both parent logins. `Justifications.window_start` and
`window_end` come from those inputs (both required, `YYYY-MM-DD`, start not
after end). Every observed entry was inside the window, so whether the page
hides older entries is not established: treat entries sent before
`window_start` as possibly missing, not as absent. A page whose status select
has an option other than `0` (wszystkie) selected is refused with
`UNSUPPORTED_CAPABILITY`, because a list narrowed to one status would be a
silently partial result.

## List

The list is the one `table` whose classes include `decorated stretch center`
(the filter table is `decorated filters small center`). Required:

- `thead`: one row of seven cells (`td` observed), labels in this order:
  `Załącznik`, `Okres usprawiedliwienia`,
  `Liczba usprawiedliwionych nieobecności`, `Treść`,
  `Powiadomieni nauczyciele`, `Data wysłania`, `Status`
  (`config.JUSTIFICATION_HEADERS`). Any other label, order or count is
  `PARSE`.
- each other row outside `tfoot`: seven cells, no `colspan`/`rowspan`.
- `tfoot`: only empty rows (one empty `td colspan="7"` observed).

Per entry (`Justification`):

| Cell | Observed shape | Field |
| --- | --- | --- |
| Attachment | empty on every observed entry | `has_attachment`: true when the cell has any element or text; its markup is unknown and nothing in it is read or followed |
| Period | in `<b>`: `od YYYY-MM-DD do YYYY-MM-DD`, or `YYYY-MM-DD, lekcje: N, N` / `YYYY-MM-DD, lekcja: N` | `start`, `end`, `lessons` (empty for a range; page order for one day). `lekcji`, the Polish plural for five or more, is accepted too (not observed). Start after end, duplicate lessons, or any other shape is `PARSE` |
| Count | integer | `absence_count` |
| Content | parent's free text | `content`, multiline, at most 8192 characters |
| Notified teachers | names separated by `, ` and `<br>` | `teachers`, page order, at most 64 |
| Sent | `YYYY-MM-DD HH:MM:SS` | `sent_at`, a naive `datetime` in Synergia's local time; no timezone is inferred |
| Status | `wysłane`, `usprawiedliwione`; a decided entry adds ` (` name `)` | `status` (`SENT`, `JUSTIFIED`, `REJECTED`) and `decided_by` |

`odrzucone` (`REJECTED`) is source-informed: it is a filter option, not yet
seen on an entry. `wszystkie` is the filter's "all" option, not an entry
status. Any other status word is `PARSE`. Limits: 512 entries, 262144 total
characters (content, teachers and deciders); over a limit is `LIMIT`.

## Explicit empty list

A login without entries was recorded earlier with an explicit empty row, but
its exact markup was not captured. Accepted as empty: no entry rows, or
exactly one row holding one non-empty cell with `colspan="7"` (its text is not
read). This rule is not observed live; the live check will show it.

## "Brak dostępu"

Both student logins got a 200 page whose only heading is `h2.inside`
"Brak dostępu" and which has no menu: the same page Synergia gives a session
it no longer knows (`LOGGED_OUT_HEADING`, `LOGGED_IN_PAGE_MARKER`), although
the session was live. On this route the two look identical, and the login's
role is not known from what the library reads (`Identity` has an owner and a
student for every login), so the read cannot skip the request for a student.

Instead, when the list request gets that page:

1. One GET of `/informacja` (`student_information`) checks the session.
2. If that page is also the logged-out page, the session is gone: the usual
   recovery applies (sign in again once and read the list again; in a session
   just signed in, `PARSE` and the cooldown, as for any read).
3. Otherwise the read fails with `UNSUPPORTED_CAPABILITY`. The session is
   kept, nothing is cached as a result, and later calls in the same session
   fail the same way without a request. A new session (after any sign-in)
   asks once again.

This applies equally to a parent login that gets the page, for example where
a school has switched the module off. `UNSUPPORTED_CAPABILITY` was chosen over
`ACCESS_DENIED` because the latter starts the account cooldown and is used for
identity mismatches.

## Diagnostics

The seven header labels are in the failure-diagnostics allowlist; cell text,
names and dates are masked. `python -m librus_python_api.inspect_page
justifications FILE` reports `denied_page` and `entries`.

## Live check

`justifications` runs in the weekly profile with reads `justifications` and
`student_information`. Slot 0 (parent) expects `any`; slot 1 (student)
expects `unavailable`.
