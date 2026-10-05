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

## Reference-client coverage and provenance

The external reference client was a behavior reference,
not code to copy or an oracle. Fixtures and implementation here are original;
the group/checkbox shapes were independently observed with approved access.
There is no reference-client runtime dependency, hidden fallback or vendored code.
The external package's MIT metadata conflicts with its bundled GPLv3 license;
the reference is not described as unambiguously MIT-licensed.

A since-removed offline script supplied captured bytes to the reference client through an inert,
strictly scoped replay client. It could not make network calls. Native and external
parsers received identical bytes; only mismatch counts and classifications escaped.
Chromium independently checks rendered labels, tokens, numeric IDs, control
linkage and group availability with page scripts/networking disabled.

| Reference-client behavior | Native behavior | Coverage |
| --- | --- | --- |
| `recipient_groups` returns tokens only | Typed labels, references, availability and library lookup capability | All eight observed tokens agree on identical bytes |
| `get_recipients(group)` returns name-to-ID dictionary | ID-bearing ordered records with account/group provenance | Three approved populated groups agree with the reference client and Chromium |
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

## 0.4.5 choice discovery and broader response layouts

Four independent login contexts expose eight named types. Five return populated
labelled checkbox lists; `sadmin` instead returns one matching pair of hidden
`DoKogo`/`DoKogo_hid[]` numeric values without a displayed name. Native records
preserve `label=None` for that exact shape, never fabricate a name or return an
empty list. Page-level scripts remain inert. Unexpected visible data, controls,
conflicting values or labels fail. Sending to an unnamed target is not authorized.

The class-dependent parent-council type returned a class-unavailable UI notice
on all contexts. It is a typed unsupported capability, not proof of zero
recipients. Unknown notices/prompt states cannot silently coexist with a
successful list of only recognizable rows.

The `grupa` root displays a named `idGrupy` select, one blank value-zero option
and a choose-group prompt on all contexts. `recipient_group_choices` returns
its bounded nonzero choices; all observed option lists are empty. This is
empty group discovery, not explicit empty-recipient success.

Group/reference `selection_id` defaults to zero for compatibility. Positive
numeric selections are allowed only for `grupa`; they preserve account/type/
selection provenance in references and cache keys. The central five-field
form still excludes recipient selections, credentials, body/subject and uploads,
and fixes virtual-class selection to false. Root zero is never interpreted as
all group members. Original loopback fixtures qualify populated choice parsing,
selection wire forms, distinct caches and bounds, but nonzero dispatch and
populated hierarchy are not observed live. No recursive or virtual-class
selection is claimed. Availability metadata is not an authorization token.

Independent Chromium checked every response. The reference client agrees on common named
recipient pairs and the eight type tokens; it loses the anonymous target and
has no equivalent typed group-choice or unavailable-capability result. These
are intentional semantic differences, not silently inherited omissions.
Installed replay uses private independently rendered expectations through the
public API; captures/expectations are deleted afterwards. Exact qualification
and remaining gaps are in [VERIFICATION.md](../VERIFICATION.md).
