# Native MCP 2.0 readiness

Reviewed 2026-10-04 against the consumer's [2.0 roadmap][roadmap] and manifest at
`0aaf658c657197817a7c8cae35d39f05484403fd`. The consumer was inspected read-only as
a requirements reference. No consumer implementation, fixture or documentation
was copied into this MIT library.

## Delivery decision

Replace the consumer backend and wire contracts together in MCP 2.0. There is
no intermediate MCP 1.x compatibility release, old-field translation layer or
fallback backend. Library and consumer versions remain independent. Develop
against exact local artifacts; qualify the published library before releasing
the consumer. Tool/schema changes do not authorize resetting notification
checkpoints or retrying an uncertain send. State migration or quarantine and
rollback must be deliberate and tested.

## All 18 planned items

IDs follow the original roadmap order. "Available" describes library behavior,
not completed MCP integration. These foundations are included in local-first
0.6.0; additions are recorded in [the changelog](../CHANGELOG.md).

| ID | Requirement | Library readiness | Consumer work |
| --- | --- | --- | --- |
| A01 | Common collection envelope | Available: typed collections, bounded pages/cursors and observation metadata. No snapshot guarantee. | Define one wire envelope; retain domain-specific completeness and cursor semantics. Do not add fake upstream paging to local aliases. |
| A02 | Records rather than display-name maps | Available: typed grade, recipient, agenda and other collections preserve separate records. | Serialize arrays; avoid merging same-name subjects/people or same-day events. |
| A03 | Stable keys for upstream labels | Added now: `DetailField` and `normalized_fields` for agenda, homework and attendance details. Existing collection records already have named fields. | Expose normalized records, raw/unknown fields and notes under new schemas. Unrecognized metadata remains raw, not guessed. |
| A04 | Explicit attendance units | Available: `FrequencyMeasure.ratio` in 0..1 or `None`, with separate counts. | Use native `ratio`; remove legacy percentage conversion. |
| A05 | Filter scope argument | Available: `GradeView` and `AttendanceView` implement all/week/last-login semantics. | Expose `scope` mapped to native `view`; remove `sort_by`. |
| A06 | IDs/references instead of URLs | Available: validated numeric attendance IDs and account/kind/backend-bound school/message references. | Publish native reference schemas; remove arbitrary `href`/`detail_url` inputs. |
| A07 | Integer calendar and consistent date inputs | Available: integer year/month, civil dates and bounded windows, including monthly homework aggregation. | Define consistent argument names and default dates. |
| A08 | Stable error categories | Available: domain error classes/codes, typed unsupported states and uncertain send outcomes. | Add configuration/permission categories and sanitized JSON error serialization. |
| A09 | Remove unbounded collection flag | Available: bounded message/lesson collection with safe continuation. | Remove `all_pages`; expose native limits/cursors. |
| A10 | Replace standalone consume tool | Available: checkpointed consume plus `NotificationWorkflow` and `NotificationStore`. | Expose stateful notifications, consume consent and delivery acknowledgement; remove redundant tool only when its replacement is usable. |
| A11 | Package/entry-point rename | No library blocker; import package is already `librus_python_api`. | Move to `librus_mcp`; actual entry point is `src.cli:main`, so retain CLI routing rather than blindly selecting `server:main`. |
| A12 | Mutation-tool replacement | No runtime library prerequisite. | Inspected manifest still declares Cosmic Ray; evaluate mutmut after package rename and retain meaningful regressions. |
| A13 | Explicit/XDG configuration | Available: explicit credentials/settings, no implicit consumer config discovery. | Implement `LIBRUS_CONFIG`/XDG precedence and remove cwd discovery. |
| A14 | Configuration upgrade instructions | Available: explicit construction in `API.md`. | Document breaking configuration changes with MCP 2.0; no intermediate deprecation release is required. |
| A15 | Retire old state mirror | Available: optional native SQLite persistence with replay and single-use send claims. | Migrate or quarantine pending data, then remove the short-hash mirror; no indefinite dual writes. |
| A16 | Resolve old state-path collisions | Native stores use explicit ownership/binding; they do not discover legacy files. | Reject ambiguous old paths before one-time import; retain originals for tested rollback. |
| A17 | Attachment resources | Available: typed metadata, bounded streams and optional atomic `files.publish_attachment()`. | Define resource URIs/storage/host support; signed download URLs are not durable resource IDs. |
| A18 | Attachment and response size bounds | Available: shared transport/byte/deadline bounds and cancellation-safe streams. | Keep serialized response/resource/context limits; avoid large inline payloads. |

## Implemented in this increment

The reusable gap was detail-key normalization. The [detail contract](detail-fields.md)
lists known labels, displayed-value semantics, limits and evidence. Ambiguous
attendance labels now fail before public result/cache publication. Original
loopback tests cover known and unknown labels, empty/full text, independent
accounts, cached reuse and failure recovery. No new route is needed.

No generic repository/UoW or common JSON envelope is added to the library:
upstream calls are not transactional, and a wire envelope is a consumer schema.
Existing typed domain collections provide the necessary facts.

## Next acceptance slice

1. Define MCP 2.0 schemas and native service lifecycle with one shared scheduler.
2. Exercise every enabled tool through stdio against the installed library and a
   local fixture server; assert new schemas, effects, budgets and account binding.
3. Prove state import/quarantine and rollback with disposable stores, retaining
   pending events and UNKNOWN send history without duplicate dispatch.
4. Remove old backend dependencies, redundant scraping/recovery/caches and
   old wire models after the replacement invariants pass.

Behaviour notes, observation cards and wider live qualification remain the
evidence-dependent gaps in [TODO.md](../TODO.md). This review does not enable new
live access or complete the consumer migration.

[roadmap]: https://github.com/krzysztofbury/librus-mcp/blob/0aaf658c657197817a7c8cae35d39f05484403fd/TODO.md#major-release-200
