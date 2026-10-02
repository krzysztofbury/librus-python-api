# Recipient discovery (0.4.1)

## Scope and side effects

Two fixed selection operations discover named group types and the numeric
recipients in one selected group. They use the existing account-isolated service,
request/deadline/body budgets, lock, parser worker and cache/coalescing path.
Both are selection-view operations and are never replayed after expiry or an
ambiguous response. No send, message open, mark-read, attachment or read-once
operation is enabled.

The recipient POST has exactly five fields: `typAdresata` is a bounded named
token; `poprzednia=5`, `tabZaznaczonych=''`, `czyWirtualneKlasy=false` and
`idGrupy=0` are fixed. Credentials, selected-recipient payloads, subject/body,
upload and send fields cannot pass the transport guard. All paths are in
`config.py` with matching OpenAPI operations.

## Independent observations

The live composer has eight group rows, preceded by a table header. Each radio's
value is a named token, its ID is `radio_TOKEN`, and the visible label links to
that ID. Treating types as numeric stopped the initial capture before any
recipient POST; the scope was explicitly amended, not widened automatically.
The original headed-table regression failed before the parser was changed to
read `tbody` only.

The approved tutor, teacher and school-office lookups each returned populated
responses. Every recipient label links to a `check_NUMERIC_ID` checkbox whose
value matches that ID. A separate ID/value-free checkbox selects all; it is not
a recipient. Checkbox/label cardinality is checked so an unlabeled recipient
cannot silently disappear. Duplicate IDs fail; duplicate names with distinct
IDs survive.

The `grupa` type has unqualified selection semantics. It is reported with
`lookup_supported=False`; `recipients()` refuses it before I/O rather than
guessing that group zero means all recipients or asserting an observed hierarchy.
Further group/virtual-class selection is deferred. No empty
recipient page was observed, so no empty-success shape is invented.

## Apix coverage and provenance

The external `librus-apix` 1.5.3 distribution was a behavior reference,
not code to copy or an oracle. Fixtures and implementation here are original;
the group/checkbox shapes were independently observed with approved access.
There is no apix runtime dependency, hidden fallback or vendored code.
The external package's MIT metadata conflicts with its bundled GPLv3 license;
the reference is not described as unambiguously MIT-licensed.

`scripts/compare_recipients.py` supplies captured bytes to apix through an inert,
strictly scoped replay client. It cannot make network calls. Native and external
parsers receive identical bytes; only mismatch counts and classifications escape.
Chromium independently checks rendered labels, tokens, numeric IDs, control
linkage and group availability with page scripts/networking disabled.

| Apix behavior | Native behavior | Coverage |
| --- | --- | --- |
| `recipient_groups` returns tokens only | Typed labels, references, availability and library lookup capability | All eight observed tokens agree on identical bytes |
| `get_recipients(group)` returns name-to-ID dictionary | ID-bearing ordered records with account/group provenance | Three approved populated groups agree with apix and Chromium |
| Repeated name overwrites prior ID | Equal names with distinct IDs remain records | Original offline regression, not a live duplicate-name observation |
| No labels can become `{}` | Missing/unknown layout fails explicitly | Empty live evidence pending |
| Arbitrary group string / caller-owned requests | Typed account-bound reference, fixed form, shared traffic budget | Foreign/injected reference and unsafe-form guards exercised offline |
| Unqualified group selection | `grupa` explicitly unsupported for lookup | Additional group/virtual-class selection is deferred, not a guessed empty result |

## Qualification limits

One login context, three populated group types. Other group types, account roles,
empty lists, virtual classes, subgroup membership and disabled recipients remain
unqualified. Group availability is metadata, not a permission token or a send
authorization. Recipient discovery never authorizes contact with anyone.

Two approved login attempts used 26 total HTTP requests: ten for initial composer
discovery, sixteen for the installed public smoke including six recipient POSTs.
No third login was performed. Both raw directories are temporary and are deleted
after final installed offline replay; only sanitized metrics are retained in
[VERIFICATION.md](../VERIFICATION.md) and `release-evidence/0.4.1-recipients.json`.

The final installed smoke passed before an additional missing-label cardinality
guard, conservative lookup-capability naming and route-evidence metadata were added.
The strengthened parser is checked
against every captured response with Chromium and the final installed artifact,
without another credentialed call. This distinction is recorded, not called a
second fresh live smoke of changed code.
