# Verification

What has actually been run, and what has not. Earlier per-increment logs are
in the Git history of this file.

## Current release evidence (2026-10-05)

The library-only 1.0.0rc1 was published through real PyPI Trusted Publishing in
[run 37281758063](https://github.com/krzysztofbury/librus-python-api/actions/runs/37281758063)
at `01b32e0dd2407809cf89aec32b1e49b32b2a3363`. The public JSON reports non-yanked
wheel/sdist uploaded on 2026-10-05. Hashes matched the sealed run, and its fresh
Python 3.14 public-index installation and loopback runtime smoke passed:

- Wheel SHA256: `c879dcb4fda13314254e0c0d012c9a2981e87f8b7a431247df9c3990a4fbe893`.
- Sdist SHA256: `7ecbefdba84714dc95080665d4019adbc40c497475856e897d24a51b6433be13`.

Prerequisites #22-#25 subsequently merged as PRs #28-#31 and closed separately.
Remote main was confirmed at `68ae2197d636773bbf066df8ac818f3ce3f1532e` after #25.
Stable 1.0.0 preparation freezes the documented native library contracts; its
own source/artifact qualification, remote tag, hosted release matrix and public
upload/confirmation remain pending. The rc1 upload does not qualify new bytes.
MCP installed/stdio acceptance, production-state migration/rollback, comparative
performance and broader live-school evidence remain separate unfinished gates.
No new live Librus access or production-state change is authorized by this work.

The deployed dependency-drift workflow passed its first manual run
[37311653065](https://github.com/krzysztofbury/librus-python-api/actions/runs/37311653065)
on both Python versions at pre-Windows main `b268124c88f20556bc95c9445a708fe4942568b2`.
This exercises the newest-permitted-runtime Linux artifact path, not Windows
qualification or evidence of a scheduled trigger.

Earlier sections below record their evidence at each historical checkpoint;
their then-pending upload/merge statements are superseded by this current entry.

### Stable release preparation review

Source 1.0.0 passed 1,607 tests on Python 3.13/3.14, with 25 Windows-only skips
and one optional resource test deselected, plus Ruff/format, strict mypy, hooks,
history scan, built metadata and strict Twine checks. The initial local seal
correctly rejected uv's extra build-directory `.gitignore`; copying only the
archives into a separate directory as the hosted workflow does passed sealing.

Installed qualification then exposed an existing timeout-fixture race: its 30 ms
deadline could expire in DNS before the first request reached the server, making
the next request enter the stalled-response branch. Injecting 100 ms into the real
socket resolver reproduced it with zero server calls. The existing owner test now
warms the same single-slot connector, asserts an actual body byte was received
before timeout, and completes the next request while the stalled fixture remains
unreleased. Both ordinary and delayed-DNS cases passed, along with all 41 transport
tests. No production transport seam or behavior was changed. Full final-head
source/installed and hosted qualification remain pending after this test edit.

Local final-head qualification then passed 1,608 tests in both source runs and
all eight installed wheel/sdist configurations (Python 3.13/3.14, locked/latest),
with all eight loopback smokes and artifact/seal/security gates. Hosted run
37313408236 still failed: Linux 3.13 and Windows 3.14 process-race cases observed
LIMIT instead of INVALID_INPUT in the losing process. The public busy-timeout
contract permits LIMIT before any upstream work; the race test had incorrectly
required one scheduling-dependent error. Its existing real SQLite contention
test independently proves LIMIT leaves a pending token and performs no HTTP.

The process worker now reports its public dispatched-request count. The race
test requires exactly one accepted sender and one loser reporting only
INVALID_INPUT or LIMIT, with zero loser traffic. After restart it requires one
accepted history record and explicitly rejects replay of both presented tokens
with INVALID_INPUT, unused attempts and zero parent-service traffic. Actual
fixture send count remains exactly one. All 47 persistence cases passed locally
after the change. No production locking, busy budgets, retry behavior or UNKNOWN
history changed. Full final-head CI must pass; failed jobs are not waived.

Run 37314309378 passed Linux source/installed and Windows 3.13, but Windows 3.14
exposed a second-boundary assumption in the unused-preview expiry test: expiring
the first token does not expire a later-created second token. The owner test now
uses an explicit clock with same-second and one-second-staggered creation,
advances to the later of the two actual expiries, and verifies both old tokens
are gone and the new token remains pending without HTTP. The staggered case
reproduced the original assertion failure locally before the test correction.
Expiry implementation, production clock and TTL remain unchanged. Final-head
qualification is required after this fixture-only edit.

Pair-programmer review applied TigerStyle #4 (paired validation), #6 (positive
and negative space), #11 (warning clean) and #13 (explicit defaults): package,
OpenAPI, classifier, artifact assertions and versioned documentation agree;
library stability is explicitly distinct from consumer/live readiness. Existing
artifact/runtime and release-boundary tests own this version-only change; no
duplicated export-list or source-string tests were introduced. The fixture change
strengthens observable connector cleanup with a demonstrated failure and no
test-only production code. No remaining source review blocker was identified.

## Windows disk qualification (#25, 2026-10-05)

Initial Windows installed-artifact qualification failed on missing IANA timezone
data and LF-only process-fixture handshakes, rather than being accepted from Linux
checks. The Windows runtime now declares tzdata and tests normalize CRLF explicitly.
[Run 37310538865](https://github.com/krzysztofbury/librus-python-api/actions/runs/37310538865)
passed both Python 3.13/3.14 Windows jobs: 185 disk-boundary tests in each of four
installed wheel/sdist configurations, eight POSIX-only cases skipped per run, and
all installed loopback smokes passed. Its quality and Linux artifact jobs passed.

The original implementation uses documented Microsoft Win32 APIs through the
PSF-licensed pywin32 dependency. No consumer helpers or another Librus client's
fixtures were copied. Required Windows cases use real ACLs, NTFS hardlinks,
junctions, competing processes, killed send claims and raw checkpoint/replay/ack
recovery. Capability-report injection separately exercises unsupported volume
guards, not a fabricated filesystem. No live Librus requests occurred.

Pair-programmer review applied TigerStyle #2 (bounded loops), #4 (paired
validation), #6 (positive and negative space), #12 (full error handling) and
#13 (explicit defaults). It caught ancestor rename races, SQLite journal ACL
inheritance and temporary-handle cleanup after failed validation. Ancestors now
remain pinned, journals require protected inheritable private directory ACLs,
and failed CREATE_NEW validation deletes only the owned handle. Commit-point
cancellation joins the rename worker and leaves only a complete final file.
The public private-directory helper avoids consumer-owned Win32 provisioning.
Final head `08ad8db59f615aeb9a9ffddcde27d310481793f5` passed all five CI jobs in
[run 37311543233](https://github.com/krzysztofbury/librus-python-api/actions/runs/37311543233).
Each of four Windows installed wheel/sdist configurations passed 193 tests and
its loopback smoke, with eight POSIX-only cases skipped. Local source on Python
3.13.15/3.14.7 and four Linux installed configurations passed 1,607 tests each,
skipping 25 Windows-only cases and deselecting one optional performance test.
Ruff, formatting, strict mypy including the Win32 module target, artifact/strict
Twine checks, history secret scan and hash-locked dependency audit passed.
No remaining review blocker was identified. PR #31 merged and #25 closed after
comparing its exact head with the pushed SHA. Stable release is a separate gate.

The existing maximum-body parser resource gate also passed separately on Python
3.14: eight 262,144-byte jobs, 0.1085 seconds elapsed, 0.0156 seconds maximum
heartbeat delay and 1,500,467 traced peak bytes. This is a coarse local resource
check, not comparative MCP performance qualification. Disposable builds, reports
and environments allocated by those commands were cleaned up.

## Typed notification recovery (#24, 2026-10-05)

Focused source qualification passed 101 notification tests, including twelve new
recovery cases. Public SQLite/loopback cases cover compact historical and modern
delivery discovery, original source/receipt across restart, raw-only recovery
after parse failure, retained uncertain consumption, delivery coexisting with raw
or uncertainty, acknowledged cursor progress, invalid/missing/foreign context,
corrupt seen-state rejection, bounded output and repeated cancellation. Existing
fresh-process bootstrap recovery now uses both new public lookup methods.

Pair-programmer review applied TigerStyle #2 (bounded loops), #6 (positive and
negative space), #12 (full error handling) and #13 (explicit defaults). Independent
flags retain coexisting work instead of forcing a misleading single status. Reads
use an owned SQLite snapshot without registration or creating per-context lock
files. An active-poll case proves status can observe a conservative marker while
explicit resolution remains excluded; it cannot authorize another consume.
Ruff and strict mypy passed. No remaining review blocker was identified. No live
Librus access, implicit recovery mutation or production migration occurred.

Full local qualification passed 1,605 tests on Python 3.13.15/3.14.7 and in each
of four locked installed wheel/sdist configurations. One optional performance
test was deselected per run. All installed runtime smokes, Ruff, formatting,
strict mypy, artifact/metadata checks and strict Twine passed. Disposable builds
and environments were cleaned up. Hosted CI/merge and stable publication remain
separate gates; the Windows platform issue is still open.

## Neutral notification bootstrap (#23, 2026-10-05)

Focused source qualification passed 89 notification persistence/workflow tests,
including 24 new public-boundary cases. Tests exercise all mapped categories,
explicit unmapped reports, conflicts/malformed inputs/context mismatch, capacity
rollback, historical archive validation, restart and fresh-process recovery,
idempotent acknowledgement, repeat-import refusal, staging failure, repeated
cancellation and shutdown. The first regression failed on missing public imports.
All inputs are original fictional fixtures; no old consumer implementation or
production files were copied and no live Librus request was authorized or made.

Pair-programmer review applied TigerStyle #2 (bounded loops), #4 (paired
assertions), #6 (positive and negative space), #7 (predictable memory) and
#12 (full error handling). It caught context registration outside the atomic
import: registration now shares the state/delivery commit, and tests prove no
partial context/state/delivery survives failure. Historical items reject invented
provenance, raw progress and uncertain consume markers; serialized event bytes
are bounded before complete batch construction. Ruff and strict mypy passed.
No remaining review blocker was identified. This implements a neutral library
boundary, not a production migration or lossless reverse mapping of old opaque IDs.

Full local qualification passed 1,593 tests on Python 3.13.15/3.14.7 and in each
of four locked installed wheel/sdist configurations. Every run deselected one
optional performance test; all four installed loopback runtime smokes passed.
Ruff, formatting, strict mypy, archive/metadata validation and strict Twine passed.
Disposable builds/environments were cleaned up. The development version remains
1.0.0rc1 until all four integration issues qualify; these artifacts were not
published. Hosted PR qualification, merge and stable publication are separate gates.

## Modern notification source (#22, 2026-10-05)

Local source qualification passed 1,569 tests on Python 3.13.15 and 3.14.7.
The same count passed in each of four locked installed configurations:
wheel/sdist on both versions. Each run deselected one optional performance test;
all installed loopback runtime smokes passed. Ruff, formatting, strict mypy,
archive metadata/content checks and strict Twine checks passed. Disposable
artifacts and environments were cleaned up; no live Librus access occurred.

Ten new public-boundary cases exercise explicit legacy/modern selection,
summary-only shared budgets, account separation, identical numeric message IDs,
pending replay after restart/export/import, offline acknowledgement, old format-3
legacy import, incompatible archive rejection, ordinary failure before read-once
consumption and all-category polling. Existing persistence fault/process tests
remain intact. The initial regression failed on the missing source-selection API.

Pair-programmer review applied TigerStyle #2 (bounded loops), #4 (paired
assertions), #6 (positive and negative space) and #13 (explicit defaults).
Batch decoding now caps item count, validates reference account/source on read,
and keeps legacy as the explicit default for old pending records. Backend changes
reject pending delivery mismatch rather than discard or rewrite it. No remaining
review blocker was identified. Hosted PR qualification and merge are separate
gates; this entry does not claim stable publication or completed MCP migration.

## Hosted release workflow verification (2026-10-05)

