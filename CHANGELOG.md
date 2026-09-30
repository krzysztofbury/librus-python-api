# Changelog

## 0.1.0 - Local-first account and identity service

- Native async account-isolated transport with scoped cookies, fixed destinations,
  explicit TLS/proxy settings, and bounded streamed/decompressed bodies.
- Shared rate/burst/concurrency/queue and whole-operation budgets, deterministic
  cleanup, bounded parser workers, and repeated-cancellation regression coverage.
- Public typed service/client API, credentials/configuration, immutable owner/
  student identity and profile results, specific exception factory, and optional
  redacted structured Loguru diagnostics.
- Coalesced safe reads, explicit account/session freshness, and Tenacity-bounded
  recovery for proven expiry only, without automatic replay of login failures.
- Evidence-labelled OpenAPI wire contracts and independently authored fixtures.
- Installed-artifact loopback/MCP stdio qualification through an opt-in consumer
  adapter. No default consumer backend change or production release.

This version is a locally built delivery, not a PyPI publication or independently
verified live Librus integration. PyPI begins at 1.0.0rc1. Live authentication/
layout evidence, daily credentialed CI, wider platforms, and later endpoint
families remain explicitly pending.
