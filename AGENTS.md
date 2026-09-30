# Agent instructions

This is a public, MIT-licensed repository for an independent Librus Synergia
client. Follow any workspace-level agent rules as well as these project rules.

- Write repository content in English. Do not include private or personal
  context, credentials, or identifiable school data.
- Do not copy code, tests, documentation, or parser fixtures from upstream
  `librus-apix` or another project. Review provenance before adding external
  material. Implement behavior from independently established requirements
  and independently authored fixtures.
- Do not call live Librus without explicit authorization. Never use read-once
  schedule requests or message-sending calls for routine verification.
- Daily credentialed CI is an intended feature. Live access is allowed only
  after the owner configures the dedicated default-branch workflow, credentials,
  account scope, allowed operations, and budgets. Ordinary tests and PR jobs
  remain offline. Planning this workflow does not authorize ad hoc live calls.
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
- The 0.x deliveries are local-first. PyPI publication and publishing automation
  are deferred until 1.0.0rc1. Verify built artifacts locally, including consumer
  integration, without implying they have been published.
- Do not claim a package, API, test command, or release workflow exists until
  it has been implemented and exercised.
