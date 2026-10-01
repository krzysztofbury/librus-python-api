# librus-python-api

An independent Python library for accessing Librus Synergia. The project is in
local-first development stage: an async account service supports bounded login,
typed identity, and student-information reads against offline fixture servers.
The local-first `0.2.0` delivery adds final summaries, inline numeric/descriptive grades,
raw school averages, explicit upstream views, dated period marks, descriptive
publications, and inclusive date windows. 0.2.0 is grades-only; attendance and the
remaining school reads belong to 0.3.0. The current `0.3.0.dev0` increment adds
offline-tested attendance collections, upstream views, and date windows; details
and frequency remain pending. Attendance is not live-qualified. Qualification and delivery status
are recorded in VERIFICATION.md, not inferred from this scope adjustment.
Bounded login/identity/summary/current-grade live qualification has passed for a narrow
observed variant. General compatibility is unverified; nothing is published to PyPI.

The first intended consumer is
[librus-mcp](https://github.com/krzysztofbury/librus-mcp). This repository will
own the HTTP client, authentication, parsing, bounded collection reads, and
typed domain results. The MCP server will continue to own its tools, account
configuration, user-facing response contracts, and durable notification state.

## Primary use case

Let MCP fetch school data through a small async, typed API using several
independent Librus logins. Optimize for fewer upstream requests, predictable
latency, and enforced security boundaries rather than maximum parallelism.

One service should manage isolated account clients under a shared rate,
concurrency, queue, and request budget. Reuse sessions and reference data,
coalesce identical safe reads within an account, and expose typed results and
failures. A student login and a parent login remain distinct even when they
refer to the same student; their permissions and data may differ. MCP chooses
which accounts to query and combines the results. The library owns bounded
retrieval, not summary generation or automatic cross-account merging.

The `0.x` deliveries are local-first. Verify built artifacts and the integration
offline, including local `librus-mcp` adapter tests. PyPI publication and publishing
automation are deferred until `1.0.0rc1`. A dedicated daily
credentialed compatibility check remains planned, not configured or running.
See [the implementation roadmap](TODO.md).

## Current implementation

- Python 3.13 and 3.14 package skeleton with an MIT license and `py.typed`.
- Central typed route catalogue in `src/librus_python_api/config.py`, frozen
  Pydantic limit configuration, and closed error categories. The catalogue
  records fixed, evidence-labelled login, identity, and HTML profile routes.
- Shared async scheduler with bounded global/per-account admission, token-bucket
  rate/burst limits, round-robin fairness, shared request/deadline budgets, and
  joined cancellation/closure. This is service-local, not a distributed quota.
- [OpenAPI YAML and endpoint evidence requirements](contracts/README.md), with
  an offline check preventing route/contract drift. Import the YAML into Bruno
  for explicit manual validation; its default destination is loopback.
- Real transport/service tests with isolated synthetic logins, same-name scoped
  cookies, body/deadline bounds, and joined cancellation. Optional parser-resource
  and consumer stdio tests live alongside the portable offline suite.
- GitHub-hosted CI for Python 3.13/3.14 on Linux: quality/security checks and the
  portable suite against source, installed wheel, and installed sdist. Build
  artifacts are retained for inspection, not published to PyPI.
- [Grade reads](contracts/grades.md) with explicit column availability,
  preserved school values, bounded semantic HTML parsing, and shared account
  lifecycle/budgets. Grade-view POSTs have explicit filter side effects and no
  automatic replay; windows reuse its collection cache. Business compatibility
  against apix is tracked separately from numeric parity and performance.
  The consumer migration remains a separate task; its adapter experiment is closed.
- [Attendance collections](contracts/attendance.md) with explicit semesters,
  unknown metadata, inert detail identifiers, isolated views, and cached windows.
  This is a development increment, not completed 0.3.0 school-read coverage.

The public `LibrusService` owns isolated account clients, coalesced safe reads,
account/session-scoped freshness, Tenacity-bounded session recovery, parser workers,
and deterministic cleanup. Inputs/configuration, immutable results, specific
exceptions, and opt-in Loguru diagnostics are typed. Ordinary tests remain offline;
bounded owner-authorized live qualification is documented separately.
The local `0.1.0` delivery is qualified on Linux/Python 3.13 and 3.14, including
the installed wheel and a real four-login MCP stdio adapter experiment.
See [API usage and policies](API.md), [verification evidence](VERIFICATION.md),
and the [phase review](REVIEW.md). This does not enable production backend
migration, credentialed CI, PyPI, or general live compatibility claims.
See [the comparison](BENCHMARKS.md) for measured performance benefits and non-wins.

## Local installation

```sh
uv build --no-sources
uv pip install dist/*.whl
```

The supported public entry point is `LibrusService`. Supply credentials explicitly,
reuse one service across accounts/tools, and close it with an async context manager.
Enabled development reads are `identity()`, `student_information()`,
`final_grades()`, `grades()`, `grades_window()`, `attendance()`, and
`attendance_window()`. Version 0.3.0.dev0 is a local-only development build,
not a published PyPI release.

## Development principles

- Implement the integration independently. Do not copy code, tests, or parser
  fixtures from `librus-apix` or other third-party implementations.
- Treat Librus responses as untrusted. Bound requests, response bodies,
  pagination, and concurrency; reject malformed data explicitly.
- Isolate each account's cookies and session. Do not log credentials, tokens,
  private messages, or student information.
- Preserve read-once schedule events and never retry a message send without an
  explicit delivery-safety policy.
- Use synthetic or properly anonymized fixtures for ordinary automated tests.
  Credentialed live checks belong only in the explicitly configured daily/manual
  workflow, never in pull-request tests or load tests against Librus.

See [CONTRIBUTING.md](CONTRIBUTING.md) for runnable local setup, validation, and
build commands, and [TODO.md](TODO.md) for the remaining implementation work.

The roadmap covers typed contracts, async transport, JSON/HTML coverage, PyPI
releases, and a backward-compatible migration of `librus-mcp`. It also separates
reusable library work from MCP-specific changes in the consumer's 2.0 roadmap.

## License

MIT. See [LICENSE](LICENSE).
