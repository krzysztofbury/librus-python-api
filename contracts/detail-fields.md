# Stable detail fields

`agenda_detail()`, `homework_detail()` and `attendance_detail()` return
`normalized_fields: tuple[DetailField, ...]` alongside bounded `fields` and
`notes`. Each immutable record contains:

- `key: DetailFieldKey | None`: stable semantic name, or `None` for an unknown
  label. Keys are specific to the page family, not a global label dictionary.
- `raw_label: str`: label from the existing bounded HTML parser. Whitespace is
  rendered/normalized; attendance's parser removes its trailing colon. This is
  not an exact HTML capture.
- `value: str`: complete parser-rendered text, including empty strings.

Source order is retained. Unknown labels are kept as distinct records, not
discarded or turned into guessed machine keys. Ancillary full-width notes remain
separate. Case, rendered whitespace and trailing colon differences do not change
known keys. Duplicate canonical labels or semantic keys raise `ParseError` before
the public result is cached. Raw labels and values are omitted from reprs.

The new metadata defaults to `()` when constructing a detail with its original
arguments, and does not participate in equality or hashing. Service reads always
populate it. Existing raw fields remain available. Dataclass serialization gains
the new field; exact consumer wire schemas require explicit field projection.

| Family | Established label | Key |
| --- | --- | --- |
| Agenda | Data | `date` |
| Agenda | Nr lekcji | `lesson_number` |
| Agenda | Nauczyciel | `teacher` |
| Agenda | Rodzaj | `category` |
| Agenda | Przedmiot | `subject` |
| Agenda | Sala | `room` |
| Agenda | Opis | `description` |
| Agenda | Data dodania | `published_at` |
| Homework | Zajęcia edukacyjne | `subject` |
| Homework | Temat | `topic` |
| Homework | Kategoria | `category` |
| Homework | Data udostępnienia | `published_at` |
| Homework | Termin wykonania | `due_at` |
| Homework | Treść | `content` |
| Attendance | Data | `date` |
| Attendance | Temat zajęć | `topic` |

This increment normalizes keys, not scalar values. A `date`, `published_at`,
`due_at` or `lesson_number` field still contains displayed text, not a validated
date, UTC timestamp or integer. Do not invent timezones or silently parse mixed
date/weekday text. Existing typed collection dates remain separate.

Provenance: school labels are established in [school reads](school-reads.md);
attendance date/topic labels have the existing independently authored detail
fixture and narrow contract. Other attendance tooltip labels are not assumed to
be detail fields. Original loopback cases in `tests/test_detail_fields.py` exercise
all three public operations, two independent accounts, cache reuse, unknown/empty
values, and ambiguous-label rejection. This extends offline evidence only.

MCP 2.0 can expose these records directly and make raw labels optional in its
wire projection. The raw data is retained for unknown-field fidelity, not as an
MCP 1.x compatibility layer. No upstream route or side effect is added.
