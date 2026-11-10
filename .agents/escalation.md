# Escalation policy

Read by the `approver` role. A pull request that matches any item below goes
to the owner instead of merging on its own. The `retro` role proposes changes
to this file as pull requests; add what should have reached the owner, relax
what the owner keeps waving through, and give the reason in the PR.

## Always escalate

- Agent rules: `.agents/**`, `AGENTS.md`, `CLAUDE.md` and `.github/**`. Agent
  rules and the policy that gates merges do not change without the owner.
- Anything that writes to Librus or changes what the school sees: sending
  (`src/librus_python_api/sending.py`, `src/librus_python_api/recipients.py`),
  modern mailbox writes (`src/librus_python_api/modern_mailbox.py`,
  `src/librus_python_api/modern_messages.py`), opening a received message
  (marks it read, `src/librus_python_api/message_content.py`), read-once
  schedule requests, and any retry of a non-idempotent call.
- Upstream routes and their declared side effects:
  `src/librus_python_api/config.py` and `contracts/upstream.openapi.yaml`.
  A new or changed route is a change to what the library may do to a
  school's account.
- Sessions, logins and transport: `src/librus_python_api/transport.py`,
  `src/librus_python_api/lifecycle.py`, per-login isolation
  (`contracts/account-context.md`), and the shared rate, concurrency and
  queue budgets (`src/librus_python_api/budget.py`,
  `src/librus_python_api/scheduler.py`).
- School and children's data at rest or in output: persistence and
  notification state (`src/librus_python_api/_storage.py`,
  `src/librus_python_api/persistence.py`,
  `src/librus_python_api/notification_persistence.py`,
  `src/librus_python_api/_notification_codec.py`,
  `src/librus_python_api/checkpoint.py`,
  `src/librus_python_api/_windows_filesystem.py`), attachment files
  (`src/librus_python_api/files.py`, `src/librus_python_api/attachments.py`),
  and diagnostics allowlists (`src/librus_python_api/diagnostics.py`,
  `config.TOOLTIP_LABELS`, `tests/test_failure_diagnostics.py`). Fixtures
  stay synthetic and original.
- The public library API: exported names and signatures in
  `src/librus_python_api/__init__.py`, `src/librus_python_api/models.py`,
  `src/librus_python_api/exceptions.py`, `src/librus_python_api/service.py`,
  `API.md` and `contracts/**`. `librus-mcp` pins this library; a breaking
  or behavior-visible change is coordinated with it.
- Live access and its tooling: `scripts/live_check/**`,
  `scripts/live_capture.py`, `scripts/capture_*.py`, the `live-check`
  environment, its credentials, account scope and budgets.
- Release and publishing: `RELEASE.md`, `scripts/release_gate.py`,
  `scripts/qualify_release.py`, `scripts/verify_*.py`, `release-evidence/**`,
  version bumps, the versioned CHANGELOG entry, tags and GitHub Releases
  (they publish to PyPI).
- CI and secret scanning: `.github/**`, `.pre-commit-config.yaml`,
  `.gitleaks.toml`.
- Dependencies: `pyproject.toml`, `uv.lock`, `.github/dependabot.yml`.
- Provenance and policy: material taken from another Librus client or
  project, `LICENSE`, `SECURITY.md`, `DESIGN.md`.
- Anything that needs a live Librus run; the PR merges only after the owner
  authorizes that run.

## May merge without the owner

When review passed, CI is green and nothing above applies:

- Parser fixes for read-only views (grades, attendance, timetable, homework,
  announcements and similar modules) with original synthetic fixtures and
  no change to exported models.
- Internal refactors with tests, `inspect_page` improvements, benchmarks
  (`tests/performance/**`, `BENCHMARKS.md`).
- Tests and docs other than the ones listed above.

The board config for this repository lives in `krzysztofbury/librus-mcp`
(`.agents/cos.json`).
