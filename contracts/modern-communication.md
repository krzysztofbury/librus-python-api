# Modern communication continuation on PR #15

This original implementation uses separately approved public-app behavior
inspection and narrowly scoped authenticated observations. No external code,
app bundle or private response fixture is incorporated. Legacy and modern
references, cookies and cache keys stay distinct. There is no automatic backend
selection, fallback, settings mutation or consumer cutover.

## Recipient directory

All ordinary school branches use fixed allowlisted routes in `config.py`:
student/parent/guardian/council selections use students-and-attendants; teacher,
tutor, administrator and other school employee selections use school-employees;
`classParents` uses class-parents, not the council route.

Combined `parents,guardians` and virtual selection are explicit query choices.
Only `students` and `parents,guardians` can opt into the source-established virtual
suffixes. Metadata's `lookup_supported` marks a lookup implementation, not universal
availability or live qualification. Unsupported metadata remains visible.
Discovery accepts the exact allowlisted combined `parents,guardians` identifier;
other compound identifiers are not treated as supported selections.

The strict class shape also accepts the source-established `data` envelope.
Employee results preserve account/user IDs and labels without inventing a class.
Optional availability is bounded inert JSON, not an inferred permission or
delivery rule. Ambiguous IDs, unsupported trees and unexpected fields fail the
whole lookup. IDs stay strict decimal strings. Cache keys and references retain
virtual selection; only account ID enters the existing direct-send payload.
Discovery neither authorizes a send nor qualifies its receipt.

## Mailbox summaries and continuation

`modern_messages_page` uses one-based `page` and bounded `limit` on explicit
inbox/outbox GETs. Summary reads never open content or resolve attachments, and
do not retain the upstream preview as a full message body. Values preserve
correspondent, subject, timestamps and attachment presence. Inbox requires its
read-date field; observed outbox rows omit it. Missing outbox read status stays
unknown, never establishing unread, recipient reading or delivery acceptance.

`modern_messages` uses explicit page/item limits, one shared budget and
account/folder/page-size-bound cursors. Mid-page resume checks a stable fingerprint
excluding mutable read status. Total-count drift, repeated/no-progress pages,
malformed later pages and exhausted ID history fail without partial output.
Boundary resume skips seen IDs with an explicit count. This is best-effort
collection, not a server snapshot: concurrent reordering can omit unseen records
without changing the total. The 1,000-page and 50,000-message bounds are library
policy, not upstream capacity claims. These reads never automatically retry.

## Content and inert attachment metadata

`ModernMessageReference` cannot be used as a legacy reference or in another
account. Received content requires `allow_mark_read=True`, conservatively
classifying the GET as potentially mark-read. Inbox summary caches are invalidated
before dispatch. Sent content has no inferred read effect. Both paths use the
modern session, shared scheduler and caller budget.

The reader contract is a `data` object with Base64 UTF-8 `Message`: plain text,
HTML, or a bounded XML `Message` wrapper with exactly one text/CDATA `Content`.
An optional UTF-8 BOM, comments and processing instructions before the XML root
do not bypass wrapper validation. Conflicting XML encoding declarations are
rejected rather than silently changing UTF-8 text. Physical line breaks are
preserved before inert HTML text rendering. XML network,
DTD and entity access is prohibited. Duplicate/nested content elements and active
markup fail closed. Details derive attachment presence from the actual attachment
list because independently observed responses omit the list-only flag. An explicit
inconsistent flag is rejected rather than silently corrected.

Optional `originalMessage`/`originalTopic` preserve an inert original body/subject,
with explicit `withdrawn` and `archived` flags. Archived attachment references
carry their namespace and use a distinct resolver; no automatic archive fallback.
Archive/withdrawal variants remain source-informed and offline-qualified, not
live-qualified. Unknown or malformed receipt layouts fail without partial output.

## Recipient read observations, not invented delivery acknowledgements

Sent details expose `recipient_receipts`, `recipient_count`, `read_count` and
`receipt_source`. The source-established `individualRecipients` roster takes
precedence when present; otherwise `receivers` is used. Each receipt retains a
strict decimal-string `recipient_id`, display `name`, `to`/`cc`/`bcc` channel and
optional timestamp. Present `readed` null/empty means no reading was observed;
an absent field means unknown. A valid timestamp means reading was observed at
that time. Duplicate recipient IDs, ambiguous CC/BCC flags, malformed dates and
invalid counts fail the entire parse. Receipt rosters and text have fixed bounds.

Aggregate counts are upstream observations, not a library assertion that a group
roster is exhaustive; they are not equated to the number of visible leaves.
No independently meaningful delivery-status field was established. `delivered`
therefore remains `None`, even when a read timestamp exists. Nothing here changes
a durable send's acceptance status, reconciles UNKNOWN history or permits resends.
Ordinary single-recipient read and null observations were candidate-API qualified;
expanded rosters and CC/BCC were source-informed and independently tested offline.

## Modern attachment streaming

