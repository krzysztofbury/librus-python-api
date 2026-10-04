# Modern messaging: explicit backend and 0.5.0 qualification

The modern composer at `https://wiadomosci.librus.pl/nowy/` is a separate
messaging backend from the legacy Synergia HTML routes implemented in 0.4.6.
Successful modern recipient discovery does not qualify legacy lookup or sending.
0.4.7 implements an explicit, offline-qualified modern backend. No automatic
fallback, account-setting mutation or cross-backend ID reuse is implemented.
0.5.0 qualification observed one separately approved sole-recipient send and its
created/sent acknowledgement, independently confirmed by the owner in the official
sent UI. This is not universal receipt/layout qualification or recipient reading.

## 0.4.11 offline session recovery

A launch redirect to an exact native login route reports SESSION_EXPIRED, not
ACCESS_DENIED, without following it. Foreign origins, mismatched login/token/target
and unsupported handoff shapes remain denied. This classification does not establish
the still-unqualified replacement live handoff layout.

Every modern send freshly verifies the existing side-effect-free modern identity
GET before dispatch. Cold binding already includes this GET; a warm binding adds
one GET to the caller's shared budget. Failure leaves NOT_DISPATCHED. Modern
401/403 and transport/validation errors clear modern binding/cookies/cache without
discarding a valid legacy session. A proven native launch expiry still expires
native state. Existing retry-safe flags are unchanged: a later explicit call may
rebind modern state, but this slice never automatically retries a modern read or
write. Revalidation cannot prevent expiry between GET and POST; potential dispatch
still means UNKNOWN until a definitive acknowledgement and is never replayed.

## Independently observed read-only discovery

The separately approved 0.5 launch-only diagnostic independently established an
additional exact namespace, `pobierz12`, with the same login/target/source field
facts. An initial exact-number candidate preserved `pobierz28`, but the next
installed verification returned `pobierz31` and safely stopped before handoff.
The owner then approved a bounded server-selected namespace family: `pobierz`
followed by 1-3 ASCII digits. This bound is library compatibility policy, not
evidence that every number exists or proof of the numbering algorithm. The
candidate follows only the validated URL actually returned, never constructs
alternative namespaces, retries a handoff or falls back. Origin, exact login,
token limits, fixed target/source and terminal route checks remain unchanged.
See [modern-launch-diagnostics.md](modern-launch-diagnostics.md) for scope closure,
policy decision, original regressions and installed live qualification status.
The fourth approved installed scope successfully followed one validated numbered
handoff, then stopped at modern identity parsing. No identity/recipient acceptance
or send is established. All scopes are closed; the next identity diagnostic
requires fresh approval.
The fifth shape-only scope established that modern `accountId` is a JSON integer;
its decimal value, names, string role and origin matched the verified native
owner. No identity was accepted by that diagnostic. The candidate now normalizes
only bounded non-negative identity integers to decimal strings before the existing
owner/name comparison. Recipient identifiers remain unchanged; bool, float,
negative and oversized identity values remain parse errors. Fresh installed
identity and council verification is still required.
That verification passed in the sixth freshly approved installed scope: native
and modern sender matched, and the exact saved class-qualified council leaf
matched uniquely. Fourteen requests, one credential submission, no send, scope
closed. This qualifies one explicit account/council context, not arbitrary roles
or directories. The next sole-send execution has its own fresh approval gate.

One separately approved account context used the qualified installed 0.4.6 wheel
for initial authentication and identity, followed by a private investigation
adapter for staged GET requests. The adapter reused the same account session,
native scheduler and one shared 32-request/byte/deadline budget. Requests did not
follow redirects or execute app scripts automatically. Exact handoffs and
subsequent routes were reviewed before each dispatch. One credential submission
and 19 HTTP requests were used. No sending, mailbox content, settings changes,
downloads, deletes or read-once requests occurred.

Observed flow and boundaries:

- The authenticated legacy composer links `/wiadomosci3` as the new-system entry.
  That route redirects to a modern MultiDomainLogon token handoff, then `/nowy`.
  Token URLs and cookies are credentials: private, used once and never retained
  in public evidence. Public HTML/assets alone do not prove authentication.
- The captured modern HTML references app bundles; those reference
  `/nowy/config.json`. Its observed API base is `/api` on the modern origin.
- `GET /api/me` identifies the modern account. Its account ID matched the
  independently verified native owner ID; the account role and origin system
  also matched the selected context. This is identity verification, not license
  to merge account sessions or caches.
- `GET /api/receivers/types?includeClass=true` supplies directory type metadata.
  The observed council type is `parentsCouncil`. The shipped app maps that type
  to the students-and-attendants group route, not the class-parents route.
