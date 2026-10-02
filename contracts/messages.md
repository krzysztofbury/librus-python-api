# Message lists and communication increments

## 0.4.0 contract

The ordinary received/sent list is a fixed pagination POST per page. The sent
URL also serves sending, but the library allows exactly `numer_strony105` and
`porcjowanie_pojemnik105=105`. Missing, extra, send/body/recipient/upload fields
are refused before dispatch. No send, content, attachment, delete or read-once
route is enabled in this version.

The parser checks the legacy table header, reads only its `tbody`, accepts an
explicit `Brak wiadomości` row, and ignores the blank `tfoot`. The observed
legacy-module information banner is allowlisted; other warnings remain typed
failures, not empty success. IDs must be numeric, folder-bound links on both
correspondent and subject. `/f0` is an inert suffix, never a fetched URL.

Page counts come from the same response. No pagination on page zero means one
page, as observed on both folders. A requested nonzero page without metadata is
not accepted as an empty range. Populated pagination is source-informed and
checked with original fixtures, not live-qualified yet.

Bounds, continuation, deduplication, timestamp and status semantics are specified
in [API.md](../API.md#message-lists). All reads share the existing account-lock,
scheduler, cache/coalescing, parser-worker and operation-budget boundary. POSTs
are not replayed. A later-page failure never exposes or caches partial output.

## Independent evidence and provenance

Requirements were informed by the external `librus-apix` 1.5.3
distribution (metadata homepage: https://github.com/poroknights/librus-apix), and
by the consumer's bounded mailbox collection requirements. No implementation,
fixture or test from that distribution or the consumer was copied here. Original
fixtures use independently observed layout with invented values. No apix runtime
dependency or fallback is added.

Its package metadata advertises MIT while its bundled license is GPLv3. Treat
that inconsistency as a provenance warning, not an assertion of MIT licensing.
Implementation and fixtures here remain independent.

Private authorized captures are replayed using only apix's pure parsers by
`scripts/compare_messages.py`, never another login or network client. Chromium
uses the same bytes with scripts and networking disabled to independently check
visible fields, computed unread flags, attachments, references and empty markers.
Only sanitized counts/classifications are retained; raw pages and field diffs
are deleted. Agreement with apix is not a correctness oracle.

| External capability | Native 0.4.0 | Evidence / difference |
| --- | --- | --- |
| `get_received`, `parse` | `messages_page(RECEIVED)`, `messages(RECEIVED)` | Populated page zero observed; identical-byte replay agrees on every summary field |
| `get_sent`, `parse_sent` | Same calls with `SENT` | Empty page and header observed; populated rows have offline original proof only |
| `get_max_page_number` | `MessagesPage.page_count` | Derived per folder from its list response; no extra GET or received-count reuse for sent mail |
| Caller pagination / collection | Account/folder-bound bounded cursor | Unique IDs, overlap deduplication, page-count drift, mid-page fingerprints and non-progress rejection |
| Received bold style | Typed `unread` | Same meaning, checked against Chromium computed style; numeric CSS bold supported |
| Sent recipient status | Raw `recipient_read_status`; `unread=None` | Apix compares a tag with `"NIE"`, which is not a valid recipient-status interpretation; never inherit this behavior |
| `recipient_groups`, `get_recipients` | Implemented in 0.4.1 | Simple-group lookup and named discovery; [separate contract](recipients.md) |
| `message_content` | Implemented in 0.4.2 | Explicit potential mark-read consent, full text and send/read civil timestamps; qualified only for an already-read received message |
| Attachment indicator | `has_attachment` | Indicator only; separate native streams implemented in 0.4.3, not an apix capability |
| Notification helpers / read-once events | Deferred to 0.4.4 | Callback handoff, not persistence owned by the library |
| `send_message` | Plan-only | Separate approval gate; no live send in list qualification |

Live qualification is limited to one login: a populated two-row received page
and an explicitly empty sent page. Populated sent rows, multi-page metadata,
attachment indicators, other account roles and the newer
mailbox layout remain pending. See [VERIFICATION.md](../VERIFICATION.md).

Later 0.4.3 evidence extends page-zero lists to 35 received and eight populated
sent rows, plus populated attachment flags and one content attachment reference.
Independent Chromium and same-byte apix common fields agree. Pagination and
newer layouts remain pending; native streams have no apix parity counterpart.

## Feature/version sequence

Each version is independently tested and locally packaged. No consumer changes
or PyPI publication are part of these increments.

1. **0.4.0 - Lists:** ordinary received/sent summaries and bounded continuation.
2. **0.4.1 - Recipient discovery:** source/account-bound groups and recipients,
   deduplicated bounded lookup. Fresh bounded authorization before live discovery.
3. **0.4.2 - Content:** full message text and inert attachment metadata. Classify
   received opens as potentially mark-read before enabling any live test. Require
   a specific approved message or an approved already-read/sent selection.
4. **0.4.3 - Streams:** allowlisted credential-free destinations, bounded bytes,
   deadlines and cancellation. MCP retains file naming and atomic publication;
   its integration is separately authorized.
5. **0.4.4 - Notification primitives:** checkpoint callback with durable handoff
   and cancellation semantics. Never consume live read-once events as routine
   verification. MCP retains seen-state, hashes, spool replay and migrations.
6. **Sending - plan first, version not assigned:** agree on the contract and
   qualification scope before implementation. The proposed boundary is a
   validated unique account-bound recipient set, bounded subject/body, exactly
   one dispatch and typed accepted/rejected/unknown-delivery outcomes. Timeout,
   cancellation or an unknown response after dispatch must never cause replay,
   a fallback backend or an unqualified success. MCP retains preview/confirmation
   tokens. First qualification is loopback fault injection; any later live send
   needs a named consenting recipient, exact approved content and an explicit
   one-attempt budget. No recipient contact is authorized by this roadmap.

   The future manual qualification case is one Polish automation-test message to
   one privately specified recipient. Its approved payload must identify the
   sender and the automation test, say that no reply is needed, and apologize for
   the unsolicited message. Keep the recipient and exact text outside this public
   repository. This case belongs to the separate sending increment, not 0.4.2;
   it does not bypass offline fault tests, exact-recipient/sender verification or
   fresh bounded authentication/discovery approval. At most one send dispatch,
   with no retry or fallback after an ambiguous result.

## Qualification lessons

- A message detail has two exact `stretch` tables: main metadata and an optional
  separate `Przeczytano` receipt. Treating every matching table as main metadata
  rejected a real already-read message. An independently authored regression
  failed before receipt-aware parsing was added.
- lxml comments do not behave like HTML elements for attribute defaults. A page
  comment caused a raw `TypeError` in attachment discovery; skip non-element
  nodes, with a failing-before-fix regression.
- HTTP GET is not evidence of no side effects. aiohttp's persistent-connection
  retry can replay a potentially mark-read GET outside scheduler accounting.
  A real loopback disconnect regression proves that hidden replay is disabled.

- Discover real populated and explicit-empty layouts before treating fixtures as
  wire evidence. A blank footer and an informational banner broke the first
  offline replay even though synthetic tests passed; four failing original
  regressions were added before the correction.
- Account for actual authentication hops, not a guessed five-request handshake.
  The live path here uses nine requests including identity. A list scope counts
  all hops and forbids a second credential submission.
- A tiny live mailbox proves semantics, not pagination/load support. Preserve
  those gaps and exercise full bounded multi-account collections offline.
- Scope is per attempt. Unused requests never authorize a third login or an
  operation with a different side effect.
