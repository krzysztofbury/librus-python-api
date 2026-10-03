# 0.4.11 offline review follow-ups (S10)

## Pre-change pair-programmer review

The baseline is the remotely confirmed merge of PR #13, including 0.4.10, into
main. Baseline portable suite: 1,253 passed, one opt-in performance test deselected.
This is a skill-guided self-review, not an independent agent/model review.

Safety findings and boundaries:

- S10(c,d), `_storage.py`, `persistence.py`, `notification_persistence.py`:
  unbounded retention lifetime eventually consumes bounded capacity, while plain
  context fingerprints permit correlation. TigerStyle #2 bounded work and #4
  paired validation: add explicit atomic selection-based retention, preserve
  recovery/uncertainty, version and salt actual persisted bytes. No production
  migration or implicit reset is authorized.
- S10(a,b), `transport.py:authenticate_modern`, `service.py:_authenticated` and
  `_execute_modern_send`: modern login expiry must not become denial or invalidate
  a valid legacy session. TigerStyle #6 unsupported states and #12 full error
  handling: distinguish origin/session ownership, revalidate with the existing
  side-effect-free modern identity GET before sending, and never retry a send.
- S10(e-g), cursor batches, attachment destination validation and mailbox parser:
  stale continuation differs from malformed input; unsupported redirect/pager
  shapes must fail without permission cooldown or silent truncation. TigerStyle
  #4 paired validation and #6 explicit unsupported states.
- S10(h,i), attachment demand and send return lifetimes: a paused consumer must
  not hold shared admission indefinitely, and a complete response must not be
  discarded merely because its return crosses a deadline. TigerStyle #2 bounded
  waits, #12 joined cleanup and #13 explicit defaults.

## Storage slice post-change review

- Explicit caller pruning chosen instead of school-year/age expiry. There is no
  automatic weakening of seen/dedup history. Accepted-send pruning requires a
  separate duplicate-risk opt-in; uncertain/claimed sends remain unprunable.
- Pending raw/reservation/delivery prohibits seen pruning under the held process
  context lock. All selections validate before SQL deletion/update; other category
  state, initialization and last acknowledgement survive.
- Salt creation is atomic under SQLite BEGIN IMMEDIATE; reopening/process
  competition retains the same salt. Persisted contexts/lock paths/batches/raw
  links use store-local identifiers; public replay remains context-bound.
- Archive v2 validates the source namespace before target rebinding. Raw bytes,
  receipts and cursor progress survive a new target salt. Old layouts fail without
  mutation; salt/schema tampering is not treated as an empty store.
- Real SQLite/public-native tests cover retained duplicate protection, capacity
  reuse, atomic foreign/unknown-ID refusal, expired unused confirmations, independent
  durable salts, actual persisted-byte inspection, old-schema refusal and existing
  competing-process/crash/replay paths. Source suite: 1,269 passed, one deselected.
  Ruff and strict typing pass. Installed qualification is a final release gate.

## Modern-session slice post-change review

- Exact modern-launch redirects to native login routes report SESSION_EXPIRED;
  unsupported/foreign account handoffs remain denied and are never followed.
- Every send verifies modern identity freshly under the same account operation
  lock and shared request budget. A cold binding already performs this GET; a warm
  binding costs exactly one additional GET. Preflight expiry/denial stops before
  POST and preserves NOT_DISPATCHED. No write is retried.
- Messages-origin expiry provenance is library-private and contains no URL/body.
  It clears modern binding/cookies/cache only, not valid legacy identity/cookies.
  Modern HTTP/validation failures also clear modern state. A proven native launch
  expiry still invalidates native state. Existing modern read retry policies remain
  unchanged: recovery occurs on a later explicit call, not implicit replay.
- Original public two-origin regressions failed before the fixes for login redirect
  classification, omitted warm preflight and legacy invalidation after a modern
  401. They pass after the changes. Full source suite: 1,276 passed, one deselected;
  Ruff/typing pass. Warm concurrent sends now budget their two distinct preflights.
- A preflight cannot eliminate expiry between GET and POST. Post-dispatch errors
  still retain UNKNOWN, clear the modern binding and never replay the message.

The edge-case post-change review will be recorded in its own scoped commit. All
verification stays offline with independently authored fixtures.
