# Modern messaging: observed discovery, implementation pending

The modern composer at `https://wiadomosci.librus.pl/nowy/` is a separate
messaging backend from the legacy Synergia HTML routes implemented in 0.4.6.
Successful modern recipient discovery does not qualify legacy lookup or sending.
No modern backend, modern send API or automatic fallback is shipped yet.

## Independently observed read-only discovery

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
incorporated in the repository. Original offline fixtures are still required
before implementing the modern backend.

## Required next increment, not authorized implementation

Prioritize explicit modern-backend support over guessing legacy class selectors.
No retirement date or universal migration policy for legacy messaging has been
established. Account settings must not be silently toggled to select a backend.

Before modern sending:

1. Approve the next feature/version scope separately. Preserve existing 0.4.6
   single-use attempts, cancellation/uncertainty semantics and shared budgets.
2. Add the modern origin, authentication handoff and all enabled routes centrally
   in `config.py`, with matching OpenAPI operations and original offline wire
   proofs. The investigation adapter is not a shipped library interface.
3. Bind references to both the independent login and messaging backend. Modern
   recipient `accountId`, modern `userId` and legacy recipient IDs must not be
   conflated or accepted across backends without separately established proof.
4. Independently establish modern plain-text payload encoding, acknowledgement,
   definitive rejection and potentially dispatched boundaries. Captured app code
   indicates JSON sending, unlike the legacy repeated form; no send request or
   acknowledgement has been observed live. No automatic cross-backend fallback
   or replay is safe.
5. Qualify source and installed wheel/sdist under representative offline load,
   including one-dispatch fault proofs and account/backend isolation. Obtain fresh
   exact payload and live-budget approval for the privately planned sole-recipient
   manual test. Discovery approval is not send approval.

Consumer preview/confirmation, durable attempt records, crash recovery and
reconciliation remain application-owned. Consumer migration, merge and publication
remain separate gates. See [sending.md](sending.md) and [../VERIFICATION.md](../VERIFICATION.md).
