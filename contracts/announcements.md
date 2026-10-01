# Announcement reads: 0.3.0.dev0

`await account.announcements()` is one ordinary HTML collection GET, not a
mark-read operation, agenda/event consumption, attachment request, or consumer
migration. It returns immutable `Announcements(identity, items, observation)`.

## Domain and compatibility

Each `Announcement` includes `title`, `author`, `date_text`, `published_on`,
`content`, and `reference`. Order and repeated items are preserved. Reprs omit
school text and references. There are no implicit detail requests or link/script
execution. Date text must be a valid ISO civil date; the original text is retained
alongside `datetime.date`. No timezone or publication time is invented.

| Concern | apix/consumer baseline | Native policy |
| --- | --- | --- |
| Title/author/date | HTML strings; title source whitespace preserved | Complete bounded plain strings, whitespace normalized; missing title/author/date fails rather than inventing values |
| Body | Full first-TD text from the third data row | Full bounded plain text with paragraph/list/BR line boundaries; source whitespace normalized and inline word joins preserved. Empty body remains empty; never truncate |
| Field mapping | Three positional row values | One THEAD title and semantic TH/TD fields, independent of row order; duplicate, missing, unknown and unparsed nonempty rows fail |
| Civil date | Raw string | Both original ISO date text and typed civil date. Invalid dates fail; unqualified alternate formats report unsupported capability |
| References | No upstream ID returned | Explicit account-alias-scoped content fingerprint, not a fabricated upstream resource ID |
| Empty | Broad warning-container shape means empty | Specific configured no-announcement phrase and container structure. Missing markup or unrelated warnings do not become empty success |
| Recovery/cache | Existing client session | Shared service budgets, isolated login/session cache/coalescing, explicit freshness and at most one proven-expiry safe-read recovery |
| Serialization | MCP title/author/description/date strings | Consumer-owned mapping from content/date_text; no MCP response-model dependency or notification persistence |

The observed HTML supplies no IDs or numeric announcement links. `reference` is
`content-sha256:` plus a length-framed SHA-256 digest of the fixed schema version,
configured account alias, title, author, date text and canonical content. It is
stable for unchanged canonical fields in the same configured scope, independent
of page/field order or login session generation. It is not an upstream ID, URL,
authentication token, change-tracking guarantee or globally shared identity.
Edits and account-alias changes produce a new reference. Identical copies share
one reference but remain distinct items. Consumers must keep login identity with
references and never use equality to merge security contexts or permissions.

Native plaintext is intentionally not exact apix whitespace. Reference-parser
bugs are not a reason to corrupt native data. Compare normalized rendered content
on identical responses, as required by CONTRIBUTING.md.

## Structure, bounds and proof ownership

- Fixed route and twentieth OpenAPI operation live in config.py and
  upstream.openapi.yaml. No arbitrary URL/read-once/write operation is enabled.
- Recognize `decorated big center printable margin-top` tables. Title is one
  THEAD TD spanning one/two columns; author/date/content are line0/line1 TH/TD
  rows. Observed labels are Dodał, Data publikacji and Treść. Autor/Data aliases
  and alternate row order are original offline requirements, not live variants.
- A blank footer is allowed. Nested tables, active content, unknown fields,
  contradictory empty markers, malformed spans/dates, unsafe parser repairs and
  malformed recognized siblings fail the collection without partial output.
- Limits: 256 items; 1024 characters per title/author/date; 65536 content characters
  per item; 262144 total rendered characters; common body/tree/depth/admission and
  original request/deadline limits. Limit errors do not silently truncate content.
- Bodies are plaintext, not rich HTML, attachment data or link targets. Page
  scripts/forms are not executed. Unsupported active content in fields fails.
- Reuse the existing 64-entry account result cache and default fresh-read behavior;
  session invalidation clears cached announcements. No detail/metadata fan-out.
- `tests/announcements_support.py` owns independently authored semantic markup
  and exact GET loopback fixture. `tests/test_announcements.py` owns integrity,
  long text, boundaries, references, empty/malformed/bounded cases, four-login
  isolation/coalescing, freshness, safe recovery, original budgets/form guards,
  failed-parse non-caching, and joined cancellation cleanup.

## Provenance and qualification

Installed unmodified apix 1.5.3 and the read-only consumer are requirements/
comparison references, not dependencies or copied implementation/fixtures.
The installed apix distribution's advertised MIT metadata and bundled GPLv3
remain a provenance warning. No source, docs, fixtures or capture was copied.

One authorized discovery and one installed-native qualification each used one
login and ten HTTP requests on the same context, 20 of a fresh 32-request cap.
The page contained seven complete announcements, including bodies above 1024
characters. Unmodified apix parsed the same response offline; Chromium rendered
the same markup with scripts and external requests disabled. Native/apix/browser
agree on all items and normalized title/author/date/content. Three baseline
titles and seven body strings differed only in whitespace; native body line
formatting also differs from browser presentation without changing words.
Private pages/results were discarded after in-memory classification. Native
cached reuse made no extra HTTP request. This is populated installed retrieval,
not a full styled/interactive UI, independent apix network workload, sustained
capacity benchmark, or universal role/layout qualification.

Empty marker phrases/layout, reordered/aliased labels, nested/rich/active content
rejection, duplicate items, reference edits and configured bound rejection have
offline proof only. Maximum-sized populated workloads, wider roles, changed date
formats and alternate upstream IDs
remain unqualified. Consumer cutover, other 0.3 families and publication are
separate gates. See VERIFICATION.md for installed/source checks and evidence.
