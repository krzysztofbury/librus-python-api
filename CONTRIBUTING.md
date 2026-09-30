# Contributing to librus-python-api

Thanks for your interest in contributing. This project is starting from an
independent implementation rather than modifying or redistributing upstream
`librus-apix` code.

## Before contributing

- Open an issue to discuss a new public API or significant behavior change.
- Write original code and tests. Do not submit copied third-party source,
  tests, documentation, or HTML fixtures unless its provenance and license
  have been reviewed for this MIT-licensed repository.
- Never commit credentials, cookies, access tokens, school identifiers, or
  identifiable student, teacher, or message data. Use synthetic fixtures or
  anonymize real material before it enters the repository.
- Keep ordinary tests and pull-request CI offline. A separate owner-configured
  daily/manual workflow may use real credentials for bounded login/read checks,
  following [the live CI roadmap](TODO.md#p6-live---daily-credentialed-compatibility-check).
  Never use real Librus for load tests, sends, or read-once verification.

## Development workflow

### Install commit checks

Install the hooks once per clone before making commits:

```sh
uv tool install pre-commit==4.6.2
pre-commit install --install-hooks
```

The pinned Gitleaks hook builds with Go; install Go before initializing hook
environments. Hooks block common credential/session files even when force-added,
detect private keys and hardcoded secrets, check basic file hygiene, and reject
commits directly to `main` or `master`. Use a feature branch for changes.
The Gitleaks configuration extends its standard rules with literal-password
checks, including short values and punctuation that token heuristics can miss.

```sh
pre-commit run --all-files
pre-commit run gitleaks-worktree --hook-stage manual
pre-commit run gitleaks-history --hook-stage manual
```

The normal Gitleaks hook scans staged changes, including when invoked with
`--all-files`. The manual worktree command also checks untracked working files;
the history command scans the locally available Git history. Scanner findings
are redacted. Fix findings instead of creating a blanket secrets baseline.

Keep real credentials and raw captures outside the checkout. `.env.example`
may contain placeholders only. Automated detection cannot identify all personal
school data or every password: independently anonymize fixtures and review the
staged diff. Git hooks are local checks; each clone must install them.

### Package development

The package layout and development commands are not established yet. Add
reproducible setup, lint, test, and build instructions here alongside the first
implementation. Until then, keep changes focused, document observable
behavior, and explain safety and compatibility implications in pull requests.

Use a branch for your change and open a pull request against `main`. Include
the checks you ran and any behavior that could not be verified without live
Librus access.

## Security

Do not disclose vulnerabilities or sensitive school data in public issues.
Follow [SECURITY.md](SECURITY.md) for private reporting.
