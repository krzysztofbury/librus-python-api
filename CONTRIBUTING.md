# Contributing to librus-python-api

## Ground rules

- Write original code, tests and fixtures. Do not copy source, tests, docs or
  HTML from `librus-apix` or other projects. They are references for behaviour
  only.
- Never commit credentials, cookies, tokens, raw captured pages, or identifiable
  student, teacher or school data. This is a public repository: content is in
  English and fixtures are synthetic.
- Ordinary tests and pull-request CI never contact Librus. Live access needs the
  owner's explicit authorization (see [Live verification](#live-verification)).
- Never send messages, consume read-once events or mark anything as read during
  verification.

## Setup

```sh
uv sync --locked
uv tool install pre-commit==4.6.2
pre-commit install --install-hooks   # needs Go for the Gitleaks hook
```

Hooks block credential and session files, private keys and hardcoded secrets,
check file hygiene, and refuse commits to `main`. Manual scans:

```sh
pre-commit run gitleaks-worktree --hook-stage manual
pre-commit run gitleaks-history --hook-stage manual
```

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build --no-sources
```

CI (`.github/workflows/ci.yml`) runs these on Python 3.13 and 3.14, audits the
locked dependencies, scans history for secrets, then rebuilds and reruns the
suite against the installed wheel and the installed sdist outside the checkout.
To reproduce the installed-artifact run locally:

```sh
uv export --quiet --locked --no-emit-project --format requirements-txt -o "$TMP/req.txt"
uv venv "$TMP/venv" && uv pip install --python "$TMP/venv/bin/python" --require-hashes -r "$TMP/req.txt"
uv pip install --python "$TMP/venv/bin/python" --no-deps dist/*.whl
cd "$TMP" && PYTHONPATH=/path/to/checkout "$TMP/venv/bin/python" -m pytest /path/to/checkout/tests
```

`uv run pytest -m performance` runs the opt-in parser memory and heartbeat
measurement.

## Where tests live

| Contract | Owner |
| --- | --- |
| Admission, coalescing, caching, session recovery, budgets, cancellation, wire forms, typed page notices, for every read | `tests/test_account_reads.py` |
| Scheduler rate, queues, fairness, pauses | `tests/test_scheduler.py` |
| Transport: cookies, body limits, redirects, statuses, form rules | `tests/test_transport.py` |
| Login, identity, profile, diagnostics, close | `tests/test_identity.py` |
| Parser semantics for one family | `tests/test_<family>.py` |
| Route catalogue matches the OpenAPI contract | `tests/test_contracts.py` |
| Live capture safety | `tests/test_live_capture.py` |

A new read goes into the tables in `tests/reads_support.py` and
`tests/test_account_reads.py`; its family module covers only what is specific to
that family. Fixtures copy the observed structure with invented values.

## Live verification

Synthetic tests prove behaviour against fixtures, not that Librus serves that
structure. Every past live failure here came from a fixture written from
assumptions or from apix's behaviour instead of from a real page. Apix agreeing
with this library on a synthetic page proves nothing, because apix mislabels
fields and returns `[]` for pages it does not recognize.

With the owner's authorization for a stated scope and request budget:

1. Capture. One login, an operation allowlist, a request cap, and raw pages
   saved privately:

   ```sh
   uv run python scripts/live_capture.py --secrets FILE --account N --out DIR
   ```

   `DIR` must be new and outside the repository. Files are written 0600. The run
   continues past failures, so one login shows every family's state.
2. Cross-check offline. Chromium renders the same bytes independently, with
   scripts and network disabled:

   ```sh
   uv run --with playwright python scripts/crosscheck.py DIR
   ```

3. For each failure, read the captured page, write an original fixture with the
   same structure and invented values, add a failing test, then fix.
4. Rerun the capture on the fixed build and record the results in
   [VERIFICATION.md](VERIFICATION.md).
5. Delete the capture directory.

Rules that past mistakes earned:

- Look at the actual page before reasoning about a failure. Counters and
  structure summaries collected while discarding the bytes cost three logins
  and diagnosed nothing.
- Run the whole read surface, not only the family being worked on. A full smoke
  found broken profile, timetable and agenda parsing that earlier family-only
  runs had missed.
- An empty result is not populated coverage. A page that parses is not a
  correct page; compare counts and rendered text.
- Typed outcomes beat guesses. A disabled view, a rejected date range and an
  unknown notice are different from an empty list.
- Green CI proves the offline checks. Report a live gate as pending until it
  has actually run.

## Adding an endpoint

1. Add the route to `ENDPOINTS` in `src/librus_python_api/config.py`, with its
   side effect, retry safety and evidence level, and any form builder.
2. Add the matching operation to `contracts/upstream.openapi.yaml`.
3. Add a public method on `AccountClient` that validates input and passes one
   `fetch` to `_read`.
4. Add the operation to the shared read tables, then the family parser tests.
5. Capture and cross-check it live before calling it verified.

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