- Expanding that branch performs
  `GET /api/receivers/groups/students-and-attendants?receiverType=parentsCouncil`.
  The observed response contains `classes`, each with a class `label` and a
  nested `receivers` array. Leaf entries contain `accountId`, `userId` and `name`.
  The one privately intended class-qualified recipient resolved uniquely.

This establishes one populated council layout on one account only. It does not
establish universal type/class layouts, absent/disabled recipients, virtual
classes, pagination or send compatibility. Scope ended after discovery; unused
requests authorize no rerun, additional council or live send.

## Independent offline browser check

Chromium rendered the captured app bundles against the exact captured composer,
config, account identity, type metadata and council response bytes. All browser
network requests were intercepted in an offline, service-worker-disabled context.
The receiver dialog and council/class branch were expanded without selecting a
recipient, saving a draft or sending. The unique intended leaf rendered under
the intended class, and its DOM leaf key matched the JSON recipient account ID.

Ancillary subject captions, crossed-out-student metadata and signatures used
explicit invented empty stubs; CSS was stubbed. Unread-count, external fonts and
any other non-allowlisted traffic were blocked, including telemetry in earlier
offline attempts. This verifies the directory's account-ID mapping and tree
semantics, not styling, unrelated account data or whole-app live compatibility.
The inspected app code is an external behavior reference only. No bundles,
implementation excerpts, private captures or derived personal fixtures were
incorporated in the repository. The implementation uses independently authored
synthetic fixtures, not sanitized copies of private response data.

## Implemented scope and remaining live gates

Prioritize explicit modern-backend support over guessing legacy class selectors.
No retirement date or universal migration policy for legacy messaging has been
established. Account settings must not be silently toggled to select a backend.

The approved 0.4.7 scope implements the following boundaries:

1. Preserve existing 0.4.6
   single-use attempts, cancellation/uncertainty semantics and shared budgets.
2. Modern origin, authentication handoff and all enabled routes are centralized
   in `config.py`, with matching OpenAPI operations and original offline wire
   proofs. The investigation adapter is not a shipped library interface.
3. Separate `ModernRecipientTypeReference` and `ModernRecipientReference` bind
   the independent account alias and modern backend. Modern
   recipient `accountId`, modern `userId` and legacy recipient IDs must not be
   conflated or accepted across backends without separately established proof.
4. `prepare_modern_send` validates locally without I/O; its attempt uses the same
   single-use and potential-dispatch semantics as legacy sending. The JSON contract
   is source-informed by three separately approved unauthenticated public-asset
   GETs, with zero credentials, account data, script execution or sends. Topic is
   UTF-8 Base64; body is HTML-escaped plain text encoded as UTF-8 Base64 because
   the modern reader interprets decoded content as HTML and converts newlines to
   breaks. Recipient payload contains `accountId`, never `userId`. Fixed fields
   are `storageId=null` and `category="normal"`; CC/BCC, groups, OSIN accounts,
   uploads, replies, forwards, signatures and drafts are excluded.
    A successful HTTP response alone remains UNKNOWN. The 0.5 candidate accepts
    only HTTP 201/application-json with exact `data` containing positive bounded
    integer `messageId` and `status="sent"`. This observed envelope establishes
    upstream acceptance, not recipient reading. Explicit allowlisted source-informed
    denial codes on HTTP 400/422 can establish REJECTED; rejection envelopes remain
    unqualified live.
5. Qualification covers source and installed wheel/sdist under representative
   offline load,
   including one-dispatch fault proofs and account/backend isolation. Obtain fresh
   exact payload and live-budget approval for the privately planned sole-recipient
   manual test. Discovery approval is not send approval.

`modern_identity`, `modern_recipient_types` and `modern_recipients` are ordinary
bounded reads with explicit max-age caching. Only the `parentsCouncil` lookup
is supported; other type metadata is returned with `lookup_supported=False`.
Directory parsing accepts only the established one-nested-array class shape,
preserving class labels and unique account IDs; unsupported or ambiguous shapes
raise errors rather than returning partial results. Empty classes are synthetic
offline cases, not claims about observed live empty-directory semantics.

Authentication manually inspects one native launch redirect and one modern
handoff redirect. Both are non-retryable and budgeted; the token, encoded login,
target, source and destination are allowlisted before dispatch. No composer or
JavaScript fetch is needed at runtime. Modern identity must match the native
owner ID and available names. Modern cookies are never copied into the legacy
jar, and legacy cookies are never copied into the modern jar. Invalidation and
shutdown clear/close both account-owned contexts. Limits and token syntax are
conservative library policy, not universal upstream guarantees.

Optional API persistence supplies durable confirmation binding, atomic claims
and conservative crash recovery for modern attempts too. Human approval and
manual reconciliation remain application-owned. Consumer migration, merge and publication
remain separate gates. See [sending.md](sending.md) and [../VERIFICATION.md](../VERIFICATION.md).
