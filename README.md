# librus-python-api

An independent Python library for accessing Librus Synergia. The project is in
the foundation stage: a local development package can be built and installed,
but no functional Librus client or supported network API has been released.

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

## Current foundation

- Python 3.13 and 3.14 package skeleton with an MIT license and `py.typed`.
- Central typed route catalogue in `src/librus_python_api/config.py` and closed
  error categories. The catalogue currently has no enabled Librus operations.
- [OpenAPI YAML and endpoint evidence requirements](contracts/README.md), with
  an offline check preventing route/contract drift. Import the YAML into Bruno
  when operations are added; there are no working requests in it yet.
- Loopback-only `aiohttp` evaluation with four independent synthetic sessions,
  scoped duplicate cookies, body limits, deadline, and cancellation checks.
  This is transport-selection evidence, not a supported client or load test.

Authentication, identity, shared traffic scheduling, and the MCP adapter remain
pending. No live Librus calls were used to validate this foundation.

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
