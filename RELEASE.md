# Releasing librus-python-api

## Owner setup

The publishing file is **`.github/workflows/workflow.yaml`**. Its filename is part
of the PyPI Trusted Publisher identity, not just its display name.

Configure a GitHub Trusted Publisher (or a pending publisher for the first upload)
on PyPI with:

| Field | Value |
| --- | --- |
| Project | `librus-python-api` |
| Owner | `krzysztofbury` |
| Repository | `librus-python-api` |
| Workflow filename | `workflow.yaml` |
| Environment | `pypi` |

No API token or PyPI password belongs in GitHub secrets. PyPI requires the owner
to complete account security/2FA requirements. A pending publisher does not
reserve the project name. See [PyPI's pending-publisher instructions][pending].
The first real PyPI OIDC upload succeeded for 1.0.0rc1 in
[run 37281758063](https://github.com/krzysztofbury/librus-python-api/actions/runs/37281758063).
TestPyPI is intentionally not used.

The GitHub `pypi` environment requires owner review, disallows administrator
bypass and permits deployments only from branch `main` and tags `v*`; a release
run deploys from its tag. Self-review is allowed for this single-owner
repository: the owner can publish a release and then explicitly approve its
publication job. Add an independent reviewer and disallow self-review
if a two-person approval policy is needed. No environment secrets are needed.

This environment is separate from branch protection. The existing `protect-main`
ruleset was disabled when inspected; it was not changed by release setup. Review
branch/tag protection separately so only reviewed code can change the release
workflow or create/move `v*` tags.

## Before the first 1.0 release

The first `1.0.0rc1` candidate is explicitly approved as a library-only beta
prerelease with the 0.7.0 API. It does not claim completed MCP integration,
old-state migration/rollback, broader live qualification or stable 1.0 readiness.
These remain separate tracked gates; publication does not close them.

Stable 1.0.0 is scoped to the documented native library API, with the integration
boundaries #22-#25 independently merged and qualified. It is the library dependency
for the later native MCP cutover, not the consumer release itself. Its compatibility
policy is in [API.md](API.md#compatibility-policy); general live-school guarantees,
production migration and MCP acceptance are not inferred from its classifier.

The pipeline supports `v1.0.0rc1`, `v1.0.0` and later version tags. It refuses
publishing 0.x; a qualification run can exercise a 0.x development tag without upload.
It does not decide product readiness or imply completed consumer migration.

Required release decisions:

1. Freeze the supported library API and explicitly document unsupported school
   features/layouts. Preserve pending live checks as pending, not "passed".
2. Qualify the exact candidate in MCP or explicitly scope the first library
   release independently of MCP cutover. MCP integration and migration/rollback
   are separate, unfinished roadmap gates, not provided by a publishing workflow.
3. Preserve 0.6 persistent stores/UNKNOWN records. 0.7 introduced required context
   keys and format 3; no automatic legacy state migration exists.
4. The first `1.0.0rc1` upload is complete. The approved stable release remains
   library-only; qualify the consumer against its exact installed dependency before
   the later MCP cutover. Scope changes require an explicit readiness decision,
   not an automatic version bump by this workflow.
5. Update `__version__`, OpenAPI version, versioned changelog and README release
   status/install command together. Keep classifier assertions in the artifact
   verifier consistent with any intentional Beta-to-Stable change.

Release setup enables no credentialed checks. All release tests and runtime
smokes use synthetic loopback servers, never real Librus. The manual,
owner-authorized live check in step 4 runs locally, never in CI. The separate
weekly live check below never publishes and is not a release gate.

## Procedure

`librus-mcp` follows the same steps in its `DISTRIBUTION.md`, without step 3.
When a release of both is needed, publish this library first, then pin it in
`librus-mcp`.

1. Merge the release preparation PR after CI passes on its exact head and on
   `main`. Release scripts and `workflow.yaml` must be present in both `main` and
   the tagged source. `main` requires signed commits: commit with GPG
   (`commit.gpgsign`) and check the PR head before replacing anything,
   `gh api repos/OWNER/REPO/commits/SHA --jq .commit.verification.verified`.
   Only if it is `false`, recreate the same tree as one signed commit with the
   GraphQL `createCommitOnBranch` mutation on a `release-X.Y.Z` branch (GitHub
   signs it; a REST `git/commits` call is not signed), confirm the trees match
   and close the unsigned PR in its favour.
2. Create an annotated immutable tag at the intended merged commit. Push it and
   confirm the remote tag points to that commit. Never replace an uploaded tag.
3. Run **Qualify and publish library** from **main** for that tag. It never
   publishes. All checks must pass, including macOS and Windows disk gates.
4. Run the read-only live check, which a release request from the owner covers.
   Nothing is published until it passes. Build the
   tagged source's wheel, install it into a fresh environment outside the
   checkout, and from the checkout root run
   `ENV/bin/python -m scripts.live_check run --profile release --secrets FILE`
   with that environment's interpreter. It logs in once per configured account, uses only
   allowlisted reads (no message opens, sends or read-once routes) and reports
   statuses and counts only. The `release` profile covers messaging and
   session reads, not grades or other school reads: when the release changes
   such a read, also run `--profile weekly --record` on the same wheel. It
   allows two logins per run, so split the accounts into `0600` pair files in
   scratch and delete them afterwards. Publish only if it passes, and record the summary
   in the release notes. A failed step blocks publication; fix it in a new
   version rather than publishing a version that failed.
5. Publish the GitHub Release, which starts publication:
   `gh release create vX.Y.Z --verify-tag --title "X.Y.Z - Summary" --notes-file FILE`.
   The summary is a few words from the changelog entry; the notes are that entry
   and the live check summary. Add `--prerelease` for a release candidate. The run
   builds its own sealed pair once, qualifies
   it, then waits for `pypi` environment approval. Bytes from an earlier
   verification run are not silently substituted into a later run.
6. Inspect that run's tag, commit and results, then approve the publish job.
   Trusted Publishing uploads only that run's verified wheel/sdist with
   attestations. PyPI hashes and a fresh installed runtime smoke are checked
   afterward, and the run attaches the wheel, sdist and `SHA256SUMS` to the
   release. A publication job is never run from a PR.
7. Check what users get: a fresh install from PyPI and the attached files.

CLI equivalent:

```sh
gh workflow run workflow.yaml --ref main -f tag=v1.0.0
# After qualification, the live check and an explicit release decision:
gh release create v1.0.0 --verify-tag --title "1.0.0 - Summary" --notes-file FILE
```

## What the pipeline proves

- Remote tag, package/changelog/OpenAPI version and main ancestry agree.
- Locked tools, quality hooks, secret-history scan, dependency audit and source
  tests pass before building. The build backend is pinned and installed from the
  lock; release builds use no build isolation to avoid a floating backend.
- Wheel/sdist metadata, MIT license, typed marker and lean archive contents pass
  the artifact verifier and strict Twine metadata/README checks.
- One pair is built, sealed with SHA256, uploaded by artifact ID, and downloaded
  unchanged for every qualification job and the publisher. Tampered/extra files
  fail; the publisher does not rebuild or upload the manifest.
- Both archives run the full offline suite and installed loopback smoke on Linux
  and macOS, Python 3.13/3.14, with locked and newest permitted runtime dependencies.
  Test tooling stays locked. Latest-runtime resolution takes the newest releases
  outside the 7-day supply-chain window (`exclude-newer` in `pyproject.toml`).
- Both archives separately run Windows x64 NTFS disk/persistence acceptance and
  installed runtime smokes on Python 3.13/3.14, with locked/latest dependencies.
  Every Windows job verifies the same manifest; publishing requires all of them.
- Only the isolated, environment-gated publishing job has `id-token: write`.
- Post-upload verification compares public PyPI wheel/sdist hashes with the
  sealed manifest and resolves the exact version from PyPI outside the checkout.
  It is pending until a real publication occurs, not proved by an offline mock.

`.github/workflows/dependency-drift.yml` separately checks newest allowed runtime
dependencies weekly and on demand. It has no upload authority or Librus secrets.

## Failures and recovery

A job that failed on a flake reruns with `gh run rerun ID --failed`, which keeps
that run's sealed artifact for 14 days. Before upload, fix a real failure and
repeat verification. Do not waive a failed platform matrix or remove an invariant
just to get a release out. To stop a release, reject the waiting approval first,
since a later approval would publish with no release to attach to, then
`gh release delete` it; the tag stays. A fault in the tag's own source or workflow
needs a new version, because a release run uses the files at the tag.

For a few minutes after an upload, uv may report that the new version does
not exist although PyPI's JSON API lists it: the simple index is still
catching up. A consumer's CI job or a `uvx` check failing that way is not a
packaging fault; retry or rerun it a few minutes later.

Once anything reached PyPI, never delete and republish the release: a new run
builds again and cannot upload over an existing version. If `confirm` or `attach`
fails on a flake, rerun that job with `gh run rerun ID --failed`. If it fails
because of the workflow at the tag, a rerun fails the same way; complete both
jobs by hand from the run's sealed artifact (`gh run download ID`), as was done
for 1.10.0:

1. Check the downloaded files against the `manifest` digest that `build`
   recorded: `python3 scripts/release_gate.py verify --directory DIR --digest
   DIGEST`.
2. Confirm PyPI's files have the same hashes:
   `uv run --locked python scripts/verify_published.py --wait-index DIR`.
3. In a fresh environment, install the hash-pinned locked dependencies
   (`uv export --locked --no-emit-project`), then the published version from
   PyPI with `--no-cache --refresh`, and run `uv pip check` and
   `scripts/installed_smoke.py` with `ARTIFACT_ENV` set to that environment.
4. Attach the same files: `sha256sum -- *.whl *.tar.gz > SHA256SUMS`, then
   `gh release upload vX ./*.whl ./*.tar.gz SHA256SUMS`.
5. Say in the release notes what was done by hand, and fix the workflow before
   the next release.

If upload fails, check PyPI before rerunning. One of the two files may already
exist. PyPI versions/files cannot be overwritten; do not rebuild different bytes
and publish them under the same version. This pipeline intentionally does not
use `skip-existing`. Retain the sealed run artifact (14 days) and reconcile an
incomplete upload with the owner; a new version is the safe normal recovery.

If post-upload confirmation fails, the package may already be public. Inspect
the public JSON/version and original hashes first. The confirmation waits up to
ten minutes for PyPI's simple index to list both files, because the JSON API
updates first, and retries the fresh installation twice. Retry verification, not
the entire publisher, for temporary index visibility failures. A
compromised/broken release requires an explicit yank and corrected version.
Never auto-delete a release or reset user state; document a known-good
dependency pin for rollback.

## Weekly live check

`.github/workflows/live-check.yml` detects upstream drift. Every Monday at
05:17 UTC, and on manual dispatch, it builds a wheel from `main`, installs it
with hash-pinned locked dependencies, logs in once per configured account
and makes only the side-effect-free reads declared in `scripts/live_check`.
It never sends, opens received messages, consumes read-once events, downloads
files or writes notification state. It fails on rejected credentials, required
account action, throttling, maintenance, parser errors, identity mismatch, or
coverage that differs from `contracts/live-check-expectations.json`. It never
retries and never logs in twice with the same credentials in one run.

Hard limits: at most two logins, 70 requests and 4 minutes per login, and 10
minutes per run. Logins the run deadline leaves unchecked are reported as not
run, which fails the run.

It never installs a release from PyPI. To check a published release, run the
local release profile on its installed wheel (Procedure, step 4).

Logs, job summaries and artifacts of this public repository are readable by
anyone. The check prints versions, statuses, coverage values and counts only.

### Configuration (owner, once)

1. Create the GitHub environment `live-check`. Restrict deployment branches to
   `main`. Add no required reviewers: the schedule runs unattended.
2. Keep `main` protected and the set of collaborators with write access minimal:
   anyone who can change workflows on `main` can reach these secrets.
3. Prefer dedicated accounts. Each run signs in, which updates the account's
   last-login information and may affect notification baselines of other
   clients using the same login.
4. Locally, with the owner's authorization, print the expected identities from
   the checkout root:
   `ENV/bin/python -m scripts.live_check identity --secrets FILE`
   (refused inside CI).
5. Add environment secrets `LIBRUS_LIVE_LOGIN_n`, `LIBRUS_LIVE_PASSWORD_n` and
   `LIBRUS_LIVE_IDENTITY_n` for slots 0 and 1. Slot 1 is optional.
6. Run the workflow manually with `record` ticked. Review the printed coverage
   map, set each slot's `role`, mark naturally volatile checks (for example
   timetable, agenda, homework) as `any`, and commit it to
   `contracts/live-check-expectations.json` through a PR.

Until expectations exist, every run fails with `no_expectations`. Missing
secrets fail with the missing secret names.

### Notifications and freshness

GitHub emails failures of scheduled runs to the user who last changed the
workflow's cron line, and of manual runs to the person who started them.
Enable email for failed workflows under GitHub Settings, Notifications,
Actions. A green badge is only as fresh as its run date: GitHub disables
scheduled workflows in public repositories after 60 days without repository
activity and may delay or drop scheduled runs. Check the run history if no
weekly run appears; a missing run sends no email from that workflow itself.

The separate dependency-drift workflow runs `scripts/check_live_freshness.py`
in its own job with `contents: read` and `actions: read` only. It queries the
GitHub API for completed `live-check.yml` runs on `main` and fails if the most
recent completion (`updated_at`) is older than eight days, missing or malformed.
It also rejects future/inconsistent timestamps and unexpected workflow/branch
records. API/authentication errors fail the job. No Librus credentials are used.
Freshness includes completed failed runs; the live workflow's own status and
failure notifications still report their outcome.

Reproduce the offline recent/stale decisions with `uv run pytest
tests/test_live_freshness.py`. Its fixture is a projection of public GitHub run
metadata retrieved on 2026-10-09, with no school data. A manual dependency-drift
dispatch can exercise the watchdog on a feature branch while it inspects only
`main` live runs. If GitHub suppresses both schedules, neither can alert; inspect
run history when both are missing.

### If a credential may have leaked

1. Change the Librus password of the affected account.
2. Delete the environment secrets and disable the workflow.
3. Review recent run logs and summaries for unexpected content.

[pending]: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
