# Public API: 0.2.0 development

The 0.1.0 delivery implements login, gateway identity, and HTML student
information. The `0.2.0.dev0` increment adds final-grade summaries, not a completed
academic release. Bounded login/identity/final-summary live qualification has
passed for a narrow observed variant; general account compatibility is unverified.
Reading school data requires separate authorization.
Authentication can change the upstream last-login timestamp.

## Ownership and typed results

Module ownership is explicit: shared transport/wire/domain/diagnostic records live
in `models.py`; settings and route policy in `config.py`; exception definitions and
the factory in `exceptions.py`. Transport/parser/scheduler/service modules own
behavior, with private worker and queue state beside their implementation.

```python
from librus_python_api import (
    AccountCredentials, LibrusService, StudentInformation,
)


async def profile(login: str, password: str) -> StudentInformation:
    credentials = AccountCredentials(login=login, password=password)
    async with LibrusService({"account": credentials}) as service:
        return await service.account("account").student_information()
```

Construction/import performs no network I/O, credential discovery, environment
proxy lookup, or logging configuration. The service creates transports lazily,
owns every account/session/parser worker, and is event-loop local. It must not
be reused across loops. `aclose()` is idempotent and joins actual work, including
when callers cancel repeatedly. Cleanup can outlast an operation deadline while
bounded parser threads finish, because Python threads cannot be preempted.

Use one long-lived service for all accounts/tools in a process. Every configured
login has a distinct security context, even when parent/student logins represent
the same student. Independent processes need external quota coordination.
Optional `expected_owner_id` and `expected_student_id` on credentials verify the
configured identity. A changed identity inside an established session is denied.
Multi-child switching and persistent cookie import/export are unsupported.

`AccountClient.identity()` returns frozen `Identity(owner, student, observation)`.
`owner` is the login owner; `student` is the represented student, not the cache key.
`student_information()` returns frozen `StudentInformation` with identity, name,
class, register number, tutor, school, lucky number, and profile observation.
IDs are bounded strings. Optional person names can be `None`; required profile
fields cannot silently disappear. Observations include the login alias, aware UTC
time, source operation, and session generation. Reprs omit personal fields.

Gateway User records may omit Id and supply the explicit Account.UserId reference.
The owner remains Account.Id; missing or conflicting represented-user references
fail instead of being inferred from names or owner identity.

`LuckyNumber` explicitly distinguishes available from unavailable. Its `day` is
`None` where the HTML marker supplies no evidenced civil date. Neither a missing
number nor a missing date is replaced with zero or today's date. These records
are library domain types, not MCP output schemas. Consumers serialize them
explicitly rather than accidentally exposing all identity/provenance fields.

## Budgets, freshness, and coalescing

All account reads accept `budget: RequestBudget | None` and
`max_age_seconds: float = 0.0`. A shared budget spans all selected account calls:

```python
import asyncio
from librus_python_api import LibrusService, RequestBudget, StudentInformation


async def profiles(service: LibrusService, aliases: tuple[str, ...]) -> list[StudentInformation]:
    budget = RequestBudget(max_requests=32, timeout_seconds=120.0)
    return await asyncio.gather(*(
        service.account(alias).student_information(budget=budget)
        for alias in aliases
    ))
```

Defaults: 32 requests, 120 seconds from budget construction including queue wait,
and 4 MiB cumulative response bytes. Every actual dispatch consumes one request,
including login steps, redirects, verification, and recovery. Failed dispatches
are not refunded. Compressed responses conservatively charge both wire and
inflated bytes; identity-encoded bodies are charged once. Limits stop new work
with `LimitError`; no partial identity record is fabricated.

Fresh reads are the default. An explicit age from zero through 3600 seconds allows
reuse of at most three cached results per account. Session invalidation clears all.
TTL is checked against monotonic elapsed time at every read; older values are
replaced on the next fetch. Cache hits still respect deadlines and cooldowns.
Identical in-flight default-budget reads share work. Explicit-budget reads share
only when the budget object is identical. One canceled waiter does not cancel
other waiters; cancellation of the last waiter cancels and joins owned work.
Global/per-account operation admission also bounds coalesced waiters and tasks
waiting for an account's session lock. Session-changing operations are serialized.

## Configuration and injection

- `SchedulerLimits`: five requests/second, shared burst ten, two active requests
  globally, one per account, 32 queued globally/eight per account, 16 accounts, 32 operation
  callers globally/eight per account. These are not Librus-approved quotas.
- `TransportLimits`: 30-second total request and 10-second connect timeout,
  4 MiB response bodies, ten redirect hops per chain, 128 cookies, 256 KiB parser
  input, and 60-second cooldown. JSON nesting and HTML depth are capped at 32;
  HTML nodes at 8192. Two parser workers are shared by the service.
