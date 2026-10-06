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
bypass and permits deployments only from branch `main`. Self-review is allowed
for this single-owner repository: the owner can start a run and then explicitly
approve its publication job. Add an independent reviewer and disallow self-review
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
publishing 0.x; `verify` mode can exercise a 0.x development tag without upload.
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

No scheduled/live credentialed checks are enabled by release setup. All release
tests and runtime smokes use synthetic loopback servers, never real Librus. The
manual, owner-authorized live check in step 4 runs locally, never in CI.

## Procedure

1. Merge the release preparation PR after CI passes on its exact head. Release
   scripts and `workflow.yaml` must be present in both `main` and the tagged source.
2. Create an annotated immutable tag at the intended merged commit. Push it and
   confirm the remote tag points to that commit. Never replace an uploaded tag.
3. Run **Qualify and publish library** from **main**, with the intended version
   and `target=verify`. All checks must pass, including macOS and Windows disk gates.
4. Run the read-only live check with the owner's authorization. Build the
   tagged source's wheel, install it into a fresh environment outside the
   checkout, and run `scripts/live_release_check.py --secrets FILE` with that
   environment's interpreter. It logs in once per configured account, uses only
   allowlisted reads (no message opens, sends or read-once routes) and reports
   statuses and counts only. Publish only if it passes, and record the summary
   in the release notes. A failed step blocks publication; fix it in a new
   version rather than publishing a version that failed.
   Then run again from **main** with the same tag and `target=pypi`. This run builds its
   own sealed pair once, qualifies it, then waits for `pypi` environment approval.
   Inspect that run's tag, commit and results before approving. Bytes from an
   earlier verification run are not silently substituted into a later run.
5. Approve the publish job. Trusted Publishing uploads only that run's verified
   wheel/sdist with attestations. PyPI hashes and a fresh installed runtime smoke
   are checked afterward. A publication job is never run from a PR.
6. Record the public version, source commit and distribution hashes; create
   release notes from the versioned changelog. A GitHub Release is not the trigger
   for publication; the manual workflow is the explicit deployment boundary.

CLI equivalent after workflow deployment:

```sh
gh workflow run workflow.yaml --ref main -f tag=v1.0.0 -f target=verify
# After qualification and an explicit release decision:
gh workflow run workflow.yaml --ref main -f tag=v1.0.0 -f target=pypi
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
  Test tooling stays locked. Latest-runtime resolution is deliberately fresh.
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

Before upload, fix the failing gate and repeat verification. Do not waive a
failed platform matrix or remove an invariant just to get a release out.

If upload fails, check PyPI before rerunning. One of the two files may already
exist. PyPI versions/files cannot be overwritten; do not rebuild different bytes
and publish them under the same version. This pipeline intentionally does not
use `skip-existing`. Retain the sealed run artifact (14 days) and reconcile an
incomplete upload with the owner; a new version is the safe normal recovery.

If post-upload confirmation fails, the package may already be public. Inspect
the public JSON/version and original hashes first. Retry verification, not the
entire publisher, for temporary index visibility failures. A compromised/broken
release requires an explicit yank and corrected version. Never auto-delete a
release or reset user state; document a known-good dependency pin for rollback.

[pending]: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
