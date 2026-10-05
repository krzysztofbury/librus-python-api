"""Release publication refuses mismatched identities and tampered artifact bytes."""

import subprocess
from pathlib import Path

import pytest

from scripts.release_gate import check_identity, identity, seal, verify


@pytest.mark.parametrize(
    "tag,version,target",
    [
        ("v1.0.0rc1", "1.0.0rc1", "pypi"),
        ("v1.0.0", "1.0.0", "pypi"),
        ("v0.7.0", "0.7.0", "verify"),
    ],
)
def test_matching_remote_main_release_is_allowed(
    tag: str, version: str, target: str
) -> None:
    check_identity(tag, version, "a" * 40, "a" * 40, True, target)


@pytest.mark.parametrize(
    "change", ["version", "tag", "main", "remote", "zero", "target"]
)
def test_invalid_publication_identity_is_rejected(change: str) -> None:
    tag, version, target = "v1.0.0", "1.0.0", "pypi"
    if change == "version":
        version = "1.0.1"
    elif change == "tag":
        tag = "main"
    elif change == "zero":
        tag, version = "v0.7.0", "0.7.0"
    elif change == "target":
        target = "other"
    with pytest.raises(ValueError):
        check_identity(
            tag,
            version,
            "a" * 40,
            "b" * 40 if change == "remote" else "a" * 40,
            change != "main",
            target,
        )


@pytest.mark.parametrize("damage", [None, "wheel", "manifest", "extra", "missing"])
def test_sealed_artifacts_reject_changes(tmp_path: Path, damage: str | None) -> None:
    wheel = tmp_path / "librus_python_api-1.0.0-py3-none-any.whl"
    wheel.write_bytes(b"original fixture wheel")
    sdist = tmp_path / "librus_python_api-1.0.0.tar.gz"
    sdist.write_bytes(b"original fixture sdist")
    digest = seal(tmp_path, "1.0.0", "a" * 40)
    if damage == "wheel":
        wheel.write_bytes(b"altered fixture wheel")
    elif damage == "manifest":
        (tmp_path / "release-manifest.json").write_bytes(b"{}")
    elif damage == "extra":
        (tmp_path / "extra.whl").write_bytes(b"unexpected")
    elif damage == "missing":
        sdist.unlink()
    if damage is None:
        assert set(verify(tmp_path, digest)) == {wheel.name, sdist.name}
    else:
        with pytest.raises(ValueError):
            verify(tmp_path, digest)


@pytest.mark.parametrize("annotated", [False, True])
def test_release_identity_uses_real_remote_tag_and_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, annotated: bool
) -> None:
    remote, repo = tmp_path / "remote.git", tmp_path / "checkout"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    monkeypatch.chdir(repo)
    for field, value in (
        ("user.name", "Release Fixture"),
        ("user.email", "fixture@example.invalid"),
    ):
        subprocess.run(["git", "config", field, value], check=True)
    package = repo / "src/librus_python_api"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "1.0.0rc1"\n')
    (repo / "CHANGELOG.md").write_text("## 1.0.0rc1 (2026-10-05)\n")
    (repo / "contracts").mkdir()
    (repo / "contracts/upstream.openapi.yaml").write_text("version: 1.0.0rc1\n")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(
        ["git", "commit", "-m", "Original release fixture"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "remote", "add", "origin", str(remote)], check=True)
    tag = ["git", "tag", "v1.0.0rc1"]
    if annotated:
        tag.extend(["-m", "Original tag fixture"])
    subprocess.run(tag, check=True)
    subprocess.run(
        ["git", "push", "origin", "main", "v1.0.0rc1"], check=True, capture_output=True
    )
    assert identity("v1.0.0rc1", "pypi") == "1.0.0rc1"
    # A longer candidate version must not pass a substring match.
    contract = repo / "contracts/upstream.openapi.yaml"
    contract.write_text("version: 1.0.0rc10\n")
    with pytest.raises(ValueError, match="OpenAPI version differs"):
        identity("v1.0.0rc1", "pypi")
    contract.write_text("version: 1.0.0rc1\n")
    # A local source update must not qualify as the unchanged remote tag.
    (package / "__init__.py").write_text('__version__ = "1.0.0rc2"\n')
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(
        ["git", "commit", "-m", "Unreleased fixture"], check=True, capture_output=True
    )
    with pytest.raises(ValueError):
        identity("v1.0.0rc1", "pypi")
