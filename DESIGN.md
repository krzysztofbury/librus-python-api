# Foundation design and evidence

## Implementation boundary

This is source-informed original work, not a clean-room implementation. Existing
clients provide behavioral references, not source/tests/fixtures to transplant.
All current HTTP fixtures are independently authored synthetic examples.

The installed package currently provides configuration, errors, request budgets,
admission scheduling, and a scope-preserving native transport. It does not yet
provide the authenticated account-service API. Fixed routes and OpenAPI paths
are evidence-labelled; source-informed routes are not live observations.

## Dependencies

| Dependency | Role | License |
| --- | --- | --- |
| Pydantic 2 | Strict, frozen configuration with runtime validation | MIT |
| aiohttp | Native async account-isolated HTTP transport | Apache-2.0 AND MIT |
| lxml | Selected for bounded semantic HTML parsing in the next identity phase | BSD-3-Clause |

Pydantic configuration does not read environment variables. Validation errors
are translated to a closed library category without attaching their raw input
or validation exception. Domain records remain independent of MCP wire schemas.
Runtime dependency distribution metadata is checked when building/installing.

FastAPI is not needed: this library is an HTTP client, not an application server.
Logging is not implicitly configured. Future diagnostics must be opt-in,
bounded, and redacted before reaching any logging implementation.

## Shared scheduling

Use one `RequestScheduler` for the entire future service, not one per account
or tool call. Each configured login has an independent account key even when
two logins represent the same student. Keys are validated before admission state
can be created. Unknown accounts cannot grow queues or maps.

The scheduler combines the following bounds at one admission boundary:

- Global/per-account active and waiting request limits.
- A shared token bucket for request rate and burst size.
- FIFO waiting within each account and round-robin eligible-account selection.
- A caller-shareable `RequestBudget` with a whole-operation deadline and maximum
  request count. Queue time is included; dispatches are not refunded on failure.
- A service-wide pause that clears burst credit and caps resume credit at one
  until admitted work/backlog drains, even when the rate timer is delayed.

Admission is synchronous between event-loop suspension points. Only admitted
requests create owned workers. A single timer handles rate resumption; saturated
callers do not create independent sleepers, semaphores, or background retries.
The per-account ring and queues cannot exceed their configured account/queue
capacities. Cancellation removes queued work or joins an active worker before
its slot can be reused. Closing fails queued work, cancels active workers, and
awaits cleanup. A canceled closer cannot cancel the shared close worker.

The scheduler's callback is an internal transport integration boundary, not a
public authenticated URL escape hatch. Callbacks must honor cancellation; this
does not protect against arbitrary Python code that bypasses admission, starts
I/O before submission, or deliberately suppresses cancellation indefinitely.
The future transport must dispatch every login step, redirect, retry, metadata
lookup, and page fetch through this same boundary.

Default policy: one request/second, burst one, two global active requests, one
active request/account, 32 global queued requests, eight queued requests/account,
and at most 16 accounts. These are conservative library defaults, not a known
Librus-approved traffic allowance. No rate increase is qualified by quiet live
accounts. Independent services/processes require separate coordination.

## Current proof and limits

The tests observe the public scheduler through real loopback HTTP for four
account keys with three requests each. They check the combined token-bucket
envelope, global peak two, per-account peak one, and exact request counts. Fast
fixture-only rate settings are not recommended live tuning values.

Fault tests cover queue overflow, shared-budget exhaustion, waiting/active
deadlines, cancellation near rate admission, paused resumption, close/rejection,
and cross-event-loop budget rejection. These prove scheduler behavior, not
authentication, populated Librus parsing, or a speedup over the existing client.

## Authentication research direction

The reviewed clients describe a cookie-based portal/form/redirect flow, not the
obsolete OAuth password grant. Reuse that behavioral sequence when implementing
authentication, while validating destinations, bounding every attempt/body/hop,
retaining cookie scope, and verifying typed identity before declaring success.
Third-party observations are research evidence, not our live verification.

References reviewed outside this source tree:

- [librus-apix client][apix-client], a source of behavioral flow requirements;
  its distribution has conflicting license evidence, so no material is copied.
- [librus-synergia authentication notes][auth-notes], a source of gateway/session
  research leads. Its claimed observations are not independently reproduced here.

[apix-client]: https://github.com/RustySnek/librus-apix/blob/2fedfe8ffa4933abb884929716519ddbeb8eb32d/librus_apix/client.py
[auth-notes]: https://github.com/MichalZaniewicz/librus-synergia/blob/7dc115fb99ac1d736da44fc55eaa76fda21f35cb/docs/authentication.md
