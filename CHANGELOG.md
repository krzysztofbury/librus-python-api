# Changelog

## 0.2.0.dev0 - Academic coverage in development

- First increment: typed final-grade summaries through one bounded HTML GET,
  with school-provided strings and explicit optional-column availability.
- New original semantic-header, merged-behaviour, unassigned, malformed, bound,
  wire/isolation/cache/recovery fixtures and an opt-in real MCP stdio adapter.
- Existing lifecycle, budgets, diagnostics, and public identity/profile contracts
  are preserved. This is not a completed 0.2.0 release or PyPI publication.
- Individual numeric/descriptive grades, GPA, windows, and other academic slices
  remain pending; summary layout/live-account compatibility is unverified.

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