`stream_modern_attachment` is an explicit, uncached, single-owner async stream.
Construction performs no I/O and validates account, backend, IDs and archive flag.
It binds the isolated modern session and resolves the attachment through
`modern_attachment_resolve`, or explicit `modern_archive_attachment_resolve`.
The JSON `data.downloadLink` must match the existing exact official sandbox
`/GetFile/{key}` contract. Userinfo, queries, fragments, alternate origins,
encoded separators and unsupported key shapes are denied before download.

Only the validated key enters the existing fixed `/GetFile/{key}/get` byte route.
The resolver's URL is never followed or exposed. Downloads use the same separate
cookie-free, credential-free session as legacy attachments, with no redirects,
retries, Referer or ambient environment credentials. Account transport limits,
shared admission, caller request/byte/deadline budgets, body-length checks,
backpressure, consumer-idle timeouts and joined service-owned cancellation apply.
Resolver expiry clears modern state without merging or clearing valid native
sessions; sandbox denial does not prove account-session expiry.

Modern references remain prohibited in legacy `stream_attachment`. Optional
[file publication](attachment-files.md) accepts the modern stream subclass and
requires the same explicit caller-selected destination. No new automatic file
storage is introduced. Custom transports may optionally implement
`resolve_modern_attachment(reference, budget)`; otherwise this feature reports
`UNSUPPORTED_CAPABILITY`. The core transport contract stays usable by legacy
implementations.

## Qualification and unavailable evidence

Three fresh authenticated scopes are closed. The first stopped at a reporter bug,
the second at a sent-layout parse error, and the third completed its approved
reads. Total: 48 requests, three credential submissions, no content, attachment,
download, send or read-once calls. Both failures have original offline regressions.
The successful scope used 20 requests against candidate source, not an installed
package. Across candidate source scopes, the API observed populated inbox pages 1-2,
outbox page 1, teacher/tutor/school-admin/council leaves, type metadata, legacy
group discovery and an empty legacy subgroup selector on one account.

At that stage no populated legacy subgroup, modern class-parent availability,
virtual class, empty modern mailbox, sent second page, richer receipt, content
open or modern download path was established. The next expansion qualified the
available subset below. Missing account data is not a passing result.
Live candidate hashes and sanitized scope facts are in
[../release-evidence/0.5-communication-scopes.json](../release-evidence/0.5-communication-scopes.json).

Original loopback tests verify routes/queries, cookie isolation, strict selections,
page/body parsing, continuation/drift/no-partial results, consent, cache
invalidation, four-account queue saturation, cancellation, deadlines and request
budgets. Source/artifact results are in [../VERIFICATION.md](../VERIFICATION.md).
Availability JSON nonfinite-number hardening was subsequently qualified offline;
live manifest hashes identify the exact earlier observed source snapshots.
Consumer integration, merge and publication remain separate gates.

## Subsequent expansion on the same PR

Two public discovery scopes completed with five unauthenticated asset GETs total,
without cookies, credentials, execution, writes or copied code/fixtures. Four
fresh authenticated scopes are closed, totaling 136 requests and eight credential
submissions across isolated login contexts. These are separate from the three
historical scopes above. Evidence:
`release-evidence/0.5-communication-expansion-scopes.json`.

- Four-login inventory qualified empty student outboxes, populated second sent
  page at size five, and existing inbox pages. None advertised class-parent,
  student or combined-parent branches; all legacy subgroup selectors were empty.
  No unsupported directory probe or identity-based session merging was attempted.
- A dedicated inspection observed two already-read received details, two existing
  sent details and two resolver envelopes. No downloads in that inspection.
- The first candidate check parsed received content but stopped when the first
  file exceeded its approved 5 MiB ceiling. Partial bytes were discarded, not
  retained or published; the scope was closed and never rerun.
- A separately approved remaining-check scope qualified another complete modern
  stream (7,004,902 bytes, bounded at 8 MiB), plain and XML content, sent read/null
  observations and one consented unread-to-read transition with before/after
  mailbox timestamps. No payload bytes or signed URLs were retained.

Archive/withdrawn originals, expanded recipient rosters, virtual/class-parent and
populated legacy subgroups still lack live data. Independent delivery status is
unavailable in the established contract. No new send, read-once event consumption,
MCP migration, merge or publication occurred. The original UNKNOWN send guard is
unchanged. Further live qualification requires fresh authorization and suitable
account data, not synthetic success claims or speculative requests.

## External compatibility review and deferred work

The pinned reference-client review found no modern/archive, virtual,
populated-subgroup or expanded-recipient implementation that closes these gaps.
Its legacy sent boolean is not independent delivery evidence. The current
independent implementation is retained without an external fallback or copied
fixtures. See [VERIFICATION.md](../VERIFICATION.md#reference-client-and-provenance).

Archive attachment resolution and archived flags in an ordinary detail response
must not be confused with archive mailbox navigation: explicit archive list/detail
APIs and archive-qualified message navigation are not implemented. That contract
work, plus remaining live layout/availability evidence and independent delivery
semantics, stays in TODO C01-C05. Suitable evidence and fresh authorization are
required to resume; repeated checks on unavailable data are not planned.