[PR #20](https://github.com/krzysztofbury/librus-python-api/pull/20) merged after
its exact pushed head passed CI. Remote main and the annotated `v0.7.0` tag were
confirmed at `2a59a73acea5d1061a2d2e906241a7d89e40d6af`.

[Run 37280801918](https://github.com/krzysztofbury/librus-python-api/actions/runs/37280801918)
passed the manual workflow in `verify` mode. The build/source gate and all eight
qualification jobs succeeded: Linux/macOS, Python 3.13/3.14, locked/latest
runtime dependencies. Each of the sixteen installed wheel/sdist configurations
passed 1,559 tests with one optional performance test deselected and passed its
loopback runtime smoke. Every matrix job verified the same sealed archive pair.
Publishing and post-upload confirmation were skipped as intended.

The next candidate is explicitly approved as a library-only `1.0.0rc1` prerelease,
with unchanged supported API from 0.7.0. Its exact-version hosted qualification,
OIDC upload and public-index confirmation are separate gates, not proved by this
0.7.0 run. MCP migration, old-state migration/rollback and broader live checks
remain unfinished. No live Librus call or PyPI upload occurred in this run.

Local 1.0.0rc1 preparation passed 1,559 source tests and 1,559 tests in each of
four locked installed configurations (wheel/sdist, Python 3.13.15/3.14.7), with
one optional performance test deselected in every run. All four runtime smokes,
archive/strict Twine checks, manifest sealing/verification, Ruff and strict mypy
passed. Disposable archives and environments were cleaned up. These local bytes
are not the eventual hosted upload; the publishing run must qualify its own pair.

## Release pipeline preparation (2026-10-05, local only)

Package version remains 0.7.0. The manual `workflow.yaml` targets are `verify`
and `pypi`; TestPyPI is not configured. Release gates seal one archive pair,
check remote identity, qualify installed distributions, and separate upload
authority from build/test jobs. See [RELEASE.md](RELEASE.md).

Locally exercised one wheel/sdist pair with archive/metadata verification,
strict Twine checks, manifest sealing and digest verification. All eight installed
combinations passed 1,559 offline tests each, with one optional performance test
deselected: wheel/sdist, Python 3.13.15/3.14.7, locked/latest dependencies. All
eight installed loopback smokes passed. Fresh latest resolution selected the
same runtime versions as the lock at this checkpoint. No live Librus was called.

The final local source suite also passed 1,559 tests with one deselected. Ruff,
format checks, strict mypy, repository hooks/actionlint, worktree/history secret
scans and the hash-locked dependency audit passed. All task-owned disposable
builds and environments were cleaned up; no release archives were retained.

GitHub API confirms the `pypi` environment requires owner review, permits only
branch `main`, allows self-review and disables administrator bypass. The existing
main ruleset remains disabled and was not changed. PyPI pending publisher setup
is owner-reported, not an exercised OIDC upload or project-name reservation.

Hosted workflow execution, macOS qualification, weekly dependency-drift runs,
publication, public checksum confirmation and fresh PyPI installation remain
pending. This preparation does not close MCP migration or 1.0 readiness gates.

## 0.7.0 library readiness (2026-10-05, local development)

Started from remote main `90dead4d8f49975f2800e974ed3c097be7c80b1d` (0.6.1),
confirmed through GitHub. This entry qualifies local source and disposable
artifacts, not a merge, tag, PyPI publication or completed MCP migration.

Implemented and checked:

- Public account identifiers use domain-separated HMAC-SHA256 with a required
  application-owned 32-byte key. An independent OpenSSL vector checks the exact
  contract. Tests cover same-key restart stability, distinct-key isolation,
  password/login/alias/origin binding and invalid-key refusal before transport.
- Both SQLite formats and neutral notification archives advance to version 3.
  Old version-1/2 stores fail with unchanged database bytes. Old archive envelopes
  and payload versions fail without importing/resetting state. Existing real
  SQLite restart, multi-process, fault and load tests retain ownership of send
  uncertainty, duplicate prevention and notification replay guarantees.
- Removed Loguru and its now-unused transitive dependency from the lock. The
  inspected MCP manifest/source, including local native adapter files, has no
  Loguru usage. MCP remote main remained
  `0aaf658c657197817a7c8cae35d39f05484403fd`. No consumer code was changed.
  Standard-library logging retains allowlisted diagnostic fields and no global
  handler configuration.
- Beta/AsyncIO/POSIX/macOS metadata and explicit POSIX-only disk workflows.
  Both stores refuse unsupported platforms before creating files. Linux is the
  exercised platform; macOS is documented as not yet qualified in CI.
- Actual wheel/sdist inspection verifies metadata, `py.typed`, and lean contents.
  AGENTS.md, TODO.md, tests, capture/development scripts and verification logs are
  absent from the sdist. Hatch's automatically included `.gitignore` is allowed.
  The same archive verifier is wired into CI after building.
- README Python examples execute against real loopback HTTP and the public API,
  covering profile, homework, final grades, timetable, attendance, announcements
  and bounded messages. Installation text explicitly distinguishes local builds
  from future PyPI availability.

| Python | Source | Installed wheel | Installed sdist |
| --- | --- | --- | --- |
| 3.13.15 | 1536 passed | 1536 passed | 1536 passed |
| 3.14.7 | 1536 passed | 1536 passed | 1536 passed |

One optional hardware-sensitive performance case was deselected per run. All
four installed configurations also ran a standalone profile/final-grade loopback
smoke with the standard logging sink, verified the installed import location and
0.7.0 metadata, and confirmed Loguru was not installed. Dependency consistency,
Ruff, formatting, strict mypy, repository hooks, worktree/history secret scans
and the hash-locked dependency audit passed. No known vulnerabilities were found.

Tested 41-file source manifest SHA256, using the algorithm documented below:
`97411d88b967dd9c2b1de2f6fbb3a2a897b1cb23f0944310aff8fe20877c0f57`.
Disposable builds, test environments and the failed initial archive-inspection
scratch were removed. No live Librus calls, credentials, production databases or
existing UNKNOWN-send records were accessed or changed.

## Reference client and provenance

Outside these validation records, the documentation calls `librus-apix` "the
reference client". It was reviewed as a source of behavioural requirements and
compared offline against identical captured bytes; it was never a runtime
dependency, fallback or correctness oracle, and no code, tests, fixtures or
documentation were copied from it.

- Versions: the 0.1-0.2 route research inspected the `librus-apix` 1.5.2 URL
  definitions; later families and communication reviews used an installed,
  unmodified `librus-apix` 1.5.3.
- Sources: [client flow](https://github.com/RustySnek/librus-apix/blob/2fedfe8ffa4933abb884929716519ddbeb8eb32d/librus_apix/client.py)
  and the 1.5.3 distribution metadata homepage
  (https://github.com/poroknights/librus-apix).
- License evidence conflicts: the 1.5.3 metadata advertises MIT while its bundled
  license file is GPLv3. It is therefore treated as a requirements reference only.
- The pinned communication review is in
  [contracts/apix-communication-review.md](contracts/apix-communication-review.md).
- Offline comparison scripts (`compare_messages.py`, `compare_message_content.py`,
  `compare_notification_counts.py`, `compare_recipients.py` and
  `compare_send_acknowledgements.py`) replayed `librus-apix` pure parsers on
  private captures. Their results are recorded in this file and in
  `release-evidence/`; the scripts were removed in 0.6.1 and remain in Git history.

## 0.6.1 (2026-10-05) - Pre-1.0 readiness review

Offline review of security boundaries, OpenAPI parity, documentation accuracy and
packaging before 1.0 PyPI work. No public API, wire contract or storage change.

- Security boundaries hold: origins are pinned to official HTTPS hosts or
  loopback, TLS verification is mandatory, redirects are never followed
  automatically, environment proxies are ignored and the explicit proxy reaches
  every HTTP call site. XML decoding forbids DTDs, entities and network access;
  JSON decoding bounds nesting and rejects duplicate keys and non-finite numbers.
  Credentials are redacted in repr, str and validation errors.
- OpenAPI parity: all 50 catalogue operations (49 paths plus the explicit send
  variant) match method, path, side effect, retry safety, evidence and origin.
  One stale evidence note (received pagination) was corrected.
- Fixed: the unused `tenacity` dependency was removed, and `publish_attachment`
  now reports UNSUPPORTED_CAPABILITY instead of AttributeError where
  `O_DIRECTORY`/`O_NOFOLLOW` are missing; its regression failed before the fix.
- Source, installed wheel and installed sdist on Python 3.13.15 and 3.14.7 each
  pass 1,522 portable tests (one performance test deselected). Ruff, strict
  typing, hooks, history/worktree secret scans and the locked dependency audit
  pass; installed metadata no longer lists `tenacity`; archives rebuild with
  identical hashes. Archives are in `dist/0.6.1/`; hashes are in
  `release-evidence/0.6.1-readiness-qualification.json`.

Zero live Librus requests, credentials or sends. Nothing was published.

## 0.6.0 release preparation (2026-10-04)

The pre-merge compatibility review found that required `normalized_fields`
constructor arguments would break callers constructing detail results. The new
metadata now defaults to `()` and is excluded from equality/hash comparisons.
All three public detail workflow cases failed with the original constructor
calls before this correction and passed afterward, including equality/hash
comparison to populated service results. Existing calls and raw fields remain
available. Additive dataclass serialization keys, optional window boundary
annotations and stricter malformed-response rejection are documented in the
changelog; exact-schema serialization remains the consumer's responsibility.

Updated package, OpenAPI and release documentation to 0.6.0. Local Python 3.14.7
source suite: 1520 passed, one optional performance case deselected. Rebuilt
0.6.0 wheel/sdist and exercised each on Python 3.13.15 and 3.14.7: all five detail
workflow/regression cases and a standalone three-operation loopback smoke passed
in all four installed configurations. Verified import location, version/MIT
metadata, `py.typed` and dependency consistency. Ruff and strict mypy passed.
The full source/artifact CI matrix is a required merge gate for the final PR head.

Final 41-file source manifest SHA256:
`381b003fcd52cd83192b6fccac5f9741a0df74c15e4a4818278e33c69695805d`.
Disposable release builds and environments were removed. No PyPI publication,
consumer installation, new live access or production-state change is included.

## Native MCP 2.0 foundations (2026-10-04, before release preparation)

Reviewed all 18 consumer 2.0 roadmap items and changed the delivery plan to a
direct native MCP 2.0 cutover. The public review is
[contracts/mcp2-roadmap.md](contracts/mcp2-roadmap.md); consumer code and state
were not changed. No MCP 1.x wire-compatibility layer is required.

Added `DetailField`/`DetailFieldKey` and `normalized_fields` to school and
attendance details. Family-specific keys retain complete displayed values,
unknown labels and ancillary notes. Ambiguous attendance labels now fail before
public result/cache publication. The initial three workflow cases and known-label
ambiguity regression failed before implementation. The final five original
loopback cases also cover unknown-label ambiguity and recovery without a cached
failed result; existing parser cases retain ownership of structural limits.

Executed on Linux:

| Python | Source | Installed wheel | Installed sdist |
| --- | --- | --- | --- |
| 3.13.15 | 1520 passed | 1520 passed | 1520 passed |
| 3.14.7 | 1520 passed | 1520 passed | 1520 passed |

One optional hardware-sensitive performance case was deselected per run. The
portable suite includes existing representative concurrency, queue, rate and
fault-load checks. Each of the four installed-artifact runs additionally exercised
three native detail operations through real loopback HTTP in a standalone runtime
smoke. Installed import location, version/MIT metadata, `py.typed` and dependency
consistency were checked. Ruff, formatting, strict mypy, repository hooks,
worktree/history secret scans and hash-locked dependency audit passed. The audit
reported no known vulnerabilities.

The tested 41-file source manifest SHA256 is
`7a733ef4867505e17372ca3553492f3836ce200ad0685be1dd2e0f2434e4b980`,
using the algorithm documented below. Later documentation edits do not change
this implementation manifest. Disposable artifacts used the existing 0.5.0
metadata; nothing was published or installed into MCP. Task-owned builds, test
environments and temporary files were cleaned. No live Librus calls were made;
existing send uncertainty and notification state were not opened or changed.

## Post-0.5 cutover review (2026-10-04, unreleased)

PR #15 was already merged. GitHub confirmed the merge and remote main at
`7c9f4b7604f93ecb031963cc9cfb41483c44440a`. The new work is on
`feat/0.6.0-cutover-contracts-security`; this entry is offline development
evidence, not a released 0.6.0 package or completed consumer migration.

Compared all 28 MCP async tool signatures and their output models, including
optional tools, against the public library. The default-branch and opt-in adapter
revisions, per-tool mappings and unresolved schema decisions are recorded in
[contracts/mcp-cutover-review.md](contracts/mcp-cutover-review.md).
[contracts/api-security-review.md](contracts/api-security-review.md) records the
Snyk-guided security control map and service/repository/unit-of-work assessment.

Implemented:

- Bounded monthly homework aggregation with a typed request, original shared
  budget, reference-aware deduplication and no partial result/cache publication.
- Optional date boundaries and explicit upstream views for grade/attendance
  windows, with a maximum 370-day difference and retained response view.
- Strict rejection of non-finite JSON constants and overflowing decoded floats.
  Four otherwise-valid identity cases failed before the fix and passed after it.
- Additional original sent and empty-file modern attachment publication cases.
  Existing tests own view/cache semantics; new workflow tests own calendar
  boundaries, account isolation, budgets, conflicts and partial-failure behavior.

Executed on Linux:

| Python | Source | Installed wheel | Installed sdist |
| --- | --- | --- | --- |
| 3.13.15 | 1515 passed | 1515 passed | 1515 passed |
| 3.14.7 | 1515 passed | 1515 passed | 1515 passed |

One optional hardware-sensitive performance test was deselected in every run.
The portable suite includes multi-account queue/rate/concurrency and fault-load
checks, not just quiet-window observations. All four installed environments also
ran a standalone runtime smoke: `homework_range`, last-login `grades_window` and
weekly `attendance_window`, with 14 real loopback requests per smoke. Imports
were asserted inside each installed environment, and MIT metadata, version,
`py.typed` and installed dependency consistency were checked.

Ruff, format check, strict mypy, repository hooks (including the new files),
worktree/history secret scans and the hash-locked dependency audit passed.
The audit reported no known vulnerabilities; no Snyk SaaS scan was run.

The 40 source Python files identify the tested implementation through SHA256
`7e8ea07992795659c0d08590169467d1da559229b8b279903fc67a99b4e3b78e`.
This is SHA256 of UTF-8 JSON mapping sorted repository-relative `src/**/*.py`
paths to file SHA256 values, serialized with sorted keys and compact separators.
The disposable builds retained the existing 0.5.0 metadata because this is an
unreleased branch; they are not replacements for the qualified 0.5.0 archives.
Builds, test environments and task-owned temporary files were cleaned.

No live Librus calls were made. Populated behaviour notes and observation-card
contracts remain unavailable, so neither public parser is implemented by
guessing. Populated completed-lessons, other school/layout qualification and
disposable read-once tests remain deferred. The original send history and its
duplicate-prevention guard were not opened or changed.

## PR #15 pre-merge review (2026-10-04)

Reviewed the branch diff against `main`: authentication and send boundaries,
modern directory/mailbox/content parsing, attachment resolution and publication,
session/cache isolation, public models, capture diagnostics, tests, OpenAPI and
the release/API/contract documentation. Review and regression calls were offline;
all authenticated live scopes remain closed. Existing UNKNOWN send history and
consumer state were not opened or changed.

Findings fixed, in priority order:

- **Safety, TigerStyle #6: Positive and negative space.**
  `modern_body.py` failed to recognize XML wrappers after a BOM or inert preamble.
  The HTML fallback silently lost CDATA, included wrapper metadata as body text
  and accepted duplicate Content elements. Recognize the XML prefix and retain
  strict parsing. Reject non-UTF-8 declarations instead of silently misdecoding
  the already UTF-8-decoded message. Six new public HTTP regression cases failed
  before correction; the existing plain/HTML/XML cases still pass.
- **Safety, TigerStyle #12: Full error handling.**
  `encode_modern_send` used an unchecked recipient type as a dictionary key.
  A malformed list-valued type leaked `TypeError` rather than `InvalidInputError`.
  Validate its type before lookup; the existing preparation parameter table now
  proves the typed error and zero network calls, failing before the fix.
- **DX, TigerStyle #3: Assertions.**
  `parse_modern_types` rejected the supported combined `parents,guardians` type.
  Permit exact allowlisted identifiers before applying the simple-name pattern;
  arbitrary compound selectors remain unsupported. The new public discovery-to-
  lookup regression failed before the fix and checks the exact wire selection.
- The active-HTML negative test previously failed at an inconsistent attachment
  flag before reaching the body guard. Its fixture now reaches that guard and
  requires `UNSUPPORTED_CAPABILITY` specifically.
- README still reported 0.4.11, TODO called 0.5 planned, and several current-tense
  notes described superseded qualification gates. Synchronize release status and
  historical checkpoints, keeping C01-C05 open. OpenAPI and route evidence now
  reflect the existing closed inbox/outbox and employee observations, with explicit
  limits on which layouts/selections were observed. No new route was enabled.

The corrected source suite passes **1,495 tests, one performance case deselected**.
It includes real loopback HTTP, four-login shared-queue saturation, stream/file
publication, cancellation, send uncertainty and SQLite/process tests, not just
mocked parser results. OpenAPI validation checks every enabled path/method and its
side-effect/retry/evidence metadata. Exact final source/wheel/sdist matrix, runtime
smoke, hashes and static/security results are recorded in
`release-evidence/0.5.0-pr15-review-qualification.json`. Review fixes have no new
live qualification; earlier live manifests and archives remain historical.

## External communication gap review (2026-10-04)

Reviewed the latest published `librus-apix` 1.5.3 and pinned source revision
`2fedfe8ffa4933abb884929716519ddbeb8eb32d`, also its `v1.5.3` tag. SHA256 checks
established that the published wheel's messaging, route and client modules are
byte-identical to that source. The package entry point, messaging documentation,
README and metadata/license were reviewed as supporting evidence. The MIT
metadata/GPLv3 license conflict persists. No external code was executed or
installed; the wheel was inspected in memory without extraction or retention.
No code, tests, documentation or fixtures were copied.

The external client has legacy HTML messaging only. Virtual selection is fixed
off, subgroup lookup fixes selection to zero, and there is no dedicated archive,
withdrawn-original, expanded/CC/BCC receipt or attachment stream implementation.
Its sent `unread` comparison is not reliable delivery evidence. No additional
gap-closing logic was established, so runtime behavior and tests are unchanged.
The review and hashes are recorded in `contracts/apix-communication-review.md`
and `release-evidence/0.5-apix-communication-review.json`.

Remaining work is explicitly separated as TODO C01-C05: unsupported independent
delivery semantics; unavailable virtual/class-parent and subgroup live data;
archive list/detail navigation contracts and archive/original live layouts; and
expanded/CC/BCC receipt live layouts. Existing independently authored offline
support remains available. No new live Librus request, credential submission,
send, history/guard change, consumer migration, merge or publication occurred.
Previously qualified implementation archives remain unchanged. This is a
documentation-only continuation on PR #15, not new live or artifact qualification.
Post-review source tests pass: **1,487 tests, one performance case deselected**.
Ruff lint/format, repository hooks and diff checks pass. The Python manifest still
matches the qualified implementation snapshot recorded below; no runtime or test
changes are inferred from the external comparison. Current-head remote CI is
checked separately on PR #15.

## Modern download, receipt and layout expansion (2026-10-04)

The latest same-PR implementation is `5318757`, still version 0.5.0. It adds
explicit modern/archive attachment resolution, credential-free bounded streams,
recipient read/null/unknown observations, plain/HTML/XML body support and inert
original/withdrawal metadata. Independent delivery acknowledgement remains unknown.
The original durable UNKNOWN history/duplicate guard and consumer are unchanged.

Two public contract-inspection scopes and four fresh authenticated scopes are
closed. The authenticated inventory used four separate login security contexts;
none exposed class-parent/virtual branches or populated legacy subgroups. It
qualified empty student outboxes and a populated second sent page at size five.
Dedicated content inspection then established the actual detail/resolver shapes.
The first candidate stream stopped at its approved 5 MiB ceiling without saving
partial bytes. A separately approved remaining-check scope qualified another
complete stream of 7,004,902 bytes, ordinary plain/XML content, recipient read/null
observations and one explicitly consented unread-to-read transition confirmed by
before/after mailbox read timestamps. No new sends or read-once event calls.

Total authenticated expansion traffic: 136 requests, eight credential submissions,
12,623,091 response bytes; nine content opens, four resolver calls, two stream
attempts and one complete stream. Only one previously-unread message was opened,
with explicit approval. Every scope stopped on its first failure or completed,
then closed without an automatic rerun. No bodies, attachment payloads, private
response captures or signed URLs were retained. Sanitized evidence is in
`release-evidence/0.5-communication-expansion-scopes.json`.

The 36 original new regressions exercise real isolated HTTP origins, strict
resolver routes and destinations, cookie/header isolation, shared four-account
queue saturation, explicit archive references, consent/content parsing, XML
entity/duplicate/nested-element rejection, ambiguous receipt failures, byte/request
budgets, deadlines, cancellation and actual local-file publication. Legacy stream
and file tests also pass, protecting the shared worker without duplicating all
lifetime tests in the modern subclass. The initial eight detail regressions failed
on the old parser before their fix. A fixture initially expected the viewer path
rather than the independently established `/get` byte route; that was corrected
offline, with no production route guessing.

Final source, installed wheel and installed sdist each pass **1,487 tests, one
performance case deselected**, on Python 3.13.15 and 3.14.7. Installed suites use
tests/scripts/contracts from the actual sdist and prove installed imports,
version/MIT license/Python floor/`py.typed`, compatible dependencies and runtime
smoke behavior. Two builds produced byte-identical archives:

- Wheel SHA256: `0b58d60115d12d44c9bfb9f0d632c47eb29ac45cdc0d4c4c8a5ac4bd89841073`.
- Sdist SHA256: `90256b23c5f2de08a15a28c7d1a7204b9c01439155463c6b876e42d38bf4801f`.
- Final Python manifest:
  `87036e160f21318a60715984e9d7d5cb826f326940a946cd5dec4fa99689efee`.

Only content endpoint evidence metadata changed after the live candidate snapshot;
no runtime/parser/stream behavior changed. Live scopes qualify source API calls,
not an installed authenticated run. Ruff lint/format, strict mypy, repository hooks,
history secret scan, locked dependency audit and lock validation pass. Qualified
artifacts and XML reports are retained in `dist/0.5.0-communication-expansion/`;
all earlier qualified artifact directories are unchanged. This section supersedes
older verification text bundled in that sdist. Machine-readable package evidence:
`release-evidence/0.5.0-communication-expansion-qualification.json`.

Remaining live gates require suitable data and fresh authorization: class-parent,
virtual/class selections, populated legacy subgroups, archived/withdrawn originals
and expanded/CC/BCC receipt rosters. Independent delivery acknowledgements remain
unsupported by the established contract. Consumer integration, merge and
publication remain separate gates. Current pushed-head remote CI is tracked in
PR #15, separately from these local implementation archive hashes.

## Compatibility continuation (2026-10-04) - Locally qualified for PR #15

The owner authorized additional library compatibility work on the same branch
and PR #15, in separate scoped commits. Consumer migration, sends, event
consumption, merge and publication are not part of this continuation.

The optional local attachment publication boundary adds 15 original tests.
Its combined stream/file suite passes 83 tests; the final full source suite passes
1,451 tests with one opt-in performance case deselected. Ruff and strict mypy
pass. The tests exercise real loopback HTTP, four concurrent account streams,
non-overwriting symlink/file collisions, interrupted reads, byte ceilings,
redacted disk failures and repeated cancellation while a real disk worker runs.
This is offline local-file qualification, not new upstream attachment evidence.
The continuation also adds bounded modern mailbox collection, consent-gated
content parsing and inert attachment metadata, broader recipient directory routes
and opt-in virtual query selection. Four-account mailbox queue saturation, account
cookie/reference isolation, continuation drift, failed later pages, deadlines and
cancellation are exercised through real loopback HTTP. Review retained explicit
unknown sent read status, strict inbox read fields, bounded inert availability
JSON and non-overwriting local-file commit/cancellation semantics. Modern download
destinations and richer receipt layouts are deliberately not guessed.

Four separately approved public-asset scopes are closed: two root/index scopes
used two GETs and 827,129 bytes each; the linked app scope used one GET and
1,129,914 bytes; targeted app inspection used one more GET of the same size.
No credentials, cookies, redirects, script execution or writes.
The first diagnostic skipped the index filename; the second established the
linked app dependency; the third established source-informed inbox/outbox list,
detail and attachment-resolution routes. Public source is an external behavior
reference, not code or fixtures to copy and not authenticated live evidence.
No app bundle is incorporated in this repository.

Three additional authenticated scopes used 48 requests, three credential
submissions and 125,247 response bytes, with zero content, attachment, download,
send or read-once calls. Each stopped on failure or completed, then closed without
automatic rerun. The first reporter error and second outbox layout error have
original regressions; the third scope succeeded. Candidate source API observations
qualify populated inbox pages 1-2, outbox page 1, teacher/tutor/school-admin/council
branches and legacy groups with an empty subgroup selector on one account.
Class-parent and populated legacy-subgroup evidence were unavailable. Live hashes
identify observed source snapshots; subsequent availability JSON hardening was
offline-qualified only. See `contracts/modern-communication.md` and
`release-evidence/0.5-communication-scopes.json`. No installed live check is claimed.

Implementation commits are separate: `ddc8397` for optional local files and
`d18e3f2` for modern communication. Version stays 0.5.0 on the still-open PR.
The actual final implementation source, installed wheel and installed sdist each
pass **1,451 tests, one performance case deselected**, on both Python 3.13.15 and
3.14.7. Installed imports, metadata/version, MIT license, Python floor, `py.typed`,
dependency compatibility and runtime smoke checks pass. Installed suites use
tests/scripts/contracts extracted from the actual sdist, not copied upstream
fixtures, with an empty disposable `.git` marker for capture safety checks.
Two builds produce byte-identical archives. The first build diagnostic counted
uv's generated `.gitignore` as a distribution; correcting that file-selection
check confirmed identical wheel and sdist hashes without a production change.

- Wheel SHA256: `04496413371684dc3b3e57b0a76a383b72869ae675ad3bdb0ef9b738baa3380e`.
- Sdist SHA256: `c8f5ac164b4f6d9c7caff74646f373f5acaaee6fe05b510baf90929a078e1207`.
- Final implementation Python manifest:
  `3ceeb3f611b594160d19d3f40f1e1c96a40de4e61f6c2a3152a618191154b986`.

Artifacts and local XML reports are retained separately in
`dist/0.5.0-communication-continuation/`; prior `dist/0.5.0/` archives are unchanged.
This final verification text supersedes pending text inside the qualified sdist.
Machine-readable evidence: `release-evidence/0.5.0-communication-qualification.json`.
Ruff lint/format, strict typing, hooks, history secret scan, locked dependency
audit and `uv lock --check` pass. Current-head remote CI remains a separate gate.
No consumer installation, state migration, merge or publication occurred.

## 0.5.0 (2026-10-04) - Modern authentication and sole-send qualification

The implementation is committed separately from the 0.5.0 version/qualification
increment. Earlier 0.4.11-version candidates are historical; their hashes do not
identify 0.5.0. The main 0.4.11 release hashes below remain unchanged. This is a
local-first delivery, not PyPI publication or a production consumer installation.
Review and closed-scope evidence are in
`contracts/modern-launch-diagnostics.md` and `release-evidence/0.5-modern-*`.

- Seven separately approved scopes used 84 HTTP requests, seven credential
  submissions and exactly one sole-recipient modern send. All scopes are closed.
  No retry/fallback/additional recipient, read-once call, content open, attachment,
  setting change, consumer migration or publication occurred.
- Live launch namespaces varied between calls. The owner approved a bounded
  server-selected numbered field; origin/login/token/target/source/terminal
  guards remain. Original regressions failed before the namespace fix.
- Modern identity returned integer accountId, independently compared against
  native owner/name. Identity-only normalization fixes the original PARSE
  regression; directory IDs remain strict. Installed sender/council verification
  passed for one context; universal roles/layouts remain unqualified.
- The one dispatch used native durable persistence and returned HTTP 201 with
  exact created/sent JSON. The owner independently confirmed the exact sent
  recipient/subject/body in the official UI. Recipient reading is not confirmed.
  The original API/durable result remains UNKNOWN/PARSE, preserved rather than
  automatically rewritten. A new narrow receipt-parser correction is qualified
  offline, not through another live send.
- Source, installed wheel and installed sdist each pass 1,385 portable tests on
  Python 3.13.15 and 3.14.7, one performance test deselected. Installed imports and
  the qualified receipt smoke are checked in each environment; two builds have
  identical wheel/sdist bytes. Ruff lint/format, strict typing, changed-file hooks
  and worktree secret scan pass. Final evidence:
  `release-evidence/0.5-modern-ack-offline-candidate.json` records the pre-version
  candidate. The 0.5.0 artifacts require their own qualification below. Earlier
  1,326/1,353/1,366 candidate evidence remains historical, not final acceptance.
- Scratch environments/builds are removed. The explicitly approved owner-only
  durable send history and one bounded receipt are retained outside Git for
  duplicate prevention/manual reconciliation. Private IDs, bodies, cookies,
  credentials and screenshots are absent from public evidence.
  The new approved claim directory contains a 20,480-byte SQLite file and a
  149-byte receipt (20,629 bytes total). The existing private approval ledger was
  updated, not reset or migrated. Nothing from these files enters Git.

Broader 0.5 compatibility, live rejection/alternate acknowledgement shapes,
modern mailbox/attachment support, read-once test-account qualification,
consumer migration, PR merge and publication gates remain open. Versioned 0.5.0
artifact qualification and current-head CI are recorded separately, not inferred
from the pre-version candidate checks.

### Versioned local artifacts

The 0.5.0 source, installed wheel and installed sdist each pass 1,385 tests on
Python 3.13.15 and 3.14.7, one opt-in performance case deselected. Each installed
environment verifies import location, version, MIT license/files, Python floor,
`py.typed`, dependency compatibility and the qualified receipt smoke. The suite
includes real loopback/runtime, durable/process and maximum-payload load proofs.
Two builds have byte-identical archives. Ruff lint/format, strict typing, repository
hooks, history/worktree secret scans and the locked dependency audit pass.

New local artifacts in `dist/0.5.0/`: wheel 119,164 bytes, sdist 518,137 bytes,
637,301 bytes total. Hashes and commands/results are recorded in
`release-evidence/0.5.0-modern-qualification.json`. The archives contain a
pre-final-evidence documentation checkpoint; this final log supersedes pending
qualification wording inside the sdist. Older `dist/0.4.11/` artifacts are unchanged.
Disposable environments/builds are removed; only the new versioned archives are
retained locally. No extra live requests, sends, history rewrites or publication
were performed during packaging. Current-head PR CI is still a remote gate.

## 0.4.11 (2026-10-03) - Offline S10 storage and session follow-ups

Pre-merge independent review (supersedes the counts, hashes and size below):
the attachment destination check reported a foreign redirect carrying a query,
fragment, percent or backslash as UNSUPPORTED_CAPABILITY instead of ACCESS_DENIED.
The reorder in `2aa756f` has seven foreign-destination regressions that failed
before it. Source, installed wheel and installed sdist on Python 3.13.15 and
3.14.7 each pass 1,302 portable cases (one performance case deselected). Ruff,
strict typing, hooks, history/worktree secret scans and the locked dependency audit
pass; archives rebuild with identical hashes. Re-qualified archives in
`dist/0.4.11/` total 621,242 bytes; the evidence file carries the new hashes.
No other defects were found; see `contracts/review-followups.md`. All traffic
stayed on loopback with zero live Librus requests.

The original pre-review record follows.

Implementation is committed in separate storage, modern-session and edge-case
slices after the remotely confirmed PR #13 merge. Pre/post review, retention
trade-offs and regressions are recorded in `contracts/review-followups.md`.
Source, installed wheel and installed sdist on Python 3.13.15 and 3.14.7 each
pass 1,291 portable cases with one performance case deselected. Ruff lint/format,
strict typing, all repository hooks, history secret scan and locked dependency
audit pass, including representative multi-account and real process proofs.
Ten repeated concurrent modern-send cases pass with one shared handoff, two fresh
preflights and no replay. No independent agent/model review is claimed.

Installed import locations, version/MIT/license/py.typed metadata and dependency
compatibility checks pass. Both archives rebuild with identical hashes. Qualified
archives are retained in `dist/0.4.11/` (620,140 bytes); sanitized hashes and results
are in `release-evidence/0.4.11-s10-qualification.json`. Disposable databases,
virtualenvs, reports and worker processes were cleaned. Archives contain the
pre-final-evidence documentation checkpoint; this final record supersedes its
pending installed gates. Current-head remote CI remains a separate PR gate.

No live Librus traffic, credential
submission, sends, read-once consumes, MCP code or production-state changes,
merge or publication. The version-2 storage refusal is intentional; no silent
migration/reset. Remaining 0.5 authentication/coverage/live/consumer gates are open.

## 0.4.10 (2026-10-03) - PR #13 review hardening

Final offline source and installed-artifact qualification:

- Four independent agent reviewers covered transport/service/catalogue parity,
  parsers and send acknowledgements against librus-apix 1.5.3 behaviour (read
  only, nothing copied), durable storage, and test value plus capture-script
  safety. No Critical finding. Fixed: post-consume checkpoint loss under another
  context's write lock, post-dispatch outcome loss under contention, capture
  transports able to send or consume, the legacy banner hiding send
  acknowledgements, read-state cursor drift, archive cursor skipping, LIMIT after
  a claim, fail-open aiohttp replay switch and missing concurrency/destination
  tests. Nine lower-priority findings are tracked as TODO S10.
- Every fix has a regression that failed before the change (listed in the
  evidence file); real SQLite write locks are held from a second connection.
- Source, installed wheel and installed sdist on Python 3.13.15 and 3.14.7 each
  pass 1,253 portable tests (one performance test deselected). Ruff lint/format,
  strict typing, repository hooks, history and worktree secret scans and the
  locked dependency audit pass. Archives rebuild with identical hashes.
- Route paths and form fields for lists, recipients and legacy sending match the
  reference library; this repository is stricter on unknown notices, counters
  and acknowledgement text. No browser or live trace was needed: no finding
  depended on unobserved upstream behaviour.

Qualified local archives are in `dist/0.4.10/`; sanitized hashes and results are
in `release-evidence/0.4.10-review-qualification.json`. All HTTP traffic was
loopback: zero live Librus requests, credentials, sends or read-once consumes.

## 0.4.9 (2026-10-03) - Optional durable notifications

Final offline source and installed-artifact qualification:

- Explicit optional native `NotificationStore`/`NotificationWorkflow`, separate
  private SQLite database, no core storage requirement and no MCP implementation
  or production-state changes. Independently authored code and original fixtures.
- Source, installed wheel and installed sdist on Python 3.13.15 and 3.14.7 each
  pass 1,235 portable tests (one performance test deselected). Ruff lint/format,
  strict typing, repository hooks, history secret scan and locked dependency audit
  pass. Installed imports resolve inside each environment; version/MIT metadata,
  license files, `py.typed` and dependency compatibility checks pass. Fifty new notification
  cases exercise actual public-native loopback and real disposable SQLite.
- Durable raw encoded bodies/metadata precede parsing; malformed markup, MIME,
  gzip and coding stay retained. An uncertain pre-checkpoint marker blocks fresh
  consume until explicit possible-loss acceptance. No upstream replay is inferred.
- Staged delivery replays without HTTP until explicit acknowledgement atomically
  commits seen IDs and cursor/cleanup. First-run, category selection and ordinary
  category failures are exercised, including all six native categories. No count
  menu, content-mark-read or hidden detail requests are made by the workflow.
- Real competing processes refuse the second same-context consume. Process loss
  during partial receipt, after checkpoint/staging and after acknowledgement
  preserves marker/raw/delivery/committed state respectively. Restart drains local
  bytes without another login or read-once request.
- Real worker faults before/after checkpoint, staging and acknowledgement plus
  repeated cancellation/shutdown join owned saves. Candidate seen-state overflow
  preserves raw data and recovers with explicitly larger supported limits.
- Representative load: four independent logins each deliver/acknowledge 1,024
  distinct events under one exact 24-request budget. Four MiB encoded raw receipt
  is retained at the accepted wire bound; shared checkpoint capacity refuses the
  next consume. Byte/event slices, 1,024 duplicate rows and workflow saturation
  remain bounded with no silent data eviction or owned active/queued requests.
- Neutral archive round trips include pending delivery/progress. Invalid version,
  exact context, bytes, count, old IDs and staged-event omission reject atomically.
  The omission regression failed before comparing imported cursor coverage with
  the retained envelope, then passes after the fix. Empty/seen-only context binding
  is covered too. Private archives are neither encrypted nor authenticated.
- A last-committed receipt retry initially failed when a newer batch was staged.
  The regression now passes, leaving the newer delivery intact and unacknowledged.
- Send store schema and qualified bytes remain unchanged across notification use;
  all 44 existing send persistence cases pass after extracting shared private
  SQLite ownership. Extra schema, raw corruption and lock symlinks fail closed.
- Pair-programmer self-review: TigerStyle #2 bounded work, #4 paired validation,
  #6 unsupported states and #12 joined failure handling. No independent agent
  review is claimed. No new HTML/UI layout, route or parser contract changes;
  existing independent same-byte/browser evidence retains its original scope.

Qualified local archives in `dist/0.4.9/` total 593,555 bytes; sanitized hashes
and results are in `release-evidence/0.4.9-notification-qualification.json`. Their
documentation captures the source checkpoint; this final log supersedes its
pending installed gate. Task-owned environments, databases, workers and scratch
were cleaned. All new HTTP traffic was loopback: zero live Librus requests, credentials
or sends. POSIX context locks do not coordinate global traffic across independent
processes. Delivery is at-least-once, not exactly-once or historical catch-up.
Modern authentication, broader coverage and live qualification remain in the 0.5
TODO. MCP mapping/migration, credentialed CI, merge and publication remain gated.

## 0.4.8 (2026-10-03) - Optional durable send workflows, offline qualification

The superseding ownership decision puts reusable durable workflows in the API's
explicit optional layer. MCP configuration, human approval, tool schemas and wire
mapping stay in its separate repository; adapter implementation happens when
migrating that repository from `librus-apix`. No MCP code/default backend or
production state is changed by this slice. Earlier consumer-owned roadmap text
below is historical and superseded by [contracts/persistence.md](contracts/persistence.md).

- Independently authored SQLite schema, storage implementation and original
  fixtures; no GPL consumer helpers or upstream material transferred.
- Source and installed wheel/sdist on Python 3.13.15/3.14.7: each 1,185 passed,
  one opt-in performance case deselected. Ruff lint/format, strict typing,
  repository hooks and locked dependency audit pass. Installed imports resolve
  inside their own environments; version/MIT metadata, license files, dependency
  compatibility and `py.typed` checks pass.
- Forty-four persistence cases use real disposable SQLite and public native
  attempts. Legacy acceptance/rejection/unknown/pre-dispatch outcomes and modern
  unknown/source-informed denial run through actual loopback HTTP, never live Librus.
- Real competing processes prove one dispatch with the same token and with
  different tokens for identical input. Killing the sender before credentials/send
  or after send receipt leaves a durable claim; history reports UNKNOWN and blocks new-token
  and duplicate-preview bypass. This is not exactly-once upstream delivery.
- Sixteen independent synthetic logins execute 64 full 50-recipient/200-subject/
  15,000-body messages at the maximum 64-worker/send admission, under one exact
  144-request service budget. All outcomes persist; no owned requests remain.
  A 4,096-record uncertain history is recoverable and refuses overflow without
  eviction. Real SQLite lock contention and worker saturation fail before HTTP.
- Repeated cancellation at claim, active send, final save and queued final save
  joins owned work; shutdown joins workers. Final-save failure retains a claimed
  UNKNOWN record even when the process-local result was ACCEPTED. Recovery works
  without plaintext tokens and never implicitly reconciles uncertainty.
- Pair-programmer self-review: TigerStyle #2 bounded work, #4 paired validation,
  #6 unsupported states and #12 complete failure handling. Original regressions
  failed before fixing extra-trigger acceptance, false-valued invalid limits,
  exact-deadline expiry and cancellation discarding a queued acknowledged save.
  They pass after the fixes. No independent agent review is claimed.
- Corrupt/unknown/altered schemas, symlinks, unsafe permissions and oversized
  files fail closed without resetting stored bytes. Credentials, message content,
  recipient labels and token plaintext are absent from the actual database.

No HTML/UI behavior or upstream wire layout changes in this slice; earlier same-
byte browser semantics remain scoped to their original contracts. Qualified local
archives in `dist/0.4.8/` total 554,187 bytes; sanitized hashes and results are in
`release-evidence/0.4.8-persistence-qualification.json`. Their documentation captures
the pre-artifact source checkpoint; this final log supersedes its pending gate.
Task-owned environments, databases, workers and other scratch are removed.
Notification storage/replay is the next separate slice;
manual reconciliation, MCP migration, live qualification, merge and publication
remain outside this delivery. No live requests, credential submissions or sends.

## 0.4.7 (2026-10-03) - Explicit modern messaging, offline qualification

### Scope and provenance

The approved follow-up adds modern identity/type/council discovery and an explicit
modern single-use JSON send API to PR #13. It does not alter settings or dispatch
the separately planned live message. Three separately approved unauthenticated
public-asset GETs completed with zero credential submissions, account data,
script execution or sends. The scope is closed with no automatic rerun. Prior
read-only modern identity/council observations remain evidence for one layout,
not live qualification of the new installed implementation.

The external app was inspected only as a behavior reference; no code, bundles,
private captures or external fixtures are incorporated. Original fixtures use
invented accounts and recipients on two loopback origins. No applicable modern
apix operation is used as an oracle or fallback. Ordinary CI remains offline.

### Qualification and review

- Source, installed wheel and installed sdist each pass 1,141 portable tests on
  Python 3.13.15 and 3.14.7; the one opt-in performance case remains deselected.
  Ruff lint/format, strict typing, hooks, secret scans, locked dependency audit
  and artifact metadata/license/py.typed checks pass.
- OpenAPI parity covers 42 operation IDs on 41 distinct method/path pairs.
  Six modern routes are centrally catalogued. Authentication redirects and
  send requests cannot be entered through the generic request interface.
- Eighty original modern cases exercise actual public prepare/execute and read
  paths across separate native/modern fixture origins. Cookie assertions exclude
  native tokens from modern requests and modern cookies from native requests;
  four independent logins sharing one synthetic student retain different owners.
- The exact JSON uses recipient account IDs, not user IDs, UTF-8 Base64 text,
  null attachment storage and normal category. Backend-specific references reject
  legacy/cross-account use before I/O. Single-use frozen outcomes retain the
  backend, native identity and observation after potential dispatch.
- Representative load includes four full 50-recipient/200-subject/15,000-body
  submissions under one exact 36-request budget and a 2,048-leaf directory read.
  The next leaf fails the bounded directory policy. Same-account distinct attempts
  share authentication but not send results; saturated shared admission dispatches
  no second send and leaves no owned active/queued work.
- Cancellation, deadline and shutdown are exercised during native launch,
  modern handoff, identity verification and send response waiting. Pre-dispatch
  failures retain NOT_DISPATCHED; potential dispatch retains UNKNOWN. Expiry,
  disconnect, partial EOF, redirects, wrong MIME and bounded-response failures
  never replay, switch backend or claim acceptance. Sent-list caches invalidate
  at potential dispatch while unrelated received summaries remain cached.
- Pair-programmer checklist self-review covered TigerStyle #2 bounded work,
  #6 unsupported states, #12 failure handling and #13 explicit transport defaults.
  It identified raw plain-text markup being interpreted as HTML by the modern
  reader. The exact-wire regression failed before HTML escaping, then passed
  after escaping body literals before UTF-8 Base64 encoding. No independent
  subagent review or universal upstream compatibility is claimed.
- `scripts/crosscheck_modern_messages.py` independently renders actual original
  loopback POST bytes in real offline Chromium. All three bodies, including
  Unicode, literal script/tag/entity text and CR/LF/CRLF, match plain-text intent.
  Networking and service workers are blocked; no external app code is executed.
  This is a source-informed reader-semantics check, not a full modern-app replay
  or proof of real server transformation. Prior captured-app directory replay
  remains qualified only as described in the modern contract.

### Retained artifacts and remaining gates

Qualified local archives are in `dist/0.4.7/`; sanitized hashes and results are
in `release-evidence/0.4.7*`. Task-owned assets, environments and logs are removed.
The private live plan remains owner-only and not authorized to send. Cumulative
approved discovery/asset scopes used 54 HTTP requests and four credential
submissions, with zero live sends; the new increment used only the three public
GETs. Unused older budgets do not authorize any further calls.

Modern HTTP success is UNKNOWN until a definitive positive acknowledgement is
independently established. Explicit validation denial envelopes are source-
informed only, not live-qualified. Installed live handoff/discovery, broader
roles/type/class layouts and the exact sole-recipient send still require fresh
bounded authorization. Modern mailbox content, attachments and reconciliation
remain unsupported. Consumer migration, credentialed CI, merge and publication
were not performed.

### Later expanded-0.4 installed verification and narrow diagnosis

The owner expanded the 0.4 delivery to include consumer-owned send/notification
persistence and ordered completion gates. Full consumer backend migration, live
sending, event consumption, merge and publication remain separately authorized.

Two new separately approved scopes each allowed one credential submission and
16 requests maximum. The installed qualified 0.4.7 wheel used ten requests in
each scope. The first verified native sender/student identity, then rejected the
modern launch redirect before a modern handoff or directory request. A separate
launch-only diagnosis verified native identity again and confirmed HTTP 302,
the expected HTTPS modern host, no query/fragment, and a ten-field path whose
fixed layout does not match the implemented contract. No token URL was retained.
The available redacted facts do not establish the replacement path literals;
guessing a route or loosening the allowlist is not justified.

Both scopes are closed with no rerun. There were zero modern handoffs, message
preparations/sends, content opens, downloads, setting changes or read-once calls.
S1 is blocked, not completed: the installed modern handoff/directory path is
still live-unqualified. Native authentication used nine requests in these
contexts, unlike the shorter synthetic fixture handshake. The strict boundary
stopped safely but exposed a real compatibility gap requiring independently
established redirect requirements and an original regression before a fix.

Cumulative approved discovery/asset/verification scopes now total 74 HTTP
requests and six credential submissions, with zero sends. Only sanitized facts
are retained in `release-evidence/0.4.7-installed-modern-qualification.json`.
Task-owned private identity captures and diagnostic runners are removed after
inspection; older qualified archives are unchanged.

## 0.4.6 (2026-10-03) - Single-use sending, offline only

### Design, scope and evidence boundary

Owner-approved single-use attempts freeze validated payloads locally and retain
inspectable outcomes across cancellation. This is the final library increment
in the original PR #13 sequence, later extended by 0.4.7. Implementation approval
did not authorize live discovery or sending:
zero Librus requests and zero live send dispatches were made in this increment.
The privately recorded one-recipient/one-message/one-dispatch qualification plan
still requires exact sender/recipient/payload verification and fresh bounded
approval. No group, extra, substitute or fallback recipient is allowed.

The legacy send form and acknowledgement placement are source-informed, not
independently observed live. Apix 1.5.3 remains a business reference only; no code
or fixtures were copied. Public fixtures contain invented messages and IDs.
Library acceptance does not prove delivery/read state, and no upstream
idempotency or durable-outbox guarantee is claimed.

### Offline qualification and review

- Source, final installed wheel and final installed sdist each pass 1,061 tests
  on Python 3.13.15 and 3.14.7; one opt-in performance case is deselected. Lint,
  formatting, strict typing, hooks, worktree/history secret scans and locked
  dependency audit pass. Built metadata, MIT license and py.typed are checked.
- Route parity covers 36 explicit operation IDs on 35 distinct method/path
  pairs. Sending is an explicit, independently validated OpenAPI request variant
  on the sent-list URL, not an implicit catalogue alias. Missing/duplicate
  variants, policy drift and invalid variant schemas fail validation. Generic
  request cannot enter the send variant; pagination still permits only its own
  exact two fields. No new arbitrary authenticated URL or form interface.
- The public preparation/execute path proves exact repeated DoKogo fields and
  fixed form values, preserved Unicode/line endings/order, immutable payloads,
  field/count/control validation and a whole encoded-form byte boundary. Limits
  are library policy, not observed upstream maxima. Distinct attempts do not
  coalesce or reuse a send result; repeated/concurrent execution of the same
  attempt cannot dispatch again.
- Real loopback boundaries cover authentication, account-lock waiting, shared
  scheduler waiting and HTTP dispatch. Cancellation, timeout and service shutdown
  before dispatch retain NOT_DISPATCHED; after dispatch they retain UNKNOWN.
  Joined completion prevents orphaned work, and terminal ACCEPTED/REJECTED
  snapshots survive cancellation at worker completion. Closed service, invalid
  budgets, exhausted auth/request budgets, denied credentials and saturated
  operation/queue admission never falsely mark dispatch.
- Disconnects before acknowledgement, partial response EOF, redirects, HTTP
  errors, wrong MIME types, encoded response limits, parser-input limits and
  response budgets never produce success or a retry. Session expiry invalidates
  authentication without resubmitting credentials or sending again. Unknown and
  contradictory markers remain uncertain; exact negative wording is not matched
  as a positive substring. No sent-folder similarity heuristic is implemented.
- Cache proofs invalidate sent-page and sent-batch results at potential dispatch,
  including an unknown acknowledgement, without needlessly clearing received
  summaries. Custom transport failures keep dispatch state and redact private
  exception text/causes and diagnostics. Custom transports must uphold the
  library-owned dispatch callback boundary; their actual network actions cannot
  be independently inferred by the service.
- Four isolated accounts representing the same synthetic student each submit a
  maximum 50-recipient, 200-character subject, 15,000-character body under one
  exact 24-request shared budget, with no account/session merging. These are
  loopback fixtures, not permission to contact any additional live recipient.
- Pair-programmer checklist self-review checked TigerStyle #2 bounded work,
  #6 unsupported/negative space, #12 full failure handling and #13 explicit
  transport defaults. It found that acknowledgement markup quoted inside a
  message body could be mistaken for acceptance. An original regression failed
  before the parser rejected message-content containers, then passed after the
  correction. No independent subagent approval is claimed.
- An optional inert apix comparison and real Chromium render use identical bytes
  from three original acknowledgement fixtures, with scripts/networking disabled.
  Native classifies accepted/rejected/unknown as designed; apix returns false for
  all three, including the positive marker. This is a classified semantic
  difference, not a fallback or live qualification. All final artifact suites
  exercise actual installed public API loopback writes and their fault paths.

### Retained artifacts and remaining gates

Only sanitized `release-evidence/0.4.6*` and qualified local wheel/sdist archives
in `dist/0.4.6/` are retained. Task-owned build/qualification environments and
logs are deleted. No private live captures were created, and no message was sent.

Live form compatibility, exact acknowledgement wording/placement and the
single-recipient manual qualification remain pending. A missing/unknown success
marker must not be broadened by guessing. Sender identity/recipient resolution
and a fresh live budget remain required; the prior 0.4.5 allowance is exhausted.
Consumer preview/confirmation, persistent attempts, crash recovery and manual
reconciliation remain consumer-owned and separately authorized. MCP migration,
credentialed CI, PR merge and PyPI publication were not performed.

### Later recipient-only verification (2026-10-03)

After implementation, the owner separately approved two bounded verification
contexts on one selected login, with per-context ceilings of 32 and 16 requests
and one credential submission each. The installed qualified 0.4.6 wheel used
10 and 11 requests respectively. Both verified the same sender identity.
No send attempt was prepared or executed, and no mailbox content, downloads,
settings changes, deletes or read-once requests occurred. These were recipient
discovery scopes, not live qualification of the send form or acknowledgement.

The first context stopped because the privately specified directory caption
did not exactly match either available council selector. Independent Chromium
checked all eight displayed type labels on those same bytes. The owner then
clarified the class-council selector and approved a fresh context. Its sole
lookup returned the exact class-unavailable notice and no recipient labels,
independently confirmed with Chromium scripts/networking disabled. The installed
API returned UnsupportedCapabilityError, not an empty recipient success.

The response does not establish that the represented student actually lacks a
class; it establishes that this legacy selector/form did not resolve the intended
class-qualified recipient. No numeric ID or class path was guessed. Unknown
class/virtual-class selection remains a gap, and no alternative account, council
or recipient was substituted. Unused requests authorize no rerun or widened scope.
The two scopes total 21 requests and zero sends. Raw pages and temporary runner/
wheel environments were deleted. Essential sender checks and the unresolved
single-recipient plan remain in private owner-only state outside Git; only
sanitized accounting is retained here and in the release-evidence sidecar.

The owner then separately approved discovery on the corresponding student login,
with a fresh 16-request ceiling, one credential submission and one class-council
lookup. The installed wheel verified that independent account identity and used
11 requests. The lookup again returned the explicit class-unavailable notice,
with no recipient labels, independently checked in offline Chromium. This was
an authorized discovery-context change, not a change of sender or permission to
reuse another account's references. No recipient ID or class path was resolved,
and no send attempt was prepared or executed. All three scopes total 32 requests
and three credential submissions, with zero sends. The third task's private
capture, runner and installed-wheel environment were deleted after recording
the essential unresolved state privately. Further discovery needs fresh scope;
no guessed form, alternate council or recipient is authorized by unused budget.

### Later modern-composer investigation (2026-10-03)

User-provided screenshots established that the intended directory is available
in the modern messaging module, while the legacy selector remained unavailable.
The owner separately approved one fresh original-sender context, capped at 32
requests for authentication, composer assets and recipient discovery only, with
no sending or settings changes. The isolated installed-wheel investigation used
one credential submission and 19 requests. Native authentication/identity and
all staged modern requests shared the native scheduler and one request/byte/
deadline budget; reviewed redirects were separate explicit dispatches.

The modern account identity matched the previously verified native owner. The
modern types response and one council branch resolved the intended class and
sole recipient uniquely, with distinct recipient account/user ID fields. The
session was then closed. No modern ID was cast to a legacy recipient reference,
and no send attempt was prepared or executed. All four separately approved
contexts total 51 requests, four credential submissions and zero sends.

Offline Chromium rendered the exact captured modern app bundles and directory
response bytes, with all network requests intercepted and service workers
disabled. Expanding only the receiver dialog and council/class branch rendered
the unique intended recipient, with its leaf key matching the JSON account ID.
No checkbox, draft/save or send action was selected. Ancillary subject captions,
crossed-out metadata and signatures used explicit invented empty stubs; CSS was
stubbed, unrelated reads and external/telemetry traffic were blocked. This is a
bounded directory-semantics check, not whole-app or styling qualification.

The newer system is a separate backend. The qualified 0.4.6 package still ships
only legacy messaging; the private investigation adapter is not a supported
public API. Modern JSON sending, payload encoding and acknowledgements remain
source-informed/unimplemented and live-unqualified. Further implementation and
the single-recipient live test need separate approvals. No legacy retirement
date was established and no account settings were changed. Details and required
next-increment gates are in [contracts/modern-messages.md](contracts/modern-messages.md).
Token-bearing URLs, private pages/app captures, worker and temporary environment
were deleted after the worker stopped and essential private plan state was saved.
Only sanitized accounting is retained publicly.

## 0.4.5 (2026-10-03) - Recipient and mailbox coverage

### Contracts, proofs and review

- Source and final installed wheel/sdist suites pass 981 tests on Python 3.13.15
  and 3.14.7, with one opt-in performance case deselected. Ruff, formatting,
  strict mypy, hooks, secret scans and dependency audit pass. OpenAPI parity stays
  at 35 unique operations; choice discovery reuses the fixed recipient route.
- New public `recipient_group_choices` models bounded nonzero `idGrupy` options.
  Default-zero selection fields preserve existing constructor calls; positive
  selections are allowed only for `grupa`, enter reference/result provenance and
  cache keys, and retain the exact five-field transport form. Virtual classes
  stay false. No arbitrary authenticated URL or extra send/body field is accepted.
- Named recipients remain ID-bearing ordered records. The independently observed
  unnamed hidden-target pair has `label=None`, not an invented name or empty
  success. Class-unavailable and unknown notices remain explicit typed failures.
  Empty group options are not empty recipient lists.
- Sent content accepts the observed subject/date metadata with absent addressee,
  preserving `correspondent=None`. Individual receipts keep displayed names,
  raw status and civil dates without invented IDs or aggregate read time. Duplicate
  labels/order survive. Unknown statuses, incorrect spans and mixed/duplicate
  receipt tables fail the whole result. Received consent/retry semantics do not change.
- Original regressions failed before fixes for sent metadata, unnamed targets,
  unavailable class notices, inert page-level scripts and mixed receipt ambiguity.
  Existing owner tests extend selector injection, exact wire forms, distinct
  caches, malformed layouts, bounds and pre-I/O scope rejection without production
  test hooks. Four maximum sent bodies with 256 receipts and 20 inert attachments
  each complete under the same exact 24-request shared budget as received content.
- Pair-programmer checklist self-review checked positive/negative layout space,
  no silent partial output, joined existing lifecycle ownership, scoped cache keys,
  and bounded fixed-form dispatch. Main-metadata parsing is separated from receipt
  classification. No independent subagent approval is claimed for this increment.
- Final artifact imports, MIT metadata/license, Python requirement and `py.typed`
  are checked in four isolated environments. Each environment replays all 60
  captured responses through public methods on loopback against private,
  independently recorded Chromium expectations. Final library bytes match the
  installed live-smoke wheel; documentation rebuilds do not require new logins.

### Fresh bounded live scope and accounting

Owner approval allowed four discovery logins on the four configured contexts,
then one installed-artifact smoke login on a selected context. Each admitted
one credential submission and at most 32 HTTP dispatches including authentication.
Only identity, recipient composer/lookup forms, proven existing mailbox pages
zero through two and at most one sent content selected from that login's own list
were allowed. No received opens, downloads, settings changes, sends, deletes,
read-once retrieval or consumer-state writes were authorized or made.

The four discovery attempts used 20, 21, 20 and 22 requests. The installed 0.4.5
wheel smoke used 22: one login, eight type lookups, two received pages, one sent
page and one sent content open. All five logins are used; total dispatches are
105, and unused per-attempt requests authorize no rerun or expanded operation.

- All contexts show eight type tokens, five populated named recipient types with
  62 displayed records, one unnamed target, one class-unavailable type and an
  empty group-option selector. This does not establish populated group membership.
- One discovery context shows 50 received rows on page zero and six on page one;
  installed public bounded collection returns all 56. Other contexts have one
  received page. Two show populated sent lists and permit the selected sent open.
- Installed smoke returns 63 recipient records including the unnamed target,
  one explicit unavailable type, zero group choices, 56 received and four sent
  summaries, and one individual read receipt. Warm cached calls dispatch zero.
- Chromium checks 47 discovery responses plus 13 installed-smoke responses with
  page scripts/networking disabled: no semantic mismatches. All four final
  artifact environments replay these independent expectations without live access.
- Same-byte apix 1.5.3 agrees on all 12 mailbox responses (168 row observations),
  five composer type lists and 25 populated named-recipient responses (310 row
  observations). It omits all five unnamed targets, flattens unavailable/group
  states to zero recipient rows, and rejects all three sent-content captures with
  ParseError. Native agrees with Chromium on those intentional differences;
  no apix fallback, copied implementation or fixture is used.

### Remaining gaps and retained evidence

Populated group choices/nonzero dispatch, recursive/virtual-class selection,
explicit empty-recipient success, populated sent pagination, newer/richer mailbox
layouts, multiple-recipient live receipts and other read-status variants remain
unqualified. Source-informed populated selector fixtures are not live evidence.
Nullable display fields require explicit future consumer adapters. No MCP state
or spool compatibility, consumer migration or publication is claimed here.

Sending is still unimplemented and is the final planned increment in PR #13,
after design approval and offline at-most-one-dispatch fault proofs. Any live
send needs fresh exact sender/recipient/payload approval and its own budget;
this read-only scope authorizes none. Read-once qualification remains separate.

Private captures, browser expectations, builds and artifact environments are
deleted after final replay. Retain only sanitized `release-evidence/0.4.5*` and
qualified local archives in `dist/0.4.5/`. No package has been published.

## 0.4.4 (2026-10-02) - Notification and checkpoint primitives

### Offline and review

- Complete source suite: 939 passed on Python 3.13.15 and 3.14.7, one opt-in
  performance case deselected. Ruff, format and strict mypy pass. OpenAPI parity
  covers 35 unique operations; counts reuse the existing optional student landing
  route under one catalogue ID and conservative authentication/no-replay policy.
- Final installed wheel and installed sdist: 939 passed in each of four isolated
  Python 3.13/3.14 environments. Import origins, version, Python requirement, MIT
  license metadata/file and `py.typed` marker are checked. Each final environment
  replays the captured count response through the public API on loopback against
  independent private Chromium expectations. Native library bytes match the live
  smoke wheel; documentation-only artifact rebuilds do not require another login.
- Pre-commit hooks, staged/worktree/history secret scans and dependency audit
  pass. Qualified local archives remain in `dist/0.4.4/`; nothing is published.
- Public loopback tests own explicit consent, pre-I/O callback/interval validation,
  single-login concurrency rejection, no caching/coalescing/replay, complete
  encoded-payload receipt before checkpointing, unsupported MIME/coding and
  malformed gzip preserved before parsing, bounds and whole-batch failure.
- A consumer-owned temporary sink fsyncs file and parent directory. Full envelope
  serialization/reconstruction, identity and gzip codecs, original identity and
  observation, duplicate event order and zero-network local replay pass with a
  fresh service. This is not compatibility with the existing MCP spool format.
- Cancellation at the exact completed-receipt boundary, repeated cancellation,
  service close, operation deadline, cooperative checkpoint timeout, cancellation
  suppression and queued cancellation retain/join ownership before releasing
  scheduler/account/operation capacity. Other-account reads queue behind held
  checkpoint admission and resume afterwards.
- Four independent full 1,024-event batches complete under one exact 24-request
  cold-login/consume budget. Shared concurrency, byte and queue limits remain
  enforced. This is representative offline load, not a live consumption claim.
- Pair-programmer design intentionally strengthens P5 to complete encoded-response
  checkpoint before semantic parsing. Post-review found self-cancellation bypassed
  unknown acknowledgement, ambiguous layouts became valid events, and unexpected
  custom-transport exceptions escaped with success diagnostics. Nine original
  regressions failed before fixes, including two Python 3.14.7 duplicate loop-error
  cases and an unfamiliar marked counter silently becoming zero. Corrected guards,
  owned-task cancellation detection, redacted exception normalization and
  cancellation-neutral waits now pass those proofs on both supported versions.
- Pair-programmer re-review approved the offline scope with no remaining blockers.
  Its optional close/failure and authentication-landing probes are retained as
  cases in the existing owner tests, not duplicated as separate testing layers.
- Ordinary counts extend the shared read guarantee matrix. Dedicated tests own
  category/label/count semantics, absent versus malformed counters, duplicates,
  unknown marked layouts and bounds. The scoped capture runner enforces one login,
  24 attempts and one count-page dispatch, including authentication landings.

### Bounded ordinary-count live qualification

Fresh approval covered account index zero, one credential submission and 24 total
HTTP attempts: authentication, identity and the ordinary count page only. The
installed 0.4.4 wheel completed in ten requests and one login, including exactly
one count-page GET. Warm cache reuse dispatched zero requests. Five categories
were shown; a missing category is not invented. Counts are token-scoped snapshots,
not fresh notification polling or seen-state updates.

No read-once request, message open, sending, deletion or consumer-state change was
allowed or made. The login allowance is exhausted; unused requests permit no
rerun. Chromium checked the identical private response with scripting/networking
disabled and recorded independent expectations. Apix 1.5.3 received the same bytes
through an inert client: categories, labels and amounts agree. Original fixtures
cover a broader counter styling variant that apix ignores while Chromium/native
agree; apix is not the correctness oracle.

### Evidence and remaining gaps

- Sanitized evidence and distribution checksums are retained under
  `release-evidence/0.4.4*`. External apix metadata advertises MIT but its bundled
  license is GPLv3; later incorrect MIT-only labels are corrected. No external
  implementation, test, fixture or documentation is incorporated.
- Read-once schedule layouts remain source-informed and offline-qualified only.
  No live event-consumption or apix live-event parity is claimed. Qualification
  needs a dedicated test login with disposable events and separately approved
  recovery integration; the current MCP spool cannot read raw envelopes.
- Callback success is an application durability acknowledgement. Failure/timeout
  means acknowledgement unknown, including after commit. Non-cooperative or
  non-preemptible callback work can exceed its interval while ownership remains
  retained. Loss before complete accepted receipt/checkpoint remains possible;
  no exactly-once guarantee or automatic recovery is provided.
- Broader roles/menu layouts/token freshness, consumer category selection, seen
  IDs, canonical hashes, bounded spool replay, competing-process transactions
  and state migrations remain pending. No consumer migration, sending,
  credentialed CI, push or publication is part of this increment.
- Private count captures/expectations, disposable builds and qualification
  environments are deleted after final artifact replay. Only sanitized evidence
  and the qualified local wheel/sdist are retained.

## 0.4.3 (2026-10-02) - Bounded attachment streams

### Offline and review

- Complete source suite on Python 3.13/3.14: 865 passed in both environments,
  one opt-in performance case deselected. Ruff, format and strict mypy pass.
  OpenAPI parity covers 34 operations.
- Installed wheel and sdist suites pass all 865 tests in four isolated Python
  3.13/3.14 environments outside the checkout. Installed import location,
  package version, MIT license, `py.typed` and dependency consistency pass.
  Every environment replays both content captures against independent private
  Chromium expectations, including the populated attachment linkage. Final
  library package bytes match the wheel used for the live stream smoke.
- Locked dependency audit reports no known vulnerabilities. Repository hooks
  and staged/worktree/history secret scans pass.
- Public stream tests exercise original two-origin HTTP, independent login
  contexts, account-bound references, credential/cookie isolation, hostile
  redirects, real streaming, 64 KiB chunks, exact byte bounds, unknown-length
  cumulative budgets, framing/encoding failure and no automatic replay.
- Representative offline load streams one full 50 MiB file with an exact
  seven-request login/resolve/download budget. Four independent logins with mixed
  reads/downloads saturate shared admission; paused streams retain scheduler
  slots and an exact six-request warm shared budget completes queued work.
- Early break, queued/entry/body cancellation, repeated cancellation during
  delayed cleanup, service close and paused-consumer deadline cases release
  capacity only after joining owned transport work. Subsequent reads succeed.
- Pair-programmer design precedes implementation. Independent post-review found
  a first-field-only encoding guard accepted duplicate Content-Encoding and
  unsupported Transfer-Encoding with false completion. All three raw-wire
  regressions failed before the fix. The corrected complete-field guard rejects
  those representations before delivery; ordinary chunked framing succeeds.
  Duplicate identity/chunked field cases also remain in the owning regression
  table. Re-review approved the corrected offline scope with no blockers.
- The qualification runner's original loopback tests enforce one login, 24
  attempts, exact account-bound selection, already-read discovery, one bounded
  smoke download, stop-on-ambiguity and no retained attachment bytes.

### Bounded live qualification

Fresh approval allowed up to four independent discovery logins and one reserved
installed-smoke login, each with 24 total wire attempts. Scope: identity,
received/sent page zero, at most one already-read received content open per
login, and the selected smoke attachment's resolution/download up to 10 MiB.

| Attempt | Logins | Requests | Content opens | Download | Result |
| --- | --- | --- | --- | --- | --- |
| Discovery A | 1 | 11 | 0 | None | No eligible attachment |
| Discovery B | 1 | 11 | 0 | None | No eligible attachment |
| Discovery C | 1 | 12 | 1 | None | One attachment reference observed |
| Installed wheel smoke, same selected login/reference | 1 | 14 | 1 | 1 | 930,056 bytes, clean EOF |
| Total | 4 of 5 allowed | 48 of 120 allowed | 2 | 1 | No expanded or repeated attempts |

The fourth discovery login was unnecessary after an eligible message was found.
Unused allowances are not permission for reruns. No unread or sent content was
opened; no sending, deletion, read-once operation or consumer migration occurred.
The download supplied no Content-Length; actual byte accounting and clean EOF
confirmed stream completion. Attachment bytes were consumed and discarded,
never saved. One successful file does not establish arbitrary key/header formats
or the absence of upstream read effects.

Chromium independently checked all ten captured responses with scripts and
networking disabled. This extends list evidence to 35 received rows and eight
populated sent rows on page zero, including attachment/unread flags. Two content
responses include one displayed attachment and a read receipt. Rendered fields,
body lines, filename and numeric route linkage agree. The browser check initially
mistook popup-name/dimension numbers for attachment IDs; extracting only the
inert route literal corrected that false mismatch without a parser change.

Apix 1.5.3 received identical captured list/content bytes through inert parsers.
Common summary and four content fields agree. Apix has no attachment-stream,
attachment-metadata or read-receipt contract; those are native independently
checked features, not inferred apix parity.

### Evidence and remaining gaps

- Sanitized accounting is in `release-evidence/0.4.3-streams.json`; local artifact
  checksums are in `release-evidence/0.4.3.sha256`. No public evidence contains
  account/message/file IDs, signed keys, filenames, cookies or body text.
  Task-owned private captures, browser expectations, build trees and virtual
  environments are deleted after qualification; only the two local distribution
  archives and sanitized evidence remain.
- Sent-message downloads, multiple/empty files, alternate attachment handlers,
  key/header variants and upstream read effects remain live-unqualified.
  Conservative key grammar and provisional `none` effect classification remain
  source-informed restrictions. Populated pagination/new mailbox layouts and
  other 0.4.x gaps not explicitly observed here remain pending.
- Library file naming/saving/publication is intentionally absent. MCP atomic
  publication, notifications, sending, credentialed CI and PyPI publication
  retain their separate scopes. No push or publication is part of 0.4.3.

## 0.4.2 (2026-10-02) - Message content and inert attachment metadata

### Offline

- Complete source suite, Python 3.13/3.14: 803 passed in both environments,
  one opt-in performance case deselected. Installed wheel/sdist suites also pass
  all 803 tests in four isolated environments outside the checkout; installed
  imports, package metadata, license, `py.typed` and dependency consistency checked.
- All four artifact environments replay the three captured content responses
  and an original synthetic two-file response through the installed public API
  on loopback. Every content field agrees with independently recorded Chromium
  expectations, not a comparison against the same parser. Warm reuse dispatches
  zero requests. The qualified library package bytes match the live-smoke wheel.
- Ruff, format and strict mypy are clean. OpenAPI parity passes for 32 operations.
- Repository hooks, staged/worktree/history secret scans and locked dependency
  audit pass; no known dependency vulnerabilities were reported.
- Four independent maximum-content reads (65,536 characters and 20 file
  references each) pass through real loopback HTTP under one exact 24-request
  login/content budget. This is representative bounded offline load, not a
  performance-improvement or large live-mailbox claim.
- Shared read tests own isolation, coalescing/cache, budget/deadline/cancellation,
  notices, response limits, exact GET wire forms and no expiry replay.
- Content tests own explicit consent, bound reference validation, metadata/body/
  receipt semantics, whole-read failure, attachment linkage/cardinality/limits,
  duplicate names versus IDs, and invalidation of both received page and batch
  caches even when parsing fails. Capture tests exercise both approved flows,
  unread-selection rejection, scope and actual-attempt/login caps offline.

### Bounded live qualification

Fresh owner approval: two attempts on one independent account context, each
with one login submission, 24 total HTTP attempts, identity, received/sent page
zero and at most two opens of one already-read received message. No unread
opens, sending, downloads, deletion or read-once requests were allowed or made.

| Attempt | Login submissions | Requests | Received opens | Result |
| --- | --- | --- | --- | --- |
| Source-route discovery | 1 | 12 | 1 | Main metadata, optional read receipt and body captured |
| Installed 0.4.2 wheel public smoke | 1 | 13 | 2 | Two fresh results agree; warm reuse dispatches zero |
| Total | 2 | 25 of 48 allowed | 3 | Login authorization exhausted |

The selected already-read message has 395 normalized plain-text characters,
a displayed read timestamp and no attachments. Received lists contained two
rows (one unread) and sent lists were explicitly empty. Unread content was never
opened. Unused requests do not permit a third login or expanded scope.

Chromium independently checked all seven captured responses, including three
content responses, with scripts/networking disabled. Every common field,
rendered body line boundary and displayed read timestamp agrees. Two invented
file entries also pass the independent browser check, which is offline evidence
only. Apix 1.5.3 received the exact same three content responses through an inert
client; all four comparable fields agree. Apix has no attachment or read-receipt
contract, so those fields are independently checked, not parity-inferred.

### Regressions and evidence boundary

The observed page contains two exact `stretch` tables, not one: main metadata
and the read receipt. An original regression failed before receipt-aware parsing.
An HTML page comment caused a raw `TypeError` during attachment scanning; its
regression failed before non-element nodes were skipped. Both fixes precede the
successful installed live smoke.

A real persistent-connection disconnect test detects aiohttp's hidden GET replay:
it fails with the default retry behavior and passes with hidden retries disabled.
The service still owns explicit safe expiry recovery. Content opens never recover
or replay automatically. Potential read effects are not rolled back by parse,
transport, timeout or cancellation failure.

Privacy-safe metrics are retained in `release-evidence/0.4.2-content.json` and
distribution checksums in `release-evidence/0.4.2.sha256`. Private captures and
independent browser expectation files (0600, inside a task-owned 0700 directory
outside Git), temporary builds and environments are deleted after qualification.
No message text, field diffs, account/record IDs, cookies or screenshots remain.

### Remaining gaps

- Populated sent content, populated attachment metadata, empty/rich live bodies,
  read-receipt variants, other account roles and newer mailbox layouts are not
  live-qualified. Attachment handlers/labels have original offline proof and
  source-informed consumer requirements only; no attachment route is enabled.
- No credentialed CI, consumer migration, PyPI publication or push is included.
  Earlier feature families were regression-tested offline, not rerun live except
  for the two explicitly approved mailbox page-zero lists.
- Bounded attachment streams are next in 0.4.3. Sending and read-once operations
  remain separately planned and authorized.

## 0.4.1 (2026-10-02) - Recipient discovery

### Offline

| Check | Result |
| --- | --- |
| Complete source suite, Python 3.13 and 3.14 | 748 passed in both environments; one opt-in performance case deselected |
| Installed wheel and sdist, Python 3.13 and 3.14, outside checkout | 748 passed in each of four environments; imports, metadata, license and `py.typed` checked |
| Installed public API replay of actual private captures through loopback HTTP | All four environments: eight group types and three lookups with 1/55/1 recipients; warm cache dispatches none |
| Ruff, format and strict mypy | Clean |
| OpenAPI / route catalogue parity | Pass, 30 operations |
| Full bounded lookup | 2,000 distinct IDs sharing one display name survive one real loopback HTTP lookup |

The shared read suite owns account isolation, cache/coalescing, notices,
budgets, cancellation, exact forms and no selection replay for both operations.
The family suite owns named selectors, header/body boundaries, label/checkbox
linkage and cardinality, duplicate names versus duplicate IDs, foreign and
injected references, unsupported subgroups, limits and cache selection keys.
Capture tests own approved token selection, six-list and one-login limits, and
the actual discovery/smoke flow on loopback. No external fixture or code was
copied. `scripts/replay_recipients.py` exercises the installed runtime against
real response bytes, not only synthetic tests.

### Bounded live use

One account context, initially two attempts of at most 24 requests each. The
first scope allowed only numeric group types, which the real composer does not
use. That attempt stopped after ten requests and one credential submission,
before any recipient POST. The owner explicitly amended the remaining attempt
to the observed `wychowawca`, `nauczyciel` and `sekretariat` tokens; no third
attempt was authorized or performed.

The installed 0.4.1 wheel public smoke then passed in sixteen requests, one
login, one group GET and six recipient POSTs (two fresh reads per approved
group). Group discovery and each group lookup also passed zero-request warm-cache
checks. The three groups had 1, 55 and 1 recipients. Total: two logins, 26/48
requests. Unused requests do not authorize another login.

Chromium independently checked all eight captured responses: displayed group
labels/tokens, availability and radio linkage; recipient labels, numeric IDs and
checkbox/value linkage. The separately acquired apix 1.5.3 received
identical bytes through an inert replay client. Group-token and recipient-pair
mismatch counts were zero. No message open, sending, mark-read, download, deletion
or read-once call occurred.

### Review correction and evidence boundary

The real group header initially failed parsing; an original headed-table test
failed before the `tbody`-only correction. After the successful live smoke,
review found that an unlabeled numeric checkbox could silently disappear. A new
regression failed before a cardinality guard was added. The select-all checkbox
is explicitly excluded, not misidentified as a recipient.

The strengthened parser, conservative lookup-capability naming and updated
route-evidence metadata were qualified
offline against all private captured bytes, including Chromium comparison and
the installed public runtime on loopback. That is not a fresh credentialed smoke
of changed code and does not consume another login. Qualification uses real
populated responses rather than apix/synthetic agreement as its oracle.

Privacy-safe metrics are in `release-evidence/0.4.1-recipients.json`; distribution
checksums are in `release-evidence/0.4.1.sha256`. Raw responses were private 0600
captures outside Git, deleted after final offline replay. No names, numeric
recipient IDs, raw diffs, cookies or message text are retained.

### Gaps and next increment

- Empty recipient layouts, subgroup/virtual-class selection, other group types,
  disabled recipients and other account roles remain unqualified. `grupa` lookup
  is explicitly unsupported; unknown/empty pages fail, never silently become `[]`.
- No performance improvement, general-school compatibility, consumer migration,
  credentialed CI or PyPI publication is claimed. Earlier school reads/message
  lists were regression-tested offline, not rerun live outside this scope.
- Full message content is next (0.4.2). Its potentially mark-read effect requires
  a separate approved already-read/sent message selection before live access.
- Sending remains plan-only; discovery never authorizes contact with a recipient.

## 0.4.0 (2026-10-02) - Message lists only

### Offline

| Check | Result |
| --- | --- |
| Complete suite from source, Python 3.13 and 3.14 | 697 passed in both environments; one opt-in performance case deselected |
| Installed wheel and sdist, Python 3.13 and 3.14, outside the checkout | 697 passed in each of four environments; installed imports, metadata, MIT license and `py.typed` checked |
| Ruff, format, strict mypy | Clean |
| Repository hooks, untracked-inclusive secret scan, locked dependency audit | Pass; no known vulnerabilities |
| OpenAPI / route catalogue parity | Pass, 28 operations |
| Full bounded mailbox workload | Four concurrently requested independent 250-row mailboxes, five pages each, 40 total login/list requests; warm batch reuse dispatches none |

The shared read suite was extended for both mailbox folders, covering exact
wire forms, account isolation, caching/coalescing, expiry, no POST replay,
throttling, maintenance, notices, budgets and cancellation. Family tests own
summary semantics, numeric references, explicit empty sent/received pages,
header/row/date validation, limits, overlap deduplication, bounded continuation,
mid-page drift, repeated/clamped/non-progress pages and later-page failure.
Capture-scope tests execute discovery and installed-smoke flows on loopback,
reject send fields, unapproved pages/operations and a second login, and enforce
actual-attempt/list caps. No external code or fixtures were copied.

### Live and identical-byte replay

Fresh approval covered two attempts on one configured login, each capped at 24
requests and ten fixed received/sent pagination POSTs on pages 0..2. Identity was
allowed. Recipients, content opens, mark-read, downloads, sends, deletes and
read-once events were excluded. There was no automatic login replay.

| Attempt | Login submissions | Actual HTTP requests | Result |
| --- | --- | --- | --- |
| Early installed-route discovery | 1 | 11 | Populated received and explicit-empty sent page zero captured |
| Installed 0.4.0 wheel public smoke | 1 | 14 | Page, bounded batch, mid-page resume and zero-request warm page cache passed |
| Total | 2 | 25 of 48 allowed | Approval exhausted; unused requests do not authorize another login |

The final received page had two rows, one read and one unread; sent was explicitly
empty. Chromium, with networking and scripts disabled, independently checked
every visible summary field, numeric reference, computed unread/attachment flag
and empty marker in all seven captured list responses. The separately installed
External apix 1.5.3 pure parsers received the exact same bytes; there were zero
comparable summary-field mismatches. Neither replay used a live client.

The live smoke exercised the installed library, not checkout imports. Final
package documentation was updated afterwards; all library package bytes were
compared with the live-smoke wheel and were identical. Rebuilt artifacts were
qualified offline. Distribution checksums are in `release-evidence/0.4.0.sha256`;
sanitized live accounting is in `release-evidence/0.4.0-messages.json`.

Private captures were 0600 under a task-owned 0700 directory outside Git and
deleted after replay. No raw page, private assertion dump, screenshot, record ID
or message text is retained.

### Live-derived corrections and gaps

The first offline replay failed despite green synthetic tests: the real table
has a blank footer, and both folders show a benign legacy-module banner. Four
original regressions failed before the parser was corrected to read `tbody`
only and allow that exact information banner. Unknown notices still fail.

- Populated sent rows, multi-page metadata/continuation, attachment indicators,
  other account roles and the newer mailbox layout have no live evidence yet.
- Full mailboxes and pagination/drift limits were exercised offline. The small
  live mailbox is not load verification or a performance-improvement claim.
- Recipient discovery, full content, streams, notification checkpoints and
  sending are not implemented in 0.4.0. Their separate versions and sending
  approval plan are in [contracts/messages.md](contracts/messages.md).
- Earlier school-read families were fully regression-tested offline, not rerun
  live outside this approval. Their 0.3.0 evidence and follow-ups remain below.
- No consumer migration, credentialed CI, macOS/Windows check, push,
  hosted PR qualification or PyPI publication was performed in this increment.

## 0.3.0 (2026-10-02)

### Offline

| Check | Result |
| --- | --- |
| `pytest` from source, Python 3.14 | 622 passed (1 opt-in performance case deselected) |
| Installed wheel and sdist, Python 3.13 and 3.14, run outside the checkout | 622 passed in each of the four environments; imports resolve to the installed package |
| Ruff, format, strict mypy (src, tests, scripts) | Clean |
| OpenAPI and route catalogue parity | Pass, 26 operations |

Distribution checksums are in `release-evidence/0.3.0.sha256`, kept outside
the sdist inputs so the archive does not checksum itself.

The shared read suite (`tests/test_account_reads.py`) was checked against
planted regressions. Replaying a POST after expiry fails 6 cases. Disabling
coalescing fails 13. Caching failed reads fails 13.

### Live

The owner authorized live use of the configured accounts. Every run used
`scripts/live_capture.py`: one credential submission per run, an operation
allowlist, a request cap, and no sends, read-once events, mark-read calls or
attachments. Raw pages stayed in private 0600 scratch directories outside the
repository and were deleted afterwards.

Total for 0.3.0: 12 logins and 216 requests over four logins (two students,
each with two logins).

The final smoke ran through the installed 0.3.0 wheel on one login per student:

| Read | Student A | Student B |
| --- | --- | --- |
| identity, student_information | OK, matches Chromium | OK, matches Chromium |
| final_grades, grades | 26 subjects, 17 grades | 11 subjects, 6 grades |
| attendance, attendance_detail | 10 records | 1 record |
| attendance_frequency, subject_frequency (one day) | OK, 125 gateway rows | OK, 112 gateway rows |
| timetable | 91 slots match Chromium, including substitution notices | 91 slots match Chromium |
| announcements | 7 items | 7 items |
| agenda, two months, plus one detail | 5 and 13 events and the detail match Chromium | 3 and 3 events and the detail match Chromium |
| homework | Empty month matches Chromium | Empty month matches Chromium |
| completed_lessons_page | `ViewDisabledError` | `ViewDisabledError` |
| behaviour notes page | Explicit empty | Explicit empty |
| Requests | 28 | 28 |

"Matches Chromium" means `scripts/crosscheck.py` compared the parser's output
with Chromium's rendering of the same bytes: every event, tooltip text,
reference, detail field, timetable slot and notice tooltip, and profile field.

Grade, attendance and announcement counts were checked against the raw page
structure. On both students, every real grade box became a record. The
remaining boxes are a hidden template row and the observation card (see gaps).

Populated homework was verified on an earlier capture of the same build: 2
assignments (one marked done) and their detail page match Chromium. The
one-month window boundary was confirmed live: 1 Sep to 1 Oct is accepted and
1 Sep to 31 Oct is rejected.

### Defects found live and fixed

Each one had a failing test, written from an original fixture with the observed
structure, before its fix.

| Family | Live behaviour | Before | Now |
| --- | --- | --- | --- |
| Homework | Columns: subject, teacher, topic, category, date and weekday, due date and weekday, status, options | Mislabeled fields; weekday parsed as clock; every populated list failed | Header-mapped columns, weekday check, status and done marker |
| Homework | Ranges longer than one month answered with "Wybrano nieprawidłowy zakres daty." and an empty marker | Reported as an empty list | Rejected up front; the notice is `InvalidInputError` |
| Completed lessons | "Ten widok został wyłączony przez administratora szkoły." on all four logins | `ParseError` | `ViewDisabledError`, on every page parser |
| Profile | Name label "Imię i nazwisko ucznia" | `ParseError` | Parsed; the login owner's rows are ignored |
| Timetable | Substitution notice wrapped in its tooltip anchor | `UnsupportedCapabilityError` | Notice metadata read from the wrapping anchor |
| Agenda | 33-line meeting description | `LimitError`; with a larger cap, numbered lines became bogus fields | One `Opis` field until the next known label; 256-line cap |

The profile, timetable and agenda failures also occur on the previous `main`.
They were found only because the final smoke covered every family, not only the
0.3 ones.

## Gaps

- **Completed lessons, populated.** Every available login shows the view
  disabled by its school, so no populated layout or pagination has been seen
  live. The parser follows source-informed requirements with original fixtures.
- **Behaviour notes.** Both students have an explicit empty page. Public support
  stays deferred ([decision](contracts/behaviour-notes.md)).
- **Observation card.** The grades page can include "Karta spostrzeżeń", a table
  of formative assessments. It is not read yet, and apix does not read it either.
- **Coverage breadth.** Two students at the observed schools. Other schools,
  account roles, last-login views, custom attendance types and populated
  descriptive grades are unverified.
- **Not run in 0.3.0.** The scheduled credentialed CI, macOS and Windows, PyPI,
  and the `librus-mcp` migration.

## Earlier releases

- **0.1.0** (2026-09-30): login, identity and profile, with transport, scheduler
  and budget proof offline. Installed artifacts were verified on Linux with
  Python 3.13 and 3.14. A four-login MCP stdio experiment (closed PR #38)
  completed offline. First GitHub CI run:
  [36721820811](https://github.com/krzysztofbury/librus-python-api/actions/runs/36721820811).
  Checksums are in `release-evidence/0.1.0.sha256`.
- **0.2.0**: grades. A bounded four-context live comparison used 94 of 128
  allowed requests. See [contracts/grades.md](contracts/grades.md) and
  [BENCHMARKS.md](BENCHMARKS.md).
