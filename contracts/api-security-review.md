# Client API security and architecture review

Date: 2026-10-04. Scope: public client operations, transport/authentication,
parsers, shared scheduler/budgets, optional files/persistence and consumer cutover
contracts. Baseline is merged PR #15; this branch contains the fixes below.

## Basis and threat boundary

Reviewed against Snyk's [OWASP API Top 10 learning path][top10],
[unsafe API consumption guidance][consumption] and [SSRF guidance][ssrf].
This is a code/contract review with offline fault tests, not a Snyk product scan,
penetration test, upstream security assessment or security certification.

This package is an outbound client library, not an HTTP API server. Untrusted
inputs include upstream responses/redirects/filenames and caller selections.
The embedding Python application, its credential configuration, explicit proxy,
custom transports and filesystem destination are trusted deployment boundaries.
An Internet-facing wrapper must authenticate callers and authorize account aliases
itself. Native reference validation cannot replace that authorization, and a
reference/cursor is not a bearer credential. Use one shared service per process;
independent processes need externally coordinated quotas.

## Findings and dispositions

### Safety: permissive JSON constants - fixed, low severity

`parsers.decode_json` rejected duplicate keys and excessive nesting, but Python's
decoder accepted `NaN`, `Infinity`, `-Infinity` and overflowing `1e9999`. An
otherwise valid identity containing one in an ignored field was accepted.
Four cases in `tests/test_identity.py` failed before the fix. The decoder now
rejects non-standard constants and non-finite decoded floats before domain
validation, returning a redacted `ParseError` without attaching the raw cause.
This is input-hardening evidence, not a demonstrated account-access bypass.
TigerStyle #6: Positive and negative space; #13: Explicit defaults.

### Safety: side-effect mismatch at the consumer boundary - migration gate

MCP currently labels content/attachment-list reads as read-only. Native received
content explicitly requires mark-read consent; attachment metadata obtained by
opening that content shares the effect. Native downloads do not open content.
Keep the native gate and correct consumer annotations/consent during migration.
Do not bridge by silently supplying `True`. Read-once events similarly require
explicit consent plus durable checkpoint ownership. TigerStyle #6.

### Performance: broad homework windows lacked bounded orchestration - fixed

MCP accepts a 370-day date difference while one upstream homework selection
accepts at most one calendar month. The new helper preplans up to 13 disjoint
windows, caps aggregate items/text and retains one original operation budget and
shared admission boundary. Failures never publish partial cache entries. No
additional per-account sessions or independent traffic limiter were introduced.
TigerStyle #2: Bounded loops; #14: Batching.

### DX: date-window semantics differed from MCP - fixed

Grade/attendance windows now support optional boundaries and an explicit typed
view, preserve that view in the response and reuse its own collection cache.
Two supplied dates may be at most 370 days apart. Compact JSON/offset projection
remains in the adapter. TigerStyle #16: Naming clarity; #17: Symmetrical naming.

## Snyk / OWASP control map

| API risk | Inspected implementation and proof owner | Conclusion / boundary |
| --- | --- | --- |
| API1 object authorization | Reference/account/backend validation in `service.py`, `attachment_routes.py`, `modern_mailbox.py`; `test_communication_edges.py`, `test_modern_attachments.py` | Cross-account references rejected before dispatch. Caller-to-alias ACL belongs in the embedding server |
| API2 authentication | Strict identity checks, optional expected owner/student IDs, isolated native/modern cookies, fresh pre-send identity; `test_identity.py`, `test_modern_session_recovery.py` | No identity-based merging, silent backend fallback or interactive challenge bypass |
| API3 property authorization / exposure | Explicit wire fields and fixed form builders, inert metadata, redacted domain reprs/errors/diagnostics; `test_transport.py`, `test_identity.py`, `test_sending.py` | No arbitrary mass-assignment form. Serialization must explicitly choose exposed fields; repr redaction is not a serializer |
| API4 resource consumption | `scheduler.py`, `budget.py`, `parsing.py`, bounded transport decompression/streams; `test_scheduler.py`, `test_account_reads.py`, `test_attachments.py` | Shared queue/rate/concurrency and deadline/byte/item limits. Default policies are engineering limits, not an upstream quota |
| API5 function authorization | Explicit read-effect booleans, separate send APIs, generic transport write rejection; `test_message_content.py`, `test_sending.py`, `test_notification_checkpoints.py` | Library represents effects; consumer authenticates callers and controls feature exposure |
| API6 sensitive business flows | Single-use attempts and durable preview/claim/finish, original-budget no-retry writes; `test_persistence.py`, `test_notification_persistence_processes.py` | No exactly-once upstream guarantee. Claimed/UNKNOWN sends block duplicates; read-once replay is local and at-least-once |
| API7 SSRF | Fixed origins/routes in `config.py`, exact redirect and sandbox validation, credential-free downloads, `trust_env=False`; `test_transport.py`, `test_modern_attachments.py` | No caller-supplied authenticated URL. Loopback overrides are explicit test configuration, not a user-controlled request field. TLS validates production destinations |
| API8 misconfiguration | Strict frozen configuration, verified TLS >=1.2, explicit proxy, no global logging setup; `test_config.py`, `test_transport.py` | Consumer must secure its deployment paths and proxy. CORS, inbound security headers and HTTP authentication apply to a future server, not this package |
| API9 inventory | Central endpoint catalogue, OpenAPI effects/retry/evidence, `test_contracts.py` | Enabled wire routes are checked against the specification. OpenAPI describes upstream HTML/JSON, not invented public REST resources |
| API10 unsafe consumption | Strict JSON/HTML/XML parsing, no-network markup, body/tree/field limits, no fetched scraped links; `test_identity.py`, `test_modern_content_layouts.py`, family parser tests | Malformed/ambiguous data is an error, not empty success. Render returned text as text or escape for its output context; do not treat it as trusted HTML |

