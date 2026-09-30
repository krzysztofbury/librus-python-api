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

The foundation uses `src/librus_python_api/`, Hatchling builds, and a committed
`uv.lock`. Python 3.13 and 3.14 are the current local verification targets.
Pydantic provides strict, frozen runtime validation. `aiohttp` implements the
native transport. `lxml` parses bounded semantic HTML in joined workers. Tenacity
owns the explicit safe-read recovery policy; Loguru diagnostics are opt-in.

```sh
uv sync --locked --python 3.14
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python -m pytest
uv build --no-sources
```

The default suite includes OpenAPI/catalogue validation and real transport,
authentication, parser, and scheduler tests against original synthetic loopback
fixtures. There is no separate transport experiment or contract-check CLI to run.
All requests remain offline. Hardware-sensitive measurements and cross-repository
integration are opt-in, not silently skipped release gates:

```sh
uv run --locked python -m pytest tests/performance -m performance
```

The performance test preserves the maximum-body memory/heartbeat checks outside
the portable default suite. It records measurements as pytest properties; add
`-o junit_family=xunit1 --junitxml=/tmp/opencode/parser-resources.xml` when a
machine-readable measurement report is needed.

To repeat the suite on Python 3.13, use a separate environment so the primary
environment is not replaced:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/opencode/librus-python-api-py313 uv sync --locked --python 3.13
UV_PROJECT_ENVIRONMENT=/tmp/opencode/librus-python-api-py313 uv run --locked python -m pytest
```

Verify the wheel outside the checkout before handing off packaging changes:

```sh
uv venv /tmp/opencode/librus-python-api-wheel --python 3.14
uv pip install --python /tmp/opencode/librus-python-api-wheel/bin/python dist/librus_python_api-0.1.0-py3-none-any.whl
cd /tmp/opencode
/tmp/opencode/librus-python-api-wheel/bin/python -c 'from importlib.metadata import version; from importlib.resources import files; from librus_python_api.config import ENDPOINTS; assert version("librus-python-api") == "0.1.0"; assert files("librus_python_api").joinpath("py.typed").is_file(); assert len(ENDPOINTS) == 9'
```

Use a fresh environment path for subsequent runs. This import/configuration
smoke check alone is not an installed-client E2E read. The full offline suite and
consumer integration test below exercise that gate. No PyPI upload or publishing CI
is required for the 0.x deliveries. PyPI publication and publishing automation
start at `1.0.0rc1`; local `librus-mcp` integration can use the exact built wheel
before that candidate. Production consumer releases must still use PyPI artifacts.

To run the current offline suite against the installed wheel rather than the
editable source package, export the locked dependencies without the project,
install them in that separate environment, and run from outside the checkout:

```sh
uv export --quiet --locked --no-emit-project --format requirements-txt --output-file /tmp/opencode/librus-python-api-wheel-requirements.txt
uv pip install --python /tmp/opencode/librus-python-api-wheel/bin/python --require-hashes -r /tmp/opencode/librus-python-api-wheel-requirements.txt
cd /tmp/opencode
PYTHONPATH=/path/to/librus-python-api /tmp/opencode/librus-python-api-wheel/bin/python -m pytest /path/to/librus-python-api/tests
```

Replace `/path/to/librus-python-api` with the checkout root, never its `src/`
directory. This makes test fixtures available without replacing
the installed library. Reinstall the wheel after rebuilding the same local version;
check `librus_python_api.__file__` points into the separate environment.

For the real MCP stdio identity experiment, install the consumer adapter branch
(`feat/native-identity-adapter`, draft PR #38) into that same environment. This is
a local experiment, not a production dependency change. Then run outside the
library checkout:

```sh
uv pip install --python /tmp/opencode/librus-python-api-wheel/bin/python /path/to/librus-mcp
cd /tmp/opencode
PYTHONPATH=/path/to/librus-python-api /tmp/opencode/librus-python-api-wheel/bin/python -m pytest /path/to/librus-python-api/tests/integration -m integration --mcp-checkout=/path/to/librus-mcp
```

The test uses original synthetic HTTP fixtures, four independent logins, real
consumer field mapping, and MCP stdio. Its subprocess configuration explicitly
replaces operator credentials with synthetic accounts and permits localhost
destinations only. Expected scoped denials are redacted non-successes. No live
school requests or production notification/filesystem state are used. Selecting
integration without a valid adapter checkout is an actionable test failure.

Also install `dist/librus_python_api-0.1.0.tar.gz` in a separate environment and
run the same public-boundary suite to qualify the sdist build path. Record hashes
with `sha256sum` and review installed metadata for MIT, `py.typed`, Python support,
and runtime dependencies. See VERIFICATION.md for the actual local results.

Keep network paths in `config.py` and add the matching wire contract in
`contracts/upstream.openapi.yaml` for every endpoint. See the
[contract authoring and Bruno guide](contracts/README.md). Reuse existing
clients' concepts and documented flows, not their implementation or fixtures.

Use a branch for your change and open a pull request against `main`. Include
the checks you ran and any behavior that could not be verified without live
Librus access.

## Security

Do not disclose vulnerabilities or sensitive school data in public issues.
Follow [SECURITY.md](SECURITY.md) for private reporting.
