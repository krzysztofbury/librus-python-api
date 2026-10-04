# 0.5 modern authentication diagnostic gates

## Pre-change review

The first approved 0.5 scope permits one private account context, one credential
submission, sixteen HTTP requests including login/redirect hops, 120 seconds and
8 MiB cumulative response bytes. Allowed work is native authentication/identity,
modern launch inspection and already-supported modern identity/council discovery.
Sending, content opens, attachments, read-once events, settings changes and other
accounts remain excluded. Stop at failure/unknown redirect; no automatic rerun.

The qualified installed 0.4.11 wheel was used with an explicitly narrowed adapter.
Original two-origin offline checks demonstrated that sends, read-once consumption
and downloads refuse before dispatch, and an unknown launch route is not followed.
One offline harness attribute error was corrected before the live scope started;
that failed harness run made no live requests or credential submissions.

The live scope verified native identity against the private plan and stopped at
an unsupported modern path after ten HTTP requests and one credential submission.
No modern handoff, send, content open, download or read-once request occurred.
The launch had the expected host, ten path fields, no query/fragment, and did not
match the known template. Only boolean shape facts were retained; that is not
enough to implement a new handoff. The scope is closed, unused budget is not
permission to rerun, and no raw URL/token/capture was retained.

TigerStyle #6 (positive and negative space): preserve exact route refusal instead
of guessing an alternate namespace. TigerStyle #2 (bounded loops): one new scope
must bound all login/handoff attempts under a shared budget. TigerStyle #12 (full
error handling): native identity success does not establish modern authentication
or authorize a send. Previously approved recipient/payload intent is conditional
on fresh exact verification and an independently approved execution budget.

## Offline diagnostic improvement and post-change review

`scripts/describe_modern_launch.py` only describes an already-received response.
It performs no HTTP, follows no URL, executes no scripts and enables no core route.
Bounded parsing retains a redacted template only for a recognizable application
namespace and the fixed token/login/target/from field labels. Dynamic values are
never returned, including unknown field values. Login encoding is compared only
against the expected private login; target/source candidates are fixed public
route/origin facts. Query/fragment/userinfo contents and token digests are absent.

Eight independently authored cases cover existing/alternate namespaces, unknown
and malformed shapes, foreign origin, userinfo/query/fragment privacy, exact field
facts and absence of private response/body/login/token values from serialized
output. The focused diagnostic/session/messaging suite passes 96 cases; Ruff and
strict typing pass. These are pure diagnostic proofs, not live route acceptance
or installed 0.5 qualification. No independent model review is claimed.

## Second independently approved launch-only scope

The owner separately approved ten requests, one credential submission, 120 seconds
and 8 MiB for native identity plus one launch GET, stopping before any handoff.
Original offline adapter checks demonstrated no handoff for either known or
unknown routes, and no forbidden dispatches. The live scope used ten requests,
one credential submission and 14,785 response bytes. Native identity matched the
private plan. The structural redactor established `pobierz12`, an alphanumeric
128-character token, exact unpadded login encoding, `/nowy` target and `synergia`
source. No token value, digest or raw URL was retained. Scope closed, zero sends
or handoffs. Public facts: `release-evidence/0.5-modern-scope-2.json`.

## Route regression and post-change review

An original two-origin wire regression failed for `pobierz12` with ACCESS_DENIED
before the fix, while `pobierz28` passed. The central endpoint catalogue and
matching OpenAPI contract now describe both exact namespaces. Full path/account/
origin validation precedes selection of the matching endpoint, with no fallback.
The new endpoint is source-informed: its launch is independently observed, but
its exchange remains offline-qualified pending installed live verification.

TigerStyle #6 (positive and negative space): the owning wire suite verifies both
namespaces using a synthetic 128-character non-hex token; rejects unobserved
near-match namespaces, foreign origins, wrong login/target/source, short tokens,
query/fragment/encoding and unsafe terminal paths; and proves zero sends. The
generic-request bypass regression includes the new authentication operation.
TigerStyle #2 (bounded loops): endpoint selection is over two fixed catalogue
entries, with one handoff and shared budget. TigerStyle #12 (full error handling):
existing modern-state cleanup remains unchanged. No independent model review
or live compatibility success is claimed.

The candidate source, installed wheel and installed sdist each pass 1,326 tests
on Python 3.13.15 and 3.14.7; one opt-in performance case is deselected. Ordinary
suite runtime/load proofs remain enabled. Installed import locations are checked
inside separate environments. The initial archive runner lacked the empty Git
marker required by checkout capture-safety tests; three tests failed, and only
the disposable harness was corrected before the complete six-way rerun. Ruff,
format and strict typing are checked separately. Candidate wheel hashes and
source manifest: `release-evidence/0.5-modern-offline-candidate.json`.
The candidate retains version 0.4.11 but differs from the released main-branch
0.4.11 artifacts. Do not substitute its hashes into that release evidence or
install it into a production consumer. Disposable artifacts were removed; a
future approved live worker must rebuild and match the qualified wheel hash.

Installed verification and the sole send remain separate fresh-budget gates.
No new scope is authorized by this document.

