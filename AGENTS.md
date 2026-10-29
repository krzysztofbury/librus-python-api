# Agent instructions

This is a public, MIT-licensed repository for an independent Librus Synergia
client. Follow any workspace-level agent rules as well as these project rules.

- Write repository content in English. Do not include private or personal
  context, credentials, or identifiable school data.
- Do not copy code, tests, documentation, or parser fixtures from another Librus client
  or any other project. Review provenance before adding external
  material. Implement behavior from independently established requirements
  and independently authored fixtures.
- Do not call live Librus without explicit authorization. Never use read-once
  schedule requests or message-sending calls for routine verification.
- The weekly credentialed live check (`.github/workflows/live-check.yml`) runs
  from `main` in the `live-check` environment with owner-configured credentials,
  account scope, allowed operations and budgets. Ordinary tests and PR jobs
  remain offline. The workflow does not authorize ad hoc live calls.
- Before writing a fixture from a live observation, take a structure-only dump
  through the live-check guard (allowlisted endpoints, fixed labels, element
  tags, attributes and masked value shapes, never school text). Fixtures written
  from a prose description have diverged from live markup.
- Treat every configured Librus login as an independent security context, even
  when parent and student logins refer to the same student. Do not merge their
  sessions, permissions, data, or caches based on student identity.
- Optimize multi-account retrieval for bounded upstream traffic. All supported
  network operations must pass through shared rate/concurrency/queue budgets;
  per-account limits alone are insufficient. Keep session and cache state isolated.
- Prefer explicit limits, per-account session isolation, typed results, and
  parse errors over silent partial output. Do not retry non-idempotent writes.
- Keep public library contracts independent of MCP-specific response models
  and notification persistence. Coordinate consumer changes with `librus-mcp`.
- Keep all upstream routes in `src/librus_python_api/config.py`. Do not embed
  scraping paths in parsers or client methods. Ship each enabled route with its
  matching OpenAPI operation in `contracts/upstream.openapi.yaml`, including
  side effects, retry policy, evidence, and offline wire-level verification.
- Reuse established concepts and flows from existing clients as design
  references, with original implementation and fixtures. Source-informed
  requirements are not independently observed live behavior.
- Releases follow [RELEASE.md](RELEASE.md). While watching CI or a release run,
  compare each running job's elapsed time with its finished siblings and report
  an outlier (for example three times longer) at once instead of waiting.
- Do not claim a package, API, test command, or release workflow exists until
  it has been implemented and exercised.

## Diagnosing a reported failure

- A failure report names a kind and, from a consumer such as librus-mcp, code
  locations (`module:function:line`, the failure site last) and the library
  version. Read them against the tag of that version.
- Reproduce a parse failure offline with
  `python -m librus_python_api.inspect_page PARSER FILE`; in code use
  `diagnostics.failure_frames(error)` for locations and
  `diagnostics.describe_failure(error)` for the masked structure (tags,
  observed class tokens and ID shapes, known tooltip labels, lengths).
- When the user's saved page parses cleanly but their reads fail, the library
  received a different document (a notice, an error page, another login). Ask
  for the failure's page summary (`describe_failure` on a whole page shows body
  text length, notices and table rows), not for another page.
- A source view saved by macOS TextEdit (`Cocoa HTML Writer`) holds the source
  as text in a table; `inspect_page` rejects it. Ask for Page Source instead.
- A page a user relays is private data: keep it in job scratch outside the
  repository, never commit or quote it, delete it afterwards, and add original
  fixtures that follow its structure. For an owner's own account, capture with
  `scripts/live_capture.py` into scratch and print label structure only.
- Diagnostics are allowlist-based (`describe_failure`, `config.TOOLTIP_LABELS`).
  Extend the lists only with Librus-authored labels and markup, never values,
  and keep the marker tests in `tests/test_failure_diagnostics.py` passing.