## Files, persistence and supply chain

- `files.py` uses bounded portable basenames, directory-relative descriptors,
  exclusive owner-only temporary files, fsync and non-overwriting hard-link
  publication. Cancellation joins disk workers before cleanup. A cancellation
  during commit can leave a complete file; it cannot imply rollback. The caller
  must select a directory whose parent chain and writers it trusts. Publication
  provides integrity/atomicity, not attachment malware scanning or file execution.
- `_storage.py` validates private directory/file ownership, sidecars and schema,
  uses parameterized data queries, bounded rows/database size and short
  `BEGIN IMMEDIATE` transactions. Closing on failure rolls back an uncommitted
  transaction. No credentials/cookies are stored. Notification payloads remain
  sensitive plaintext under owner-only permissions, not encrypted-at-rest data.
- Salted account contexts distinguish login/backend/connection configuration.
  Storage import validates schemas/context before explicit rebinding. Unknown
  send state is not automatically pruned, reconciled or resent.
- Dependencies are locked; CI pins action revisions, scans worktree/history
  secrets and audits the lock. The local verification entry in VERIFICATION.md
  records actual checks. No repository source was uploaded to a scanning SaaS.

## Architecture decisions

**Service layer:** `LibrusService` owns lifecycle and shared admission;
`AccountClient` owns account session/cache and use-case orchestration. Parsers
are pure typed translations. New aggregation stays inside `_read`/`_page`, so
it inherits lifecycle, diagnostics, locks and traffic limits. Splitting the
large service file may help future navigation but is not a security fix and
must not duplicate these boundaries in family-specific clients.

**Repository pattern:** the typed `AccountTransport` protocol already separates
wire I/O from use cases. It is an upstream gateway, not a database entity
repository. `PersistenceStore` and `NotificationStore` are the repositories for
local durable state. Adding a generic CRUD repository over HTML would obscure
view-selection effects, pagination drift and backend-specific contracts without
creating a useful transactional abstraction.

**Unit of work:** `_SQLiteStore._connection()` is the local unit of work. Keep
network awaits outside its short transactions. Send processing commits claim,
then dispatches, then commits outcome; a crash between them remains uncertain.
Notification processing checkpoints bytes before parsing and acknowledges staged
delivery separately. There is no atomic transaction spanning SQLite and Librus,
so a generic remote `commit()/rollback()` API would make a false guarantee.

**REST practices applied:** validated typed selections/results, canonical errors,
bounded pagination, explicit versions/evidence, freshness/provenance, transport
timeouts and method-specific retry rules. HTTP GET is not sufficient to infer
safety: upstream GETs can consume events or mark read. Idempotency tokens are
local duplicate guards, not a server-supported idempotency key. Request DTOs do
not need to duplicate every method signature; existing typed primitives and
domain references remain appropriate for simple operations.

## Remaining limits

The review does not establish populated behaviour-note or observation-card wire
contracts, additional school/role support, archive mailbox navigation, or live
read-once recovery. Those need independent evidence and the existing live gates.
See [the cutover matrix](mcp-cutover-review.md) for compatibility differences that
must remain explicit when adapting the consumer's less expressive schemas.

[top10]: https://learn.snyk.io/learning-paths/owasp-top-10-api/
[consumption]: https://learn.snyk.io/lesson/unsafe-consumption-api/
[ssrf]: https://learn.snyk.io/lesson/ssrf-server-side-request-forgery/
