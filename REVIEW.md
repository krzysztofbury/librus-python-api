# 0.1.0 phase review

Review method: the shared pair-programmer/TigerStyle and test-audit checklists,
applied by the implementing agent. This is not an independent reviewer approval.
No live Librus request was made. Fixtures and implementation are original and
source-informed, not copied upstream material.

## Safety

- TigerStyle #12: Full error handling. Repeated caller cancellation could interrupt
  scheduler worker cleanup, and a repeatedly canceled closer could return early.
  Both failures were reproduced in scheduler tests before the fix. Owned work is
  shielded, canceled once, and joined before slots are released. Parser cancellation
  also joins actual thread completion, since Python cannot preempt those workers.
- TigerStyle #6: Positive and negative space. A foreign redirect or unexpected HTML
  is not evidence of session expiry. Only 401 or an exact approved Synergia login
  redirect permits recovery. Required JSON fields/IDs, semantic HTML fields,
  duplicate envelopes/tables, media types, and expected identities fail closed.
- TigerStyle #2: Bounded loops. Request/operation waiters, authentication hops,
  attempts, wire/inflated bytes, cookies, JSON nesting, HTML node/depth counts, and
  parser workers have explicit limits. Retry-After is capped before timer use.
- TigerStyle #13: Explicit defaults. Tenacity retries only proven session expiry,
  with at most two safe-read attempts and the original shared budget. Login POST,
  connection ambiguity, denials, maintenance, and throttles are not replayed.
  Backpressure stays at the single shared scheduler, not independent retry sleeps.
  Repeated expiry after the single recovery attempt enters an operation cooldown;
  its next-call regression failed before the fix, preventing repeated login pressure.
- TigerStyle #4: Paired assertions. Login success requires a scope-applicable
  session cookie plus parsed identity; configured owner/student expectations and
  identity consistency are checked independently of alias/cache identity.
- Diagnostics use a closed typed event and opt-in Loguru sink. Account aliases,
  credentials, URLs, response excerpts, and exception objects are excluded.
  Shared-budget counters are labelled as budget totals, not per-operation deltas.

## Performance

- TigerStyle #14: Batching. Identical safe reads coalesce within a login and budget
  scope. Caller-requested freshness reuses at most two account/session cache entries.
  Distinct login contexts never merge, even for the same represented student.
- The installed-library MCP stdio workload verifies the existing 24-tool catalogue,
  three concurrent profile callers for each of four logins, one scoped denial,
  28 cold requests, three warm requests, four reused connections, and the combined
  25 requests/second, burst-two envelope. These fixture settings are not approved
  live traffic policy. No speedup versus the old backend is claimed.
- Maximum-body parser probe: eight 262144-byte JSON/HTML jobs, two bounded workers,
  loop heartbeat sampling, and traced peak memory. Coarse local regression gates
  are ten seconds total, 250 ms maximum heartbeat delay, and 32 MiB traced peak.
  This is not a cross-platform latency or process-RSS guarantee.

## DX and remaining qualification

- TigerStyle #11: Warning clean. Ruff, formatting, strict mypy, OpenAPI/catalogue
  parity, offline suites, and installed-artifact checks are release gates.
- Public inputs, transport payloads/responses, wire validation, immutable domain
  records, typed exception factory, and diagnostic events have explicit types.
  The consumer owns field translation and its MCP output schema.
- The consumer adapter is opt-in and does not change its dependency pin, default
  CLI, tool schemas, notification state, or other operation backends. No fallback
  after native failure, private session patching, or cookie exchange is introduced.
- Live callback/account variants and profile label/layout compatibility remain
  unverified. Interactive CAPTCHA/2FA is unsupported. A lucky number has no
  fabricated civil date; unavailable data fails the consumer mapping explicitly.
- macOS/Windows, daily credentialed CI, PyPI, production backend migration, and
  broader endpoint coverage remain separate qualification work.
