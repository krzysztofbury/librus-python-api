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

The source-informed reader contract is a `data` object with Base64 UTF-8 `Message`
HTML. The parser checks the ID, bounds body/markup/attachment counts, rejects
active content and emits inert rendered text plus modern attachment references.
It never executes scripts, follows markup links, resolves files or infers
per-recipient receipts. This strict content layout is offline-qualified only;
no content opens were approved in this continuation. Forwarded/archive layouts
and unknown receipt variants remain unsupported.

Modern attachment downloads are deliberately not enabled. Public source indicates
resolution routes, but response envelopes, credential-free download origins and
redirect/header behavior lack enough evidence for safe streaming. Modern metadata
must not be passed to legacy `stream_attachment`. Legacy streams can use
[the optional file layer](attachment-files.md) for safe local publication.

## Qualification and unavailable evidence

Three fresh authenticated scopes are closed. The first stopped at a reporter bug,
the second at a sent-layout parse error, and the third completed its approved
reads. Total: 48 requests, three credential submissions, no content, attachment,
download, send or read-once calls. Both failures have original offline regressions.
The successful scope used 20 requests against candidate source, not an installed
package. Across candidate source scopes, the API observed populated inbox pages 1-2,
outbox page 1, teacher/tutor/school-admin/council leaves, type metadata, legacy
group discovery and an empty legacy subgroup selector on one account.

No populated legacy subgroup, modern class-parent availability, virtual class,
empty modern mailbox, sent second page, nonstandard receipt, content open or modern
download path was established. Missing account data is not a passing result.
Live candidate hashes and sanitized scope facts are in
[../release-evidence/0.5-communication-scopes.json](../release-evidence/0.5-communication-scopes.json).

Original loopback tests verify routes/queries, cookie isolation, strict selections,
page/body parsing, continuation/drift/no-partial results, consent, cache
invalidation, four-account queue saturation, cancellation, deadlines and request
budgets. Source/artifact results are in [../VERIFICATION.md](../VERIFICATION.md).
Availability JSON nonfinite-number hardening was subsequently qualified offline;
live manifest hashes identify the exact earlier observed source snapshots.
Consumer integration, merge and publication remain separate gates.
