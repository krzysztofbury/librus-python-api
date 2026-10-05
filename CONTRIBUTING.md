# Contributing to librus-python-api

## Ground rules

- Write original code, tests and fixtures. Do not copy source, tests, docs or
  HTML from other Librus clients or projects. They are references for behaviour
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

Release preparation, Trusted Publishing fields, approval gates and recovery are
documented in [RELEASE.md](RELEASE.md). Release checks use the same offline suite
against a single sealed artifact pair; they never call real Librus.

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
| Message summary semantics, continuation and full multi-account mailboxes | `tests/test_messages.py` |
| Message-list live scope, one-login cap and installed-smoke execution | `tests/test_message_capture.py` |
| Recipient selectors, IDs, scopes and limits | `tests/test_recipients.py` |
| Recipient-only live scope and smoke flow | `tests/test_recipient_capture.py` |

A new read goes into the tables in `tests/reads_support.py` and
`tests/test_account_reads.py`; its family module covers only what is specific to
that family. Fixtures copy the observed structure with invented values.

## Live verification

Synthetic tests prove behaviour against fixtures, not that Librus serves that
structure. Every past live failure here came from a fixture written from
assumptions or from the reference client's behaviour instead of from a real page. The reference client agreeing
with this library on a synthetic page proves nothing, because the reference client mislabels
fields and returns `[]` for pages it does not recognize.

With the owner's authorization for a stated scope and request budget:

1. Capture. One login, an operation allowlist, a request cap, and raw pages
   saved privately:

   ```sh
   uv run python scripts/live_capture.py --secrets FILE --account N --out DIR
   ```

   `DIR` must be new and outside any Git work tree. Files are written 0600. The run
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

For a separately approved message-list scope, `scripts/capture_messages.py`
supports `--mode discovery` (early ordinary list capture) and `--mode smoke`
(public installed page/batch/resume/cache path). Each invocation permits one
credential submission, at most 24 actual HTTP attempts, ten list requests and
pages 0..2 only. It stops on failure, never replays login or view POSTs, and does
not enable recipients, content, sending, attachments or read-once routes. Use
`--account` only for the separately approved account. A second invocation needs
its own authorization, even when the first left requests unused.

`scripts/crosscheck.py CAPTURE_DIR`
checks Chromium's visible message fields, references, flags and empty markers;
a message parser error fails qualification, never counts as agreement. Retain
no raw values or screenshots. Coverage and future feature approval gates are in
[contracts/messages.md](contracts/messages.md).

Recipient discovery has a separate `scripts/capture_recipients.py` allowlist:
one credential submission, 24 requests, six recipient POSTs, and only the
explicitly approved tutor/teacher/office tokens. `--mode smoke` exercises the
public APIs and zero-request warm caches. Authentication/service errors stop
the attempt. A parser failure preserves only the other approved groups' captures
for offline diagnosis and is reported as failed qualification, not success.
Always delete private captures after final offline comparisons.
See [contracts/recipients.md](contracts/recipients.md) for the hierarchy and empty
layout gates; recipient discovery does not authorize sending.

Rules that past mistakes earned:

- Look at the actual page before reasoning about a failure. Counters and
  structure summaries collected while discarding the bytes cost three logins
  and diagnosed nothing.
- Run the whole read surface when its live scope is approved. A full smoke found
  broken profile, timetable and agenda parsing that earlier family-only runs had
  missed. A bounded family-only approval does not authorize unrelated live reads;
  run the full regression suite offline and record what was not rerun live.
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
