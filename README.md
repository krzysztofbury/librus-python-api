# librus-python-api

An independent Python library for accessing Librus Synergia. The project is in
the planning stage: no installable package or supported API has been released.

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

Verification has two tracks: offline end-to-end tests for every change and a
dedicated daily CI check that signs in with real credentials and performs a
small set of allowed reads. See [the implementation roadmap](TODO.md).
These are planned capabilities, not released APIs.

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

The initial API, supported Python versions, packaging, and test commands will
be documented when implementation begins. See [TODO.md](TODO.md) for planned
work and [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance.

The roadmap covers typed contracts, async transport, JSON/HTML coverage, PyPI
releases, and a backward-compatible migration of `librus-mcp`. It also separates
reusable library work from MCP-specific changes in the consumer's 2.0 roadmap.

## License

MIT. See [LICENSE](LICENSE).
