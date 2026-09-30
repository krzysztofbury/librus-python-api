# librus-python-api

An independent Python library for accessing Librus Synergia. The project is in
local-first development stage: an async account service supports bounded login,
typed identity, and student-information reads against offline fixture servers.
Live compatibility is not yet verified and nothing has been published to PyPI.

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

The public `LibrusService` owns isolated account clients, coalesced safe reads,
account/session-scoped freshness, Tenacity-bounded session recovery, parser workers,
and deterministic cleanup. Inputs/configuration, immutable results, specific
exceptions, and opt-in Loguru diagnostics are typed. No live Librus calls were used.
The local `0.1.0` delivery is qualified on Linux/Python 3.13 and 3.14, including
the installed wheel and a real four-login MCP stdio adapter experiment.
See [API usage and policies](API.md), [verification evidence](VERIFICATION.md),
and the [phase review](REVIEW.md). This does not enable production backend
migration, credentialed CI, PyPI, or live compatibility claims.

## Local installation

```sh
uv build --no-sources
uv pip install dist/librus_python_api-0.1.0-py3-none-any.whl
```

The supported public entry point is `LibrusService`. Supply credentials explicitly,
reuse one service across accounts/tools, and close it with an async context manager.
Only `identity()` and `student_information()` are enabled in this release.

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