- `OperationLimits`: default policy for calls without a supplied budget.
- `ConnectionSettings`: explicit verified TLS context and optional `SecretStr`
  proxy URL. Automatic environment proxy discovery is disabled. Approved live
  origins cannot be expanded; loopback overrides support fixture servers. Use
  `localhost` for fixture cookie jars. Caller-owned SSL contexts are trusted
  configuration and must not be weakened/mutated after validation.
- `transport_factory`: an explicit typed `TransportFactory` creating a distinct
  `AccountTransport` per login. Service ownership includes closure. Shared object
  instances are rejected. Custom implementations must honor scheduler, budgets,
  destination validation, isolation, and joined cancellation; Python code that
  intentionally bypasses the boundary is outside the guarantee.

Fixed routes, origins, authentication policies, and semantic profile labels live
in `config.py`. No public arbitrary authenticated URL method exists. The
[OpenAPI YAML](contracts/upstream.openapi.yaml) documents twelve enabled wire
operations: the foundation, two exact login continuations, and the summary GET.
These include raw
HTML, forms, origins, side effects, and evidence gaps.

## Final-grade summaries

`await account.final_grades(budget=budget, max_age_seconds=0)` returns immutable
`FinalGrades(identity, items, observation)`. Each `SubjectGradeSummary` has
`subject`, `midterm`, `predicted_annual`, and `annual`. Each value is a
`GradeSummaryValue(availability, raw)`:

- `AVAILABLE` preserves rendered text, including empty strings, `-`, grade
  symbols, and descriptive labels. It does not assert that a grade is assigned.
- `UNAVAILABLE` means the optional column is absent and has `raw=None`.

The annual column is required. Missing/ambiguous tables or malformed subjects
are parse errors, not partial collections. Bounds are 128 subjects, 64 expanded
columns, and 1024 characters per value, in addition to the shared parser/budget
bounds. The read makes one GET after authentication; it does not change grade
filters or fetch individual-grade details. It reuses the same session, cache,
coalescing, and bounded expiry-recovery policies as identity/profile reads.
See [the grade summary contract/provenance](contracts/grades.md).

## Exceptions, retries, and diagnostics

Catch specific classes from `librus_python_api.exceptions`, or their `LibrusError`
base. `error_for(ErrorKind)` is the central redacted factory. The foundation
`LibrusError(kind)` constructor uses the same registry. Kinds and messages never
contain arbitrary response data, secrets, account aliases, or URLs.

Enabled outcomes include `InvalidInputError`, `CredentialsRejectedError`,
`AccountActionRequiredError`, `SessionExpiredError`, `AccessDeniedError`,
`ThrottledError`, `MaintenanceError`, `ConnectionError`, `OperationTimeoutError`,
`LimitError`, `ParseError`, `UnsupportedCapabilityError`, and `ClosedError`.
Interactive CAPTCHA/2FA is unsupported and reported as required account action.
Required-schema failures are parse errors, not empty success or source fallback.

Tenacity permits at most two safe-read attempts for proven session expiry only.
The initial login is outside retries. Recovery uses at most one fresh login and
the original budget/deadline. 401 and exact approved login redirects establish
expiry; arbitrary HTML/redirects do not. Denials, connection ambiguity, parser
failures, throttles, and maintenance are not replayed. Failed authentication and
denied operations and expiry persisting after recovery have scoped cooldowns.
429/503 and Retry-After pause the shared
scheduler without accumulating a resumed burst; server intervals are capped at
24 hours to prevent untrusted timer overflow.

Pass `diagnostic_sink=loguru_sink` from `librus_python_api.diagnostics` to opt in.
The application owns Loguru sinks/pretty formatting/JSON serialization. Typed
`DiagnosticEvent` contains operation, outcome, elapsed seconds, and labelled
budget totals. Shared-budget totals can include other concurrent account work
and must not be summed as per-operation traffic. Sink exceptions cannot change
the retrieval outcome. No credentials, aliases, identities, URLs, response bodies,
or exception objects are passed to the sink.

## Consumer experiment and limitations

The opt-in [consumer adapter PR](https://github.com/krzysztofbury/librus-mcp/pull/38)
retains the 24-tool catalogue and legacy profile serialization. Its launcher owns
the service; the production CLI/dependency selection remains unchanged. Missing
lucky-number data fails explicitly until a legacy unavailable marker is evidenced.
No native failure is replayed through the legacy backend.

Other callback/account variants, profile layouts, summary variants and encodings
remain unverified. Individual grades, windows, GPA, other academic reads,
and messaging/event operations,
daily credentialed CI, PyPI, macOS/Windows qualification, and production backend
migration are not part of this completed Linux local-first delivery.
