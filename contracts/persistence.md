# Optional API persistence: approved 0.4 extraction design

## Current format: 0.7.0

SQLite and notification archives now use version 3, binding to application-keyed
account identifiers. Opening a store requires POSIX and rejects other platforms
before filesystem creation. Formats 1/2 are refused without modification or
automatic migration. The historical version-2 design below describes the extra
store-local HMAC layer, which is retained. The former public unkeyed hash is
superseded by [the context-key contract and upgrade guide](account-context.md).

### Explicit notification mailbox selection (#22)

`NotificationWorkflow(..., messages_backend=MessagingBackend.MODERN)` selects one
bounded received summary page from the modern API. The default remains LEGACY.
No fallback or message-content request is made. The backend is recorded on pending
batches containing MESSAGES; replay requires the original categories and backend.
Acknowledgement preserves every other seen category and backend namespace.

Existing legacy canonical IDs are unchanged. Modern message identities use SHA256
of compact JSON `[2,"messages","modern",folder,identifier]`, so identical numeric
references cannot collide across mailboxes. Account separation remains owned by
the keyed context and store-local namespace, not student identity.

SQLite/archive version 3 is retained: schema and old seen state are unchanged.
Missing `messages_backend` on an existing format-3 delivery means legacy. New
writers include that field and modern typed summaries; older readers may reject
new pending records. Preserve original stores/exports for rollback, never reset
or rewrite them implicitly. Switching backend while a delivery is pending fails
before HTTP; acknowledge or recover the original delivery first.

### Neutral external bootstrap (#23)

`NotificationStore.bootstrap(NotificationBootstrap(...), context=...)` imports
caller-established `NotificationBaselineMapping` records and typed historical
`RecentScheduleEvent` values offline. Context must match the plan exactly. Source
identifiers are opaque; native identifiers must already be independently mapped
canonical IDs. Unknown categories, malformed IDs, collisions and duplicate or
already-seen pending events reject. A mapping with `native_identifier=None`
returns an explicit unmapped report with `imported=False` and performs no writes.
Consumers must stop or resolve that report, not silently seed a fresh account.

Empty-target-context import atomically registers context, writes initialized seen
state and stages one bounded historical AGENDA batch. Repeat attempts reject
even after acknowledgement. Item provenance is `IMPORTED_HISTORY`; identity and
observation are explicitly None. No timestamp, owner/student identity, raw HTTP
body or session metadata is fabricated. Historical delivery cannot coexist with
raw checkpoints or uncertain-consume markers. Capacity failures roll back the
whole import, not just pending events. Cancellation/shutdown joins owned workers.

Public workflow replay with the AGENDA tuple and acknowledgement remain offline,
including across process restart. `state` exposes mapped baseline IDs and native
archives round-trip the missing-provenance representation. Native observed
records missing the new provenance field are read as OBSERVED and still require
identity/observation. No SQLite schema change or automatic old-file import occurs.

