# Notification and checkpoint primitives (0.4.4)

## Ownership and design decision

The library provides typed ordinary count/event records and an explicitly
consenting read-once primitive. It does not own a notification manager, selected
categories, first-run rules, seen IDs, hashes, durable spool format, locks,
transactions, delivery limits, migrations or filesystem publication. Ordinary
grades/attendance/message/announcement/homework records already supply the other
notification inputs; do not create a second six-category orchestration facade.

Pair-programmer design intentionally strengthens P5's original validated-batch
handoff to **complete encoded-response checkpoint before validation/parsing**.
Malformed gzip, MIME, markup or parser limits must not destroy the only fully
received representation. A successful callback acknowledges consumer-owned
durable storage. Only then can a complete typed batch be returned. The consumer
must drain existing durable responses before another consume; the library
cannot inspect an external spool or enforce cross-process transactions.

## Count semantics

`notification_counts` reads the existing student landing/menu route explicitly.
The route also participates in optional authentication redirects, so the single
catalogue operation preserves its authentication classification and conservative
no-replay policy. It is never a mandatory parent-account bootstrap.

Six known menu destinations map to typed categories. Labels and nonnegative
integer counters are returned in displayed order. An absent counter for a shown
category means zero; an absent category is not invented. Invalid, duplicate or
oversized counters fail rather than silently becoming zero. Unknown navigation
links stay inert. These counters may be token-scoped snapshots: fetching their
page again does not promise a fresh notification poll or force a new login.

## Consume and replay boundary

- Consent defaults to false. A callable awaitable checkpoint is mandatory;
  callback/interval/consent validation precedes authentication/admission.
  Awaitability can only be established when invoking a callable; a wrong return
  value then becomes a typed checkpoint failure, not permission for replay.
- Read-once retrieval is uncached and never coalesced or automatically replayed.
  A simultaneous consume on the same login is rejected rather than queued.
  Independent logins keep isolated sessions and original identity provenance.
- The response-owning scheduled transport task receives bounded payload bytes
  and establishes checkpoint task ownership before another cancellable await.
  A callback added only after the scheduler returns would leave a loss window.
- The version-1 envelope contains identity, observation and encoded payload
  bytes plus Content-Type/content-coding/transfer-coding fields only. HTTP transfer
  framing is already removed by aiohttp; this is not a literal TCP/HTTP capture.
  Content decompression and semantic parsing happen after durable handoff.
  URLs, cookies, arbitrary response headers and auth data are not metadata.
- `decode_schedule_events` locally replays a consumer-persisted envelope using
  bounded parser workers and an operation budget. It never authenticates or
  dispatches HTTP, preserves original identity/observation, and requires the
  same account alias and supported envelope version. Serialization and recovery
  policy remain application-owned; envelopes are not authorization tokens.
- Events preserve added-date text, free-form type and normalized multiline data,
  order and duplicates. No synthetic ID, hash, detail link, UTC conversion or
  upstream category enum is invented. The conservative four-column/header and
  explicit-empty layouts are source-informed, not independently observed live.

## Cancellation, deadlines and uncertain acknowledgement

Before complete accepted receipt, cancellation joins network work but may still
lose already-consumed upstream events. This includes disconnection, truncation,
wire/byte/header rejection, or process termination. No exactly-once claim exists.

After complete receipt, a separate checkpoint interval defaults to five seconds
and is configurable up to thirty. Cancellation, repeated cancellation, operation
deadline and service shutdown defer until that one checkpoint attempt is joined.
The timer is not restarted and no callback/upstream retry occurs. Successful
handoff survives later cancellation or decoding failure. A callback failure or
timeout reports `CheckpointError` with acknowledgement unknown, even when normal
cancellation overlaps: persistence may have committed before raising.

The callback must cooperate with cancellation, avoid blocking the event loop,
and join any work it owns before returning/raising. If it suppresses cancellation
or uses non-preemptible I/O, ownership is retained until termination; a hard
wall-clock deadline cannot be promised. Re-entry into the same service, including
closing it from the callback, is rejected to prevent lock/close deadlocks.

Shared scheduler admission remains held through handoff; account/operation slots
are retained through parsing and joined cleanup. Ordinary request/response/queue
budgets remain unchanged. Replay counts payload bytes; gzip decoding additionally
counts accepted expanded bytes. Parser/body/record/text limits fail whole batches.

## Provenance and qualification

The separately inspected consumer supplies ownership and durable-handoff
requirements, not copied code or spool fixtures. External apix 1.5.3 supplies
business concepts and candidate routes only. Its metadata says MIT while the
bundled license is GPLv3; no external implementation, test, fixture or text is
incorporated. Its recent-event reader explicitly describes itself as untested
and screenshot-based, so it is not live evidence or a correctness oracle.

Original loopback fixtures and a consumer-owned filesystem sink prove receipt,
checkpoint ordering, restart decoding, repeated cancellation, callback failures,
shared saturation and bounds. Read-once live qualification remains pending and
must not use production events as routine verification. It needs a dedicated
test login with owner-controlled disposable events and separately approved
recovery/compatibility integration; the existing MCP spool cannot read this new
raw-envelope format automatically.

Fresh live scope here permits ordinary counts only: one configured login context,
one credential submission and 24 total authentication/identity/count HTTP attempts.
No read-once retrieval, message open, sending, deletion or consumer-state change.
Exact evidence and unresolved gaps belong in [VERIFICATION.md](../VERIFICATION.md).

The installed wheel used one login and ten requests to observe five shown
categories. Warm reuse dispatched nothing. Independent Chromium and same-byte
apix fields agree; no missing sixth category is fabricated. An original fixture
also exercises counters without the `button` styling class: Chromium/native agree
on those values while apix ignores them. Reference agreement is scope-specific,
not evidence that the external reader is a semantic oracle.

## Review lessons

- A callback can cancel its own task and return without a cancellable await.
  Checking only caught exceptions missed that state; a cancelled owned attempt
  is unknown acknowledgement even when it already committed.
- Check header spans, body cell roles and contradictory empty markers. Durable
  raw preservation does not justify fabricating typed records from malformed data.
- Normalize unexpected custom-transport failures at the new operation owner,
  not only at HTTP exception handlers; diagnostics must report failure too.
- Python 3.14.7 abandoned `asyncio.shield` wrappers logged already-handled
  checkpoint failures. Cancellation-neutral waits with explicit result retrieval
  preserve ownership without duplicate loop diagnostics.
- Restart proof reconstructs the whole envelope from disk, including version,
  identity, observation and codec metadata, not only the payload with in-memory
  metadata. This remains a test-owned format, not an MCP spool migration.
