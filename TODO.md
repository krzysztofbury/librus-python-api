# TODO

Open work only. Released scope is in [CHANGELOG.md](CHANGELOG.md), live evidence
in [VERIFICATION.md](VERIFICATION.md) and per-family limits in `contracts/`. The
0.x to 1.0 roadmap (P0-P9, S1-S10 and the MCP 2.0 cutover checklist) is complete
and lives in the Git history of this file.

## Goal

A typed, bounded async client for several independent Librus logins, published
on PyPI and consumed by [librus-mcp](https://github.com/krzysztofbury/librus-mcp).
The library owns sessions, shared traffic budgets, parsing and optional durable
workflows; MCP chooses accounts, presents consent and owns its tool schemas.

Rules that hold for every release:

- Ordinary tests and CI stay offline. Live checks need explicit authorization
  and follow [CONTRIBUTING.md](CONTRIBUTING.md#live-verification). The weekly
  credentialed check (`live-check.yml`) is active.
- A family is "verified" only after a live page from the current build has been
  checked. Record missing access as pending, never as passed.
- Consumer (`librus-mcp`) changes are a separately authorized task. Change the
  library version only when its own contract changes.

## Next

- [ ] Triage the unmapped Synergia menu modules (#41) into concrete read
  candidates, out-of-scope modules and evidence needs.
- [ ] Evaluate unmapped Gateway API 2.0 resources (#39); populated JSON is
  already observed for lucky numbers, free days, calendars and school notices.
- [ ] Then bump `librus-mcp` from 1.0.2 to the current library and expose the
  reads added since (archive mailbox and unread counts, correspondent filters,
  teacher subjects, school-year archive, formative grades, receipt class labels).

## Blocked on live evidence

Do not relax guards, guess layouts or repeat known-empty probes to close these.

- [ ] Behaviour notes (#26): implement the public read once a populated page is
  observed ([decision](contracts/behaviour-notes.md)). Every available login
  shows an explicit empty page.
- [ ] Completed lessons: verify a populated page and pagination on an account
  whose school has the view enabled. All four available logins show it disabled.
- [ ] Modern notes, trash, drafts and archived content (#45).
- [ ] Broader school-layout coverage: other schools and roles, populated
  last-login views, custom attendance types, full-year subject-frequency
  resolution, parallel group lessons, empty and rich announcement layouts,
  populated descriptive grades and publications.

## Communication gaps

- [ ] Attachments: sent-message downloads, multiple/empty files, broader
  signed-key/handler/header variants and upstream read-effect evidence. Do not
  expand allowlists without independent qualification.
- [ ] Legacy recipients and receipts: populated subgroup/virtual-class semantics,
  explicit empty recipients, sent pagination, multiple-recipient receipt/status
  variants. 1.5.0 added the class-label receipt column (#60); what decides
  whether it is shown is not established.
- [ ] Modern sending: rejection envelopes and other positive send-acceptance
  variants, unavailable directory/virtual branches and unobserved expanded
  recipient layouts.
- [ ] Read-once layouts: qualify only on a dedicated test login with disposable
  events and separately approved recovery integration. Routine live checks
  exclude them.

The C01-C05 items below are referenced from the communication contracts. Resume
each only with the evidence it names; empty observations are not passes.

- [ ] **C01 - Independent delivery acknowledgements:** unknown. Resume only with
  a distinct documented or observed field and clear semantics. Backend acceptance
  and recipient read timestamps are not substitutes; durable UNKNOWN send
  history and duplicate protection stay untouched.
- [ ] **C02 - Modern virtual/class-parent live coverage:** selections and routes
  are offline-tested. Resume with advertised, populated examples and fresh scoped
  approval. Legacy virtual selection is not implemented.
- [ ] **C03 - Populated legacy subgroup live coverage:** choice parsing and
  lookup are offline-tested. Resume with a real populated selector and
  independently checked membership.
- [ ] **C04 - Archive content:** archive mailbox listing shipped in 1.1.0 and
  original-body/withdrawal metadata is offline-tested. Archived content opens
  stay `UNSUPPORTED_CAPABILITY` until fixed routes, references and side effects
  are established (#45).
- [ ] **C05 - Expanded and CC/BCC receipt live coverage:** parsing and channels
  are offline-tested. Resume with an existing multi-recipient example and
  independently verified expectations. Never send test messages to close it.

## Quality and operations

- [ ] Intermittent macOS qualify hang in the notification checkpoint tests
  (#64). The next occurrence dumps stacks via `faulthandler_timeout`.
- [ ] Representative load evidence: fixture-server workloads (full mailboxes,
  changing pages, warm/cold caches, slow bodies, cancellation under saturated
  concurrency), recorded request counts, elapsed-time distribution, peak memory
  and numeric acceptance thresholds. No performance claim before this exists.
  Parser resource measurements exist under `tests/performance` (opt-in).
- [ ] Targeted mutation tests for critical guards: account isolation, bounded
  queues/bodies/pages, send non-retry, checkpoint ordering, redirect rejection.
  Do not use an untriaged mutation score as acceptance.
- [ ] Model unpublished data (for example an unpublished timetable) separately
  from empty success, once a live example shows its markup.
- [ ] Weekly live check freshness outside GitHub: no external watchdog detects
  scheduled runs that never start; see [RELEASE.md](RELEASE.md#weekly-live-check).

## Consumer-owned (tracked in librus-mcp)

- Document a 2.0 to 1.x downgrade, or record that none is supported.
  MIGRATION_2_0.md covers the upgrade; 2.0 moves adopted 1.x notification files
  to `state_dir/legacy-1x`.

## Architecture and ownership

| Concern | Owner |
| --- | --- |
| Account credentials/configuration, aliases, feature flags | MCP |
| Session lifecycle, authentication, scoped cookies, transport budgets | Library |
| Shared rate/burst/concurrency/queue limits across independent account clients | Library service, reused across MCP calls |
| Choosing logins, combining overlapping results, and summary generation | MCP |
| Retry classification, bounded reauthentication, account/operation cooldown machinery | Library, with public policy settings supplied by MCP |
| Endpoint capabilities, JSON/HTML parsing, typed domain data, pagination, reference caches | Library |
| Requested-category orchestration, first-run/diff/seen-state policy | Optional API notification workflow; MCP selects requested categories and serializes results |
| Durable checkpoints, canonical hashes, process locks, transactions, recovery | Optional API persistence layer |
| Attachment authorization and bounded byte streaming | Library |
| Download destination selection | MCP configuration |
| Reusable safe filenames, bounded temporary files, atomic non-overwriting publication | Optional API file layer |
| Message send transport and typed delivery outcome | Library |
| Durable send confirmation expiry/binding, single-use claims and recovery | Optional API persistence layer |
| Human approval and permission to invoke a write | MCP or other application |
| Stable detail keys and explicit attendance ratios | Library |
| MCP schemas, JSON serialization, response envelopes and context limits | MCP |

## Deferred

- Sync facade, persistent session export/import, extra account-management APIs
  and wider endpoint coverage need a demonstrated consumer first. Session
  persistence would need full cookie restrictions and explicit secure storage.
- Rust and a copied upstream compatibility namespace are out of scope.