Rollback stays consumer-owned. Keep original source files and the mapping plan,
and export a native archive before cutover. Seen hashes cannot recover old opaque
identifiers; source identifiers are not persisted and absent authentication
provenance cannot be reconstructed. Inputs must fit one staged batch; there is no
silent truncation or multi-step partial import. See [the public API](../API.md#offline-external-baseline-bootstrap)
for bounds, error/report semantics and replay steps.

### Typed offline recovery (#24)

`recovery_status(context=...)` exposes compact immutable account-bound facts:
initialized state, last acknowledged receipt, pending receipt/categories/backend
and item count, retained raw identifier/cursor/optional total/encoded wire size,
and conservative uncertain-consume marker. The flags are independent, since
ordinary delivery can coexist with raw or uncertain work. Status does not decode
raw pages, authenticate, acknowledge, stage, advance cursors, prune or clear
uncertainty. Missing contexts return no work without being registered.

`pending_batch(context=...)` returns the original durably staged native or
historical batch without remembered category/source selection, or None. It is
offline, bounded by existing persistence limits and unchanged until explicit
acknowledgement. None does not assert that raw/uncertain recovery is absent.
Use status to distinguish those facts. Raw replay and loss-consenting uncertainty
resolution remain separate explicit operations. Each lookup is atomic, but two
successive calls can observe a competing acknowledgement; use the actual retrieved
batch receipt rather than an earlier status. Use service-owned account contexts.
Invalid contexts, corrupt records and aliases inconsistent with retained metadata
reject without silent partial output. Reads create neither context registrations
nor per-context lock files. A marker may belong to an active poll; resolution
still requires context exclusion and explicit loss acceptance.

## 0.4.11 retention and storage format decision

S10(c,d) use explicit caller-selected pruning, not automatic age expiry. Native
IDs lack trustworthy age metadata across all categories; silent expiry could
re-notify old records or remove duplicate-send protection. `prune_seen` selects
one context/category and exact IDs, requires reservation/delivery recovery to
be resolved, preserves raw checkpoint bytes/cursor, initialization and all other
categories, and commits
atomically. Forgotten IDs may be notified again. `prune_send_history` selects
exact context-bound history identifiers; live pending, CLAIMED and UNKNOWN rows
cannot be deleted. Expired unused confirmations and safe terminal rows can be
removed. ACCEPTED pruning requires `allow_accepted=True`, explicitly permitting
later duplicate confirmation for the same submission. No network is performed.
SQLite reuses freed pages; pruning is logical, not secure erasure or VACUUM.
Retained raw replay is allowed after pruning, so seen saturation can be recovered
without a new read-once request, even after an earlier slice was acknowledged.
Agenda IDs proving the acknowledged raw prefix remain protected until that raw
receipt drains, so every exported archive remains independently importable.

Both database schemas advance to version 2, adding one random 32-byte context
salt per store. SQL context keys, notification lock filenames, persisted batch
contexts and raw digests use the store-local HMAC-SHA256 namespace. Public native
`AccountContext` remains stable across password rotation and restarts; its unsalted
in-memory fingerprint is not written into the store. `context_identifier` exposes
the pseudonym for explicit diagnostics after opening, without credentials.
Salts are created atomically under the database write lock and validated on every
connection. This reduces cross-store correlation/precomputed hash reuse, not
encryption or protection from low-entropy guessing by someone holding the salt.

Neutral notification archives advance to version 2 and include the source salt.
Empty-target import validates the exact source context/digests, then rebinds keys,
raw links and staged batch context to the destination store salt, retaining receipt,
seen state and progress. Payload bytes differ across stores while public replay
is unchanged. Version-1 database/archive formats fail explicitly without reset
or auto migration. Nothing is in production yet; old local stores must be kept
for diagnosis or deliberately recreated by their owner. Once MCP stores real
data, any future format change requires an explicit qualified migration and
rollback path in addition to version refusal. This slice reads no production data.

## Ownership and provenance

The owner clarified that MCP is a thin consumer and the API supplies reusable
prerequisites, including durable send/notification workflows. The optional layer
is explicitly configured by the application. Core account clients, transport,
domain results and parser contracts remain storage-independent and require no
MCP dependency, environment discovery, state directory or database.

Existing MCP safeguards are requirements references, not source to copy. All
library implementations and fixtures are independently authored. In particular,
no GPL consumer filesystem helpers, upstream parsers or private fixtures are
transferred into this MIT repository. The removed task-local MCP prototype was
never integrated or committed as an implementation. Consumer documentation on its
isolated coordination branch records the revised thin-adapter boundary.

## 0.4.8: durable send prerequisites

Implementation: an explicit private SQLite store using standard-library
transactions, bounded schema/record counts/bytes, busy timeout and storage worker
admission. File and directory checks reject non-regular files, symlinks and unsafe
ownership/permissions. Construction/import are inert; opening and closing are
explicit and cancellation joins every admitted worker. No persistent HTTP cookies
or credentials are stored and no background recovery task starts automatically.

Bind durable confirmation to an independent configured-login context, backend and
the complete immutable submission, including recipient provenance and order.
An alias alone or a shared student ID is insufficient after account reconfiguration.
Persist only confirmation-token hashes, context/payload digests, deadlines and
outcomes, not token plaintext, message bodies or recipient labels. An application
recreates the prepared immutable payload from the same approved input on redemption.

Commit the single-use claim before invoking `SendAttempt.execute`. Crash after
claim is conservatively UNKNOWN, even before HTTP dispatch. Existing token reuse
or a second preview of the same unresolved/accepted submission cannot bypass it.
Never auto-retry, select another backend, infer acceptance from HTTP status, or
reconcile by sent-folder similarity. Distinct independent login/backend contexts
must not share consent, outcomes or notification state.

Joined execution saves the typed final outcome. Cancellation propagates normally;
an acknowledged result survives joined cleanup. Failed final persistence leaves
the consumed claim uncertain, never permission to replay. Store contention,
invalid/expired binding, corrupt/unknown schema and capacity limits stop execution
before upstream work. After a claim, a failed final save (including write-lock
contention past `final_busy_timeout_seconds`) reports STORAGE, never LIMIT, and
leaves the claim uncertain. Expired unused previews may be pruned; uncertain/consumed
history is not silently discarded to make room. Manual reconciliation is an
explicit later policy, not implicit deletion or token reissuance.

Proof gates: original public-API loopback sends, installed artifacts on Python
3.13/3.14, actual process crash and competing-process claims, durable save faults,
maximum accepted load, queue saturation, symlink/corruption refusal, configured-
login/backend binding and repeated cancellation at claim/send/final-save boundaries.
These offline gates passed for 0.4.8; exact counts, hashes, limitations and review
lessons are recorded in [../VERIFICATION.md](../VERIFICATION.md). Live qualification
and any MCP integration remain separate, not implied by local storage proofs.

## 0.4.9: durable notification prerequisites

Implementation: an explicit `NotificationStore` and native
`NotificationWorkflow`, with a separate `notifications.sqlite3` in the selected
private directory. Reuse independently authored SQLite/file/worker ownership
primitives, not send schema or GPL consumer helpers. Existing 0.4.8 send databases
remain unchanged and need no automatic migration. Core clients remain inert and
storage-independent. Ordinary tests and qualification stay entirely offline.

Serialize per configured-login context across processes using held OS locks,
not expiring leases. Read selected ordinary categories first, then replay a
pending raw envelope before any new consume. Reserve bounded checkpoint capacity
and persist a consume-uncertainty marker before the read-once call. Persist the
complete encoded body and original identity/observation/codec metadata before
parsing. Malformed raw responses stay recoverable and block fresh consumption.
An unresolved marker without raw data blocks another consume until an application
explicitly accepts possible upstream loss; never expire it or infer safe replay.

Use a two-phase delivery: return a durably staged native batch with a receipt;
explicit acknowledgement atomically commits seen IDs and raw cursor/cleanup.
Cancellation, process loss or failed acknowledgement preserves pending delivery
for at-least-once replay without HTTP. This avoids marking items seen before a
caller has even received them. It is not exactly-once notification delivery.
Drain oversized accepted schedule batches in bounded event/byte slices, retaining
the full envelope and cursor. Never reset unrequested-category seen state.

Canonical identities are versioned, domain-specific, and independent of MCP.
Schedule identity covers the three visible date/type/data fields, preserving the
previous consumer's independently re-established canonical hash requirement.
Other native identifiers need an explicit qualified old-to-new mapping; do not
pretend arbitrary legacy IDs are compatible. Provide neutral bounded archive
export/import, including raw progress and staged delivery, into an empty target
only. Refuse incompatible versions/context, malformed data and implicit overwrite.
MCP-specific file parsing/mapping and production migration remain deferred.

Proof gates: real SQLite and public native loopback reads; requested-category and
first-run behavior; raw preservation before parser faults; restart replay without
credentials; save/ack faults and repeated cancellation; process kill before/after
checkpoint; competing processes; maximum batches/bytes and shared saturation;
neutral archive import/export and unchanged 0.4.8 send state. Qualify source,
wheel and sdist on Python 3.13/3.14 in separate feature/version commits.

Persist the complete account-bound encoded schedule envelope before any content
decoding/parsing. Recover and drain existing raw checkpoints before another
consume. Preserve malformed accepted responses for explicit diagnosis; do not
silently drop data or reset seen history. Provide bounded replay and deduplication,
stable canonical identities, requested-category and first-run behavior, transaction
locks and rollback-safe import/export primitives independently of MCP. There is no
automatic schema migration: unknown layouts fail without resetting existing data.

### Delivery, limits and compatibility boundaries

The store uses POSIX `flock`, with one persistent zero-byte private lock file per
registered context. Contending callers fail with LIMIT, not an unbounded wait.
The same context is serialized across processes; distinct contexts remain separate.
All actual HTTP work still uses the service scheduler and supplied shared budget.
An application using multiple processes must separately coordinate global network
traffic; filesystem context locks do not implement a distributed rate limiter.

First run means the context has no acknowledged delivery. It diffs selected native
collections against empty seen IDs, never the menu count route. Ordinary categories
use LAST_LOGIN grades/attendance, the first received-mailbox page, announcements,
and an explicit homework window (default: preceding seven days through today in
Europe/Warsaw). These are bounded observations, not a historical catch-up guarantee.
Only delivered IDs change on acknowledgement; unrequested categories stay intact.
An empty batch still has a receipt and initializes the context only when acknowledged.
While a batch is pending, the exact original category tuple must be requested.
It is replayed without HTTP even if new consume consent is omitted. Changing the
selection requires acknowledging that batch first.

All contexts share one SQLite write lock. Saves that follow an upstream side
effect (checkpoint, staging, acknowledgement) wait up to `final_busy_timeout_seconds`
(default 5 s) for it; a checkpoint save that outlives its callback timeout is
still joined, and a late commit is replayed rather than lost. Archive import
rejects raw cursor progress past any event missing from the imported seen set.

Defaults: 16 contexts, 8 workers/workflows, 0.1 s busy timeout, 32 checkpoints or
uncertainty reservations, 16 MiB combined checkpoint/reservation bytes, 4 MiB total
seen-state bytes, 4,096 seen IDs per category, 500 delivery items and 1 MiB batch
bytes. Schedule slices contain at most 500 new events and 128 KiB canonical value
JSON. The full raw envelope remains bounded by 4 MiB encoded body plus 4 MiB
metadata. SQLite main-file capacity is 64 MiB; staged delivery plus candidate
state is globally capped at 16 MiB. All bounds fail closed without pruning seen
history or consuming another envelope. Explicit larger supported limits can
recover a retained envelope that failed a smaller delivery/seen bound. An event
too large for one configured slice blocks replay rather than being skipped.

Reserve worst-case body/metadata capacity before consuming and retain the marker
using logical storage budgets, not a physical disk-space guarantee. Disk exhaustion,
filesystem failure and process loss between upstream mutation and complete durable
checkpoint remain possible loss windows. The marker records uncertainty, not data
which was never received. Reserve capacity and retain the marker
after any pre-checkpoint fault, even a failure before authentication. This may
conservatively block a call which never reached upstream. Only explicit
`resolve_uncertain_consume(accept_possible_loss=True)` removes a marker without
raw/delivery data. Complete malformed responses are not markers and cannot be
discarded through that method. Export them for diagnosis; no hidden fresh consume.

Neutral archive version 1 embeds the exact context and holds seen state, last
receipt, encoded raw envelope, cursor, pending delivery and uncertainty reservation.
Imports require an empty target context and validate raw digest, actual decoded
event count, staged event/cursor consistency and candidate seen state in one SQL
transaction. A raw envelope without an established event count is deliberately
not parsed on import, allowing recovery of malformed checkpoint bytes. Archives
contain private data, are not encrypted or authenticated, and must be protected
by the application just like the source directory. SQLite deletion is logical,
not a secure-erasure guarantee. Do not remove lock files while stores are active.

`canonical_notification_id` provides the version-1 native identity policy.
Schedule identity is SHA-256 of sorted, compact, UTF-8 JSON of date_added/type/data.
Native messages use folder and reference ID; announcements use their content
reference; homework/attendance use native IDs where present; otherwise identities
cover the typed visible value. Modified stable-ID records are not automatically
re-notified. Old MCP `schedule` category needs explicit mapping to native `agenda`.
Other old IDs require independently qualified conversion, not blind ingestion.
Neither the archive nor this workflow reads old MCP JSON/spool files or promises
wire compatibility, exactly-once delivery or durable upstream acknowledgement.

MCP-specific legacy JSON field names and spool formats belong in a thin explicit
adapter. Existing production files are not read/migrated by import, startup or
offline tests. Compatibility must be demonstrated using original non-personal
fixtures before enabling selection; retain old data until rollback is proved.
Live read-once qualification still needs a dedicated disposable-event account.

## Consumer extraction inventory

| Existing reference | Reusable prerequisite / safeguard | API destination / gate |
| --- | --- | --- |
| `librus-mcp/src/librus_client.py` authentication and `_execute` | Independent sessions, bounded denial recovery/cooldowns, no write replay, joined work | Native service/scheduler already implemented; installed consumer fault parity before retirement |
| `librus-mcp/src/response_limits.py` and response wrappers | Per-response and cumulative byte/redirect/deadline limits | Native transport/budgets; wire and saturation proof, no copied HTTP wrapper |
| `librus-mcp/src/librus_optimizations.py` | Bounded lookup fan-out, metadata reuse and cache invalidation | Native typed reads/reference caches, shared budgets and public integration proof |
| `librus-mcp/src/librus_client.py` window/page methods | Validated dates, bounded scans/items, explicit truncation and continuation | Native family APIs; consumer maps the established wire shape without another paging engine |
| `librus-mcp/src/scraping.py` | Domain parsing, body decoding, attachment destination and publication safety | Original native parsers/streams and optional file layer; explicit read effects and cancellation proofs |
| `librus-mcp/src/server.py` send confirmation helpers | Payload-bound expiring single-use confirmations and uncertainty | Optional API persistence; MCP presents approval and maps typed outcomes |
| `librus-mcp/src/notification_state.py` | Private bounded files, atomic durability, locks, canonical IDs, pending replay and state preservation | Optional API persistence/notification workflow; explicit old-format adapter and restart/process proofs |
| `librus-mcp/src/librus_client.py` notification transactions | First-run/category selection, seen-state commit, preserve consumed events across faults | Optional API notification orchestration; existing-state compatibility and exactly-once limitations explicit |
| `librus-mcp/src/config.py`, `cli.py`, `server.py`, `output_models.py` | Configuration source precedence, feature gates, lifecycle, human consent, MCP schemas/errors/serialization | Thin consumer responsibilities; define new native MCP 2.0 catalog/contracts and verify installed stdio behavior |

This inventory is a requirement map, not a claim that every extraction is complete.
Build the prerequisites in this repository now; implement adapters in the separate
`librus-mcp` repository when its migration from the legacy backend begins. No MCP
implementation changes are part of the current API persistence slice.
Retire duplicate consumer logic only in the slice whose API replacement and
adapter have passed the actual runtime/fault proof. No literal copying, hidden
legacy fallback, production-state reset, merge or publication is implied.