## Third scope: exact-number candidate does not qualify live authentication

The owner separately approved a fresh installed read-only verification with one
credential submission, sixteen requests, 120 seconds and 8 MiB, allowing one
validated handoff and identity/council discovery but no writes or content opens.
The rebuilt wheel matched the qualified candidate hash; original offline adapter
cases covered both supported namespaces, unknown-namespace refusal and zero
forbidden dispatches before live access. The live run used ten requests, one
credential submission and 14,785 bytes, verified native identity, then returned
`pobierz31` with the same redacted field facts. The exact-number candidate refused
before handoff, with ACCESS_DENIED. Zero sends or read-once requests. That scope
is closed; public facts are in `release-evidence/0.5-modern-scope-3.json`.

The namespace is not stable between launches. Supporting one more exact number
would not establish compatibility with the next launch. A bounded numbered-family
contract needs an explicit design decision, central OpenAPI route/field policy,
original boundary regressions and fresh installed verification. Observed numbers
do not prove every member of a family exists or establish the numbering algorithm.
Do not present the successful offline candidate checks as live authentication.

## Approved bounded-family policy and fourth live gate

The owner approved `pobierz` followed by 1-3 ASCII digits as a server-selected
namespace field. This is explicit compatibility policy beyond the observed
12/28/31 examples, not a claim every member exists. The one central OpenAPI path
now has a namespace parameter with the same bound; the existing operation remains
authentication-only and non-retryable. The client uses the exact server-returned
URL after full origin/login/token/target/source validation. No constructed URL,
namespace search, retry, terminal-page fetch or backend fallback is added.

Four original wire cases failed with ACCESS_DENIED before the family fix while
the two earlier numbers passed. Positive cases now cover the observed numbers
plus one/three-digit and leading-zero policy boundaries. The fixture server can
accept arbitrary namespaces so negative cases prove client refusal, not fixture
404 behavior. Negative cases reject missing/overlong/Unicode/non-numeric/case
variants before handoff, and exercise origin, userinfo, query, fragment, backslash,
token length, login and fixed target/source guards on all observed namespaces.
These are owning public-API wire proofs, not regex self-comparisons or test-only
production seams. TigerStyle #6: the broader field does not weaken other guards.
TigerStyle #2: there is still one handoff and no search loop. TigerStyle #12:
ordinary authentication/identity failure still prevents sending and clears modern
state. No independent model review is claimed.

The owner also approved one new installed read-only scope after offline
source/wheel/sdist qualification: the same one account, one credential submission,
sixteen requests, 120 seconds, 8 MiB, identity/validated handoff/council exact-leaf
verification only. All sends/content/downloads/read-once/settings/production
installation remain forbidden; stop on failure or an out-of-family shape, with
no automatic rerun. This approval does not open a send execution budget.

The approved family source/wheel/sdist candidate passes 1,353 tests on each of
Python 3.13.15 and 3.14.7, with installed import checks and one performance case
deselected. Evidence: `release-evidence/0.5-modern-family-offline-candidate.json`.
The fourth scope matched that wheel hash, verified native identity, followed one
validated `pobierz16` handoff, then stopped at modern identity with PARSE after
twelve requests, one credential submission and 15,091 response bytes. No council
lookup, send or read-once request. All contexts closed and scratch removed; no
raw token URL or response capture retained. Facts: `release-evidence/0.5-modern-scope-4.json`.
This independently exercises a new numbered handoff, not complete modern identity
or recipient verification. Identity-shape diagnosis needs fresh approval; no
parser relaxation follows from the error kind alone. All four scopes are closed.

## Fifth scope and identity-only integer normalization

The owner separately approved one shape-only identity diagnostic, with one
credential submission, twelve requests, 120 seconds and 8 MiB. Known field names/
types and owner-comparison booleans are retained; all unknown names/values and
raw response/token data stay in memory only. The pure redactor has seven original
privacy/type/bounds regressions. The initial offline adapter proof encountered
INVALID_INPUT at an unrelated mailbox form guard, before any live access; the
corrected proof reaches the actual forbidden modern-directory allowlist guard.
No production change or expanded authorization was made to satisfy that proof.

The live scope used twelve requests, one credential submission and 15,091 bytes.
Native identity matched; one numbered handoff worked. Modern identity was JSON
with integer `accountId`, string names/group/origin, and seven unknown fields.
The integer decimal value and both names matched the verified native owner;
role and origin matched existing requirements. No identity acceptance, council
lookup or send occurred. Scope closed. Facts: `release-evidence/0.5-modern-scope-5.json`.

The owning discovery/session wire regression reproduced PARSE with an invented
integer account ID before the fix. The parser now normalizes only actual Python
integers in the established 64-decimal-digit non-negative range, at identity
parsing only. `_identifier` remains strict for directory IDs; there is no global
coercion, bool/float/negative acceptance or weakened name/owner comparison.
The owning mismatch-before-send table now covers integer wrong-owner and invalid
numeric cases. Public results remain string IDs. OpenAPI and API.md describe this
wire normalization. TigerStyle #6: int membership excludes bool and preserves
all other rejection guards. TigerStyle #12: failed comparison still prevents
dispatch. Installed acceptance needs a fresh separately approved scope.

