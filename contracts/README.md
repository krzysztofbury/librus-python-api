# Upstream contract and manual validation

`upstream.openapi.yaml` documents the upstream HTTP wire interface, including
HTML scraping routes. It is not the Python domain API or the MCP tool schema,
and it is not an official Librus specification.

The catalogue covers the bounded cookie-login flow, gateway identity, HTML
student-information and [grade reads](grades.md), including fixed-form
all/week/last-login view POSTs, plus [attendance collections](attendance.md).
Source-informed
routes and synthetic callback/header
variants are labelled separately; none are claimed live-verified. Unknown
redirect routes fail closed. Do not infer an endpoint schema from a similarly
named third-party operation.

0.2.0 is grades-only. Other academic reads move to 0.3.0, messaging to 0.4.0.
Observed grade-view forms and unqualified populated layouts are distinguished in
grades.md; an exercised route is not proof of every response variant.
The 0.3.0.dev0 attendance routes include explicit details and gateway metadata
for frequency. Narrow installed evidence covers one context; source-informed and
offline-only alternatives remain distinct from populated qualification.

## Adding an endpoint

Ship these together in the same change:

1. A fixed route in `src/librus_python_api/config.py:ENDPOINTS`. All request
   dispatchers resolve routes from this catalogue. Parsers contain no routes.
2. A matching OpenAPI operation with the same `operationId`, method, and path.
   Document exact origins, required query/form/body inputs, authentication,
   success and failure responses, content types, and known account variants.
   Do not store credentials, cookies, signed URLs, or identifiable captures.
3. `x-side-effect`, `x-retry-safe`, `x-evidence`, and `x-evidence-note` on the
   operation. Record independently established requirements, fixture provenance,
   and unresolved live/schema gaps. A GET can have side effects. Do not label
    an endpoint independently observed based on a third-party report.
    Selecting a view is also a side effect (`select_view`): never automatically
    replay that POST just because it does not modify school records.
   `x-origin` and `x-upstream-origin` must match the central route catalogue.
4. Independently authored populated, empty, and malformed wire fixtures exercised
   through the actual parser/transport path. Explain how the wire response maps
   to the Python record without presenting synthetic evidence as live proof.

Use `text/html` with a string schema for raw HTML responses. Document required
semantic markers/headers and parse failures in the description; do not pretend
the upstream returns the normalized domain record as JSON. JSON operations need
their actual response envelope and field schemas. Schemas and references stay
local so validation cannot download a remote schema.
Declare path items inline; path-item references are rejected so they cannot
hide operations from the catalogue parity check. Local schema references remain
supported.

```sh
uv run --locked python -m pytest tests/test_contracts.py
```

The check rejects missing/extra routes and mismatched operation IDs, effects,
retry policy, or evidence classification. It also validates OpenAPI syntax.
It does not prove that a description/schema matches today's live Librus.

## Bruno

In Bruno, choose **Import > OpenAPI**, then select `upstream.openapi.yaml`.
Bruno supports OpenAPI 3.x YAML; see its [import documentation][bruno-import].
The default server is deliberately loopback-only. Use a
separate local environment for authorized manual validation. Never bulk-run
login, mark-read, read-once, or send operations. Importing a contract is not
authorization to call live Librus.

Keep generated collections and local secrets outside this checkout. Do not
commit real responses or cookie jars. Credentials have no committed examples or
defaults. API-side and Synergia-side origins differ on live Librus. Override
origins separately using each operation's `x-upstream-origin`; never bulk-run
the collection. Only explicitly authorized accounts and operations may be tested.

[bruno-import]: https://docs.usebruno.com/open-api/importOAS
