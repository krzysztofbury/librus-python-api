# Communication gap review against librus-apix 1.5.3

## Scope and provenance

Reviewed on 2026-10-04: the latest published PyPI `librus-apix` release, 1.5.3,
and its matching `v1.5.3` GitHub revision
`2fedfe8ffa4933abb884929716519ddbeb8eb32d`. The historical project URL redirects
from `poroknights/librus-apix` to `RustySnek/librus-apix`. This is a pinned review,
not a claim about future releases or other forks.

Sources: [published release](https://pypi.org/project/librus-apix/1.5.3/),
[messaging module](https://github.com/RustySnek/librus-apix/blob/2fedfe8ffa4933abb884929716519ddbeb8eb32d/librus_apix/messages.py),
[route catalogue](https://github.com/RustySnek/librus-apix/blob/2fedfe8ffa4933abb884929716519ddbeb8eb32d/librus_apix/urls.py),
[HTTP client](https://github.com/RustySnek/librus-apix/blob/2fedfe8ffa4933abb884929716519ddbeb8eb32d/librus_apix/client.py)
and [license](https://github.com/RustySnek/librus-apix/blob/2fedfe8ffa4933abb884929716519ddbeb8eb32d/LICENSE).

The published wheel's `messages.py`, `urls.py` and `client.py` are byte-identical
to the pinned source. Source inspection also covered the package entry point,
messaging documentation, README, metadata and license. No third-party code was
executed. The external wheel was inspected in memory, not installed, extracted
or retained. No implementation, documentation, tests or fixtures were copied.

PyPI/package metadata advertises MIT, while the repository and bundled license
contain GPLv3. This remains a provenance warning, not a declaration that copying
is permitted under MIT. This library's implementation and fixtures are original.
Review facts and hashes: [../release-evidence/0.5-apix-communication-review.json](../release-evidence/0.5-apix-communication-review.json).

## Capability comparison

| Remaining area | Reviewed external behavior | Current independent library and disposition |
| --- | --- | --- |
| Independent recipient delivery acknowledgement | No dedicated delivery model, timestamp or acknowledgement. Legacy sent parsing exposes a single `unread` boolean, not recipient delivery evidence | Keep backend acceptance, recipient reading and independent delivery separate. Delivery remains unknown; TODO C01 |
| Virtual/class-parent directories | Legacy group-token discovery and label-to-ID lookup only. Virtual selection is fixed off. No modern type discovery or class-parent route | Explicit modern virtual and class-parent lookups already have original offline wire tests. Missing live availability stays TODO C02 |
| Populated legacy subgroups | Lookup fixes subgroup selection to zero; there is no subgroup-choice API or positive-selection parameter | Bounded root choice discovery and explicit positive selection already exist independently. Populated live examples stay TODO C03 |
| Archive/withdrawn-original layouts | Legacy content result includes only correspondent, subject, body and date. No archive navigation, original-body metadata or archive attachment resolver | Original/withdrawal flags and explicit archive attachment resolution have offline tests. Archive list/detail navigation is not implemented; separate route/reference contracts and live layout evidence stay TODO C04 |
| Expanded and CC/BCC recipient receipts | No per-recipient receipt collection or CC/BCC read-status parsing | The modern parser already preserves source-established rosters, channel and read/null/unknown observations. Expanded live layouts stay TODO C05 |
| Attachment download, for comparison | A mailbox attachment indicator only; no dedicated resolver or byte-stream implementation | Ordinary modern and legacy streams are already implemented with strict destinations and isolated credential-free downloads. No missing external stream logic to reproduce |

The reviewed communication routes are legacy Synergia HTML routes. An arbitrary
URL-capable HTTP client is not a modern mailbox, archive, subgroup or receipt
implementation, and is not evidence that a particular account can use such a
feature. No external logic closes the remaining gaps.

## Deliberate semantic differences

The external sent parser compares a parsed HTML element to a string when deriving
its `unread` flag. That is not a reliable interpretation of visible recipient
status and must not be promoted into a delivery acknowledgement. Its send helper
also does not provide an independently qualified delivery/read receipt. Neither
behavior is imported into this library, and no external send was executed.

Repeated display labels can overwrite IDs in the external name-keyed recipient
mapping. Native lookup preserves ordered ID-bearing records and rejects ambiguous
IDs. Its broader choice/metadata support must not be reduced merely to match a
less expressive external return type.

This review changes documentation and backlog only. Runtime APIs, routes, tests,
version, dependencies, qualified implementation hashes and durable send history
remain unchanged. No fallback, speculative endpoint, credentialed Librus request,
new send or migration is introduced. Existing source-informed/offline coverage
remains available, with exact live limits in
[modern-communication.md](modern-communication.md).

Remaining tasks are explicitly tracked as C01-C05 in [../TODO.md](../TODO.md).
They may be resumed if qualifying contract evidence or suitable data becomes
available, with separate authorization for any live access. Repeated empty
discoveries or synthetic fixture success do not close those tasks.