## Sixth scope: installed identity and exact council recipient qualified

The owner separately approved a fresh sixteen-request/one-credential/120-second/
8-MiB read-only scope after both-Python source/wheel/sdist qualification, including
safe field-name/type facts from already-approved responses. The candidate passes
1,366 tests in each of the six environments, with installed imports verified.
Evidence: `release-evidence/0.5-modern-identity-offline-candidate.json`.

Original installed adapter cases exercised integer identity normalization and
both ordinary and invalid integer directory data, proving diagnostic retention
does not relax directory parsing; forbidden sends/read-once/downloads refused
before dispatch. The live worker matched the qualified wheel hash. It verified
native identity, one `pobierz13` handoff, modern identity/type metadata and the
unique exact saved class-qualified council leaf. Fourteen HTTP requests, one
credential submission, 16,119 response bytes, zero sends. Modern directory IDs
were strings; no extra coercion was introduced. All response diagnostics are
recognized names/types/counts only, not names/IDs/raw captures. All contexts
closed, scratch removed and scope closed. Public facts:
`release-evidence/0.5-modern-scope-6.json`.

This passes S1 for one account/council context only. The sole-message send remains
a distinct fresh approval/budget gate; no read-only budget or restored session
may be used to bypass it. Unobserved acknowledgement envelopes remain uncertain.

## Seventh scope, independent sent-UI confirmation and acknowledgement correction

The owner freshly approved the exact sole-message sender, recipient and complete
payload with one credential submission, sixteen requests, 120 seconds and 8 MiB.
Approval also selected a new owner-only native API claim store and bounded private
receipt retention outside Git. The installed candidate hash matched the previous
six-way qualification. An original offline adapter proved a durable CLAIMED row
before POST, one send, duplicate-preview blocking without HTTP and refusal of
legacy sending, downloads and read-once consumption. A new exclusive task-state
directory additionally prevents two workers from starting the same live scope.

The live run freshly verified native/modern sender and the unique exact council
leaf, then performed the required fresh identity GET and one send POST. Sixteen
HTTP requests, one credential submission, 16,471 response bytes and exactly one
potential send dispatch. It returned HTTP 201 and 46 body bytes. The native API
reported UNKNOWN/PARSE because ordinary read validation accepted only HTTP 200;
the durable claim finished UNKNOWN and blocks duplicate previews. All contexts
and the authorization closed. No retry, fallback, group, extra recipient or
post-send upstream lookup occurred. Evidence: `release-evidence/0.5-modern-scope-7.json`.

Offline private receipt analysis established exact JSON `data` with positive
integer `messageId` and `status="sent"`. The owner independently confirmed the
exact recipient, subject and body in the official sent UI. Recipient reading is
not confirmed. Neither the private identifier nor screenshot enters this public
repository. Content type was not retained in the private receipt; JSON media type
remains an explicit conservative library guard rather than a retained-header
claim. Evidence: `release-evidence/0.5-modern-send-confirmation.json`.

An original warm wire regression reproduced UNKNOWN/PARSE for an invented exact
201 receipt before the correction. The candidate handles 201 as a send receipt,
not an ordinary read, and accepts only application/json plus that exact envelope
and a positive actual JSON integer of at most 64 decimal digits. Sixteen owning
wire cases exercise valid receipt and wrong status/type/body/marker/ID, conflicting
extra fields, duplicate keys and malformed data. The durable workflow table now
proves ACCEPTED also blocks duplicate previews; the four-account maximum-payload
case covers accepted receipts with account isolation and shared traffic budgets;
the existing completed-return-deadline proof covers modern acceptance as well as
rejection. TigerStyle #6: success alone or a positive hint remains UNKNOWN.
TigerStyle #12: complete qualified receipts survive the local deadline, and no
receipt failure permits replay. No independent model review is claimed.

The correction is qualified offline without another live send. Original UNKNOWN
history is preserved; the owner's manual observation is recorded separately,
not used to rewrite SQLite rows automatically. All seven live scopes are closed,
using 84 HTTP requests, seven credential submissions and one send in total for
this 0.5 task. Further live access requires a new scope. Version/PR/release and
broader compatibility/consumer work remain separate gates.

Final post-change checks: source/wheel/sdist each pass 1,385 tests on Python
3.13.15 and 3.14.7, one performance test deselected, with actual runtime/load/
process proofs enabled and installed imports plus receipt smoke checked. Two
builds are byte-identical. Ruff, format, strict typing, changed-file hooks and
worktree secret scan pass. Final candidate evidence:
`release-evidence/0.5-modern-ack-offline-candidate.json`. Scratch is empty. The
explicitly approved private claim/receipt total 20,629 bytes and remain outside
Git for duplicate protection/manual reconciliation. No live execution qualified
the corrected receipt parser and no 0.5 release, PR, merge or publication is
claimed. The source changes remain on the qualification branch for review.
