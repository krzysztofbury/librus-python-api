# Attachment streams (0.4.3)

## Pair-programmer design

Use a single-owner context-managed stream, not the ordinary cached/coalesced
read path. One service-owned worker retains the account lock and operation slot.
The download retains shared scheduler admission through EOF, failure or early
close, including consumer pauses. A one-chunk demand/delivery handoff bounds
memory and an absolute operation deadline terminates paused consumers. From
0.4.11 every demand wait also has a separately configurable
`TransportLimits.attachment_idle_timeout_seconds` (default 15 seconds), so a long
caller budget cannot let a paused consumer monopolize shared admission. Waiting
for network bytes is not idle consumer time. Expiry reports TIMEOUT, keeps
`complete=False`, joins/closes transport work and frees admission without replay.

Safety takes priority over overlapping requests on the same account. Two fixed
requests resolve a numeric message/file reference and stream the validated
signed sandbox key using a separate session/connector with a dummy cookie jar.
No source credentials, cookies, Authorization, Referer or Origin are forwarded.
Explicit trusted-proxy configuration remains possible; environment proxy/netrc
configuration is disabled. Both hops share the same scheduler and operation
budget. No retry, redirect following, range/resume or content-open fallback.

Validate account/folder/message/file references before authentication. Signed
destinations use exact origin and path grammar, bounded unreserved key characters
and no userinfo, query, fragment, controls, percent encoding or traversal. Only
the official verified HTTPS origin or an explicitly configured loopback override
is permitted. Signed URLs never become public metadata or diagnostic/error data.

From 0.4.11 unsupported signed route/key/encoding shapes report
UNSUPPORTED_CAPABILITY, not ACCESS_DENIED, and do not install a permission cooldown.
Unambiguous foreign origin/scheme/userinfo violations remain ACCESS_DENIED.
All failures still prevent download dispatch; actual HTTP 403 remains a denial.

Actual bytes count before delivery. Content-Length is an early bound, not proof
of completed delivery. Unknown length is allowed; premature framing, unsupported
encoding, limits and deadlines fail rather than silently returning EOF. Clean
EOF plus joined transport work determines completion. Context exit, explicit
close, entry/read cancellation and service shutdown abort and join owned work.

The library does not name, save or publish files. Callers own sinks and must not
publish partial data. Default cumulative service budgets remain 4 MiB, including
login/source bytes; the 50 MiB attachment ceiling does not enlarge that budget.
Ordinary HTML/parser limits remain unchanged.

## Provenance and qualification

The separately scoped consumer's independent attachment flow informs the legacy
two-hop routes, not their complete correctness. No external implementation or
fixtures are copied. The reference client has no native attachment-download contract.
Original loopback fixtures own wire, isolation, streaming, bounds, cancellation
and saturation behavior. The installed wheel observed one exact two-hop route
and streamed 930,056 bytes to clean EOF, with no declared length. The key grammar
remains a conservative compatibility restriction, not an exhaustive upstream
contract. `none` remains a provisional effect classification, not proven absence
of upstream read effects.

Fresh live approval permits discovery on four independent configured logins:
one login and 24 total requests each, identity, page-zero received/sent lists,
at most one already-read received message with an attachment per login. A fifth
login is reserved for installed smoke on a selected eligible account, capped at
24 requests and one attachment up to 10 MiB. Three discovery logins were used;
the fourth was unnecessary after an eligible attachment was found. The reserved
installed-smoke login completed. No unread opens, sending, deletion
or read-once requests. Stop when no eligible selection exists or a response is
ambiguous. Retain only sanitized counts/classifications, never file contents.

Pair-programmer post-implementation review, exact offline/runtime results and
remaining gaps belong in [VERIFICATION.md](../VERIFICATION.md). MCP sink naming
and atomic-publication integration remain separately authorized follow-ups.

## Qualification lessons

- All HTTP encoding fields must be checked before delivery. Duplicate content
  codings or unsupported transfer codings bypassed a first-field-only guard and
  reported successful gzip bytes. Independent raw-wire regressions failed
  before the fix; ordinary chunked framing is paired with the negative cases.
- Browser attachment expectations must extract only the route literal. Popup
  names and dimensions also contain numbers; collecting every number from an
  inert onclick handler produced a false file-ID mismatch. Scripts stay disabled.
- A small successful live file does not prove bounded load or cancellation.
  Original offline proofs stream a full 50 MiB file and saturate shared admission
  with four independent logins, mixed reads/downloads and an exact wire budget.
