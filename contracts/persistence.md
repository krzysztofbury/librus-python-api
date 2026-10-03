# Optional API persistence: approved 0.4 extraction design

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

Proposed implementation: an explicit private SQLite store using standard-library
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
before upstream work. Expired unused previews may be pruned; uncertain/consumed
history is not silently discarded to make room. Manual reconciliation is an
explicit later policy, not implicit deletion or token reissuance.

Proof gates: original public-API loopback sends, installed artifacts on Python
3.13/3.14, actual process crash and competing-process claims, durable save faults,
maximum accepted load, queue saturation, symlink/corruption refusal, configured-
login/backend binding and repeated cancellation at claim/send/final-save boundaries.

## 0.4.9: durable notification prerequisites

Persist the complete account-bound encoded schedule envelope before any content
decoding/parsing. Recover and drain existing raw checkpoints before another
consume. Preserve malformed accepted responses for explicit diagnosis; do not
silently drop data or reset seen history. Provide bounded replay and deduplication,
stable canonical identities, requested-category and first-run behavior, transaction
locks, migrations and rollback-safe import/export primitives independently of MCP.

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
| `librus-mcp/src/config.py`, `cli.py`, `server.py`, `output_models.py` | Configuration source precedence, feature gates, lifecycle, human consent, MCP schemas/errors/serialization | Thin consumer responsibilities; preserve catalog/contract snapshots and installed stdio behavior |

This inventory is a requirement map, not a claim that every extraction is complete.
Retire duplicate consumer logic only in the slice whose API replacement and
adapter have passed the actual runtime/fault proof. No literal copying, hidden
legacy fallback, production-state reset, merge or publication is implied.
