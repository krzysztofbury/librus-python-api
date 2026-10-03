# Message content contract (0.4.2)

Received and sent opens use their existing folder-bound numeric references.
Received opens are conservatively classified as potentially mark-read and
require explicit consent. Both routes prohibit automatic replay and redirects;
expired sessions are invalidated, not recovered within that open. An ambiguous
failure is not proof that read state remained unchanged. The shared transport
disables aiohttp's hidden persistent-connection retry for every request so each
actual attempt is owned by the scheduler and operation budget.

The pure parser requires one three-row labelled metadata table, one body
container and at most one labelled read-receipt table. Required labels and civil
timestamps are validated, never position-only apix fallback. Supported block
boundaries become line breaks; text is never truncated. Empty content is valid
only inside the recognized structure. Active content is never evaluated.

Attachment metadata recognizes bounded quoted relative download paths in icon
handlers, including JS slash escaping. It does not execute the surrounding
handler, expose a fetchable URL or enable a download route. File/message IDs are
validated and the displayed filename is inert, untrusted text. Unknown marked
paths, anchor layouts, duplicate IDs and foreign message IDs fail explicitly.

## Provenance and evidence

The separately acquired apix 1.5.3 content reader informed the
three main fields/body requirements; existing native list observations establish
folder reference families. The separately scoped consumer's independently
implemented attachment flow informed numeric file/message linkage and filename
labels. No external code, test or fixture was copied, and neither project is a
runtime dependency. Fixtures are independently authored with invented values.
The external metadata advertises MIT but its bundled license is GPLv3; no
external implementation or fixture is incorporated despite that inconsistency.
Attachment conventions from a consumer are source-informed requirements, not
this library's independently observed live behavior.

Fresh bounded approval covers one login context, two attempts of at most 24
requests each, identity, received/sent page zero, and at most two opens of one
already-read received message per attempt. No unread open, send, delete,
download or read-once operation is authorized. Captures are owner-only outside
Git; comparisons emit counts/classifications and the captures are deleted.

`scripts/capture_message_content.py` owns those bounds and the already-read
selection gate. `scripts/compare_message_content.py` gives apix the identical
bytes through an inert client, not its live network stack. Chromium independently
checks visible metadata, rendered body line boundaries, optional receipt and
file markers with scripting/networking disabled. `scripts/replay_message_content.py`
exercises installed public runtime against captures on loopback only.
Its field expectations are recorded independently from Chromium rendering in
owner-only `rendered-content.json`, deleted with the captures.

Apix omits attachment metadata and read receipts. Its agreement on common
fields is not a correctness oracle. Exact qualification, request accounting and
remaining gaps are in [VERIFICATION.md](../VERIFICATION.md). Streams are 0.4.3;
sending remains separately planned and authorized.

Later 0.4.3 qualification observes one populated attachment layout on two
already-read content responses. Filename and message/file route linkage agree
with independent Chromium rendering; the installed wheel streams that selected
file. This closes that narrow metadata gap, not every handler/role/layout gap.
The content method itself remains inert and never downloads automatically.
See [the stream contract](attachments.md) for its separate limits and evidence.

## 0.4.5 sent content and individual receipts

Two independently captured sent opens show only subject/date metadata, without
an `Adresat` row. A separate table has a one-cell `Przeczytano` heading spanning
three columns, followed by two-cell recipient/date rows. Original invented
fixtures protect this layout, missing/unknown values, mixed or duplicate receipt
tables, incorrect spans and limits before a whole typed result can succeed.

`correspondent=None` preserves the absent field. Ordered individual receipts
preserve displayed recipient text and raw status, with a civil timestamp for
reported dates and no timestamp for the source-informed `NIE` status. Equal
labels are not merged; no upstream recipient ID or aggregate read time is
invented. Existing received/global receipt behavior is unchanged. An absent
individual table is not a claim that a message had no recipients.

Individual receipt bounds are 256 rows, 4,096 characters per field and 128 KiB
total text, plus existing whole-response/parser/operation budgets. Four maximum
sent responses, including full bodies and attachment metadata, exercise the
same exact shared 24-request budget as the existing received-content proof.

Chromium independently checks metadata/body/receipt fields on identical private
bytes with scripts/networking disabled. Apix 1.5.3 rejects the observed two-row
metadata layout with ParseError; that is a classified capability difference,
not a native fallback or proof that apix is the semantic oracle. The receipt
and body semantics agree with the independent rendered evidence.

No received content was opened in 0.4.5. Sent downloads, richer metadata,
multiple-recipient live receipts and other read-status variants remain pending.
