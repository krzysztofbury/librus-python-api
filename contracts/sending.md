# Single-use sending contract (0.4.6)

## Approved design and scope

`AccountClient.prepare_send(recipients=tuple, subject=str, body=str)` validates
and freezes a plain-text payload without I/O. The resulting `SendAttempt`
executes once with `execute(budget=...)`. No caching, coalescing, redirects,
automatic replay, post-send reauthentication, fallback or recipient lookup.
Creating a new attempt can duplicate a previous write. This is not upstream
idempotency, a confirmation token, a persistent outbox or a delivery guarantee.

The public immutable outcome is initially NOT_DISPATCHED. Before the dedicated
HTTP send entry, a library-owned callback changes it to UNKNOWN and invalidates
sent-list caches. Recognized source-informed acknowledgement layouts can change
it to ACCEPTED or REJECTED. HTTP status alone is never acceptance. Unknown,
contradictory or incomplete evidence stays UNKNOWN. Acceptance means upstream
acceptance, not recipient delivery/read confirmation.

`execute` preserves cancellation and joins owned work. The attempt remains
inspectable afterwards: queued/authentication cancellation is NOT_DISPATCHED,
post-boundary cancellation is UNKNOWN unless a terminal acknowledgement was
already established. Ordinary pre-dispatch errors raise existing typed errors;
ordinary post-boundary failures return UNKNOWN with a redacted reason. Even a
pre-dispatch failure consumes the attempt. Concurrent/repeated execution fails
without changing the original outcome or dispatching again.
In-flight snapshots are provisional; seeing NOT_DISPATCHED while work is still
running never authorizes another attempt. Reconcile only after completion or
joined cancellation. A process crash loses this local state; durable crash
recovery and duplicate prevention require the explicit optional
`PersistenceStore` workflow described in [persistence.md](persistence.md).
The process-local attempt itself remains independent of storage.

Reuse shared operation/parser/traffic budgets, account locks, isolated sessions
and joined service shutdown. Sending bypasses `_read` and its caches/flights;
the existing uncached owner has an explicit send cancellation policy. Initial
authentication is allowed once before sending, with no credential retry. A
session-expiry response after dispatch invalidates auth but never replays sending.

## Wire requirements and provenance

The send and sent-list operations share POST `/wiadomosci/1/6` but have distinct
fixed payloads, side effects and operation IDs. The OpenAPI physical operation
retains its sent-list contract and declares sending as an explicit request
variant; catalogue parity must validate both without accepting implicit aliases.
Generic transport requests cannot access the send variant. The dedicated method
owns the scheduler boundary and marks potential dispatch only after admission.

External apix 1.5.3 is a source-informed business reference only. Its metadata
advertises MIT while its bundled license is GPLv3. No code, tests, parser
fixtures or runtime fallback are incorporated. Independently authored fixtures
use invented messages and IDs. Live form/acknowledgement compatibility is pending.

The source-informed legacy form uses repeated DoKogo entries and fixed
filtrUzytkownikow, idPojemnika, Rodzaj, poprzednia, fileStorageIdentifier and
wyslij values, plus temat/tresc. No upload, pagination or extra arbitrary fields.
Exact acknowledgement text is allowlisted only in its designated result
paragraph, never substring-matched against the whole response or message body.
Unknown localized wording requires qualification, not guessed success.

## Bounds, privacy and qualification gates

Limits: 1-50 unique recipient IDs, at most 200 subject characters, 15,000 body
characters and 64 KiB for the entire encoded form. These are library policy,
not observed upstream maxima. Preserve approved text, line endings and order;
reject blank fields, unsupported controls, invalid Unicode and duplicate IDs.
Every recipient must be bound to the sender alias, including type/selection
provenance. References are forgeable structural values, not permission tokens
or proof of an intended person's identity/consent. Payloads and raw responses
are excluded from repr, diagnostics and errors.

Offline owning-boundary proofs must exercise exact repeated form fields,
admission/authentication/HTTP boundaries, concurrent execute, cancellation,
timeouts, shutdown, response loss/limits, redirects, misleading acknowledgements,
distinct accounts and shared saturation. Installed wheel and sdist suites on
Python 3.13/3.14 plus actual loopback execution are required before release.

This implementation does not authorize live access. A separately approved live
qualification is restricted to one privately recorded recipient, one message and
at most one send dispatch. No group send, substitute, additional recipient,
automatic retry or fallback. Verify the sender, exact unique recipient ID and
approved payload with fresh bounded discovery authorization; stop on ambiguity.
Keep all personal target/payload details outside this public repository. Consumer
migration and publication remain separately gated.

Later separately approved discovery resolved the sole intended recipient on the
modern backend, not the legacy route qualified offline here. The modern account
ID must not be turned into a legacy reference or sent through this form by
assumption. Modern sending support and live acknowledgement qualification remain
pending. See [modern-messages.md](modern-messages.md).
