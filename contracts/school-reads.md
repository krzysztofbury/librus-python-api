# Agenda and homework (0.3.0)

Calls: `agenda(year, month)`, `agenda_detail(reference)`, `homework(start, end)`
and `homework_detail(reference)`. These do not consume the read-once "added since
last login" agenda, submit work, download attachments or mark anything as read.

## Agenda

- Selection: the fixed POST form `rok`, `miesiac` (two digits), with year
  2001..2100 and month 1..12. It is a view selection and is never replayed.
- Every civil day of the month is returned, empty days included. A day is a
  `kalendarz-dzien` block with exactly one numbered marker; the count must match
  the month.
- Each event is one table cell, kept as full multiline `text`. The `subject` is
  the single `span`, if any. `lesson_number` and `at_time` are filled only from
  an explicit header (`Lekcja: 2`, `Nr lekcji: 2`, `09:30`). `title` is the visible
  line after the header or subject.
- Tooltip (`title` attribute): `metadata_text` holds the complete rendered text.
  `metadata` holds labelled fields and `metadata_notes` unlabelled lines.
  Observed labels are `Nauczyciel`, `Opis` and `Data dodania`. A description can
  span dozens of lines, some containing colons. Lines after `Opis` therefore
  continue that field until the next known label, so they never become fields
  of their own. Lines are capped at 256, under the 8192-character tooltip bound.
- An agenda cell may carry only a detail handler (`/terminarz/szczegoly/<id>`).
  Any other handler, such as a link to the read-once view, is unsupported.

## Homework

Observed table (`table.decorated.myHomeworkTable`), mapped by header label:

| Header | Cells | Field |
| --- | --- | --- |
| Przedmiot | 1 | `subject` |
| Nauczyciel | 1 | `teacher` |
| Temat | 1 | `topic` |
| Kategoria | 1 | `category` |
| Data zadania | 2: date, weekday | `assigned_on` |
| Termin wykonania | 2: date, weekday | `due_on` |
| Status przesyłania rozwiązania | 1 | `submission_status` (raw, optional column) |
| Opcje | 1 | `reference`, `marked_done_at` |

- Each date must be ISO and match the weekday label in the next cell, which
  guards against column drift. An unknown header is
  `UnsupportedCapabilityError`; a missing required column fails.
- The options cell has a preview button
  (`otworz_w_nowym_oknie('/moje_zadania/podglad/<id>', ...)`) that supplies the
  reference, and a "mark as done" button, which is ignored and never invoked.
  An optional image titled `Zadanie oznaczono jako wykonane (YYYY-MM-DD, HH:MM)`
  supplies `marked_done_at`.
- Window: the form is `dataOd`, `dataDo`, `przedmiot=-1`, `status=-1`. The page
  says the range must fit within one month, and its date picker caps `dataDo` at
  `dataOd` plus one month. Live: 1 Sep to 1 Oct was accepted; 1 Sep to 31 Oct and
  1 Jan to 31 Oct returned "Wybrano nieprawidłowy zakres daty." next to the
  empty marker. The library rejects longer windows before any request. If the
  notice appears anyway, it raises `InvalidInputError`.
- Empty result: exactly one `msgEmptyTable` marker ("Brak wpisów"), no homework
  table and no page notice. Any notice next to an empty marker fails.

apix maps the same cells as `lesson` (actually the subject), `subject` (actually
the topic) and joined date and weekday strings. The previous native model copied
that labelling, and its synthetic fixtures invented clock cells, so populated
pages failed live. A consumer mapping to the legacy MCP output must translate
the fields explicitly.

## Details

`agenda_detail` and `homework_detail` take the `SchoolReference` returned by the
same login. The kind, account and numeric identifier are checked before any
request. Each returns `SchoolDetail`: an optional heading, ordered label/value
`fields` with labels exactly as shown, and full-width `notes`.

Observed labels:

- Agenda detail: Data, Nr lekcji, Nauczyciel, Rodzaj, Przedmiot, optional Sala,
  Opis, Data dodania.
- Homework detail: Zajęcia edukacyjne, Temat, Kategoria, Data udostępnienia,
  Termin wykonania, Treść.

Detail GETs may recover a proven expiry once. The web UI pairs a homework preview
with a separate `checkAsRead` call; the library does not make it. Live
verification opened only an assignment already marked done.

## Limits

2048 items per collection, 1024 characters per ordinary field, 65536 per event or
detail value, 8192 per tooltip and 256 tooltip lines, 64 detail fields, 32
homework columns, and 262144 rendered characters per page. Exceeding a limit
raises `LimitError`; nothing is truncated.

## Evidence

Live on 2026-10-02, two student contexts:

- Agenda: two months each (5 and 13 events, and 3 and 3 events) plus detail
  pages. All match Chromium's rendering of the same bytes, including tooltip text
  and the 33-line meeting description.
- Homework: a populated month (2 assignments, one marked done) and its detail,
  plus empty months. All match Chromium.

Parser tests: `tests/test_school_reads.py`. Shared read guarantees and exact wire
forms: `tests/test_account_reads.py`. See [VERIFICATION.md](../VERIFICATION.md).
