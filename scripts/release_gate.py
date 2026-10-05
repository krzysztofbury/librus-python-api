"""Release identity and immutable distribution manifest, with no upload authority."""

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

TAG = re.compile(r"v(\d+\.\d+\.\d+(?:rc[1-9]\d*)?)\Z")


def check_identity(
    tag: str, version: str, head: str, remote_tag: str, on_main: bool, target: str
) -> None:
    match = TAG.fullmatch(tag)
    if match is None or match[1] != version:
        raise ValueError("Tag must match package version exactly")
    if not re.fullmatch(r"[0-9a-f]{40}", head) or head != remote_tag or not on_main:
        raise ValueError("Release must be the remote tag on fetched remote main")
    if target not in {"verify", "pypi"}:
        raise ValueError("Unknown release target")
    if target != "verify" and int(version.partition(".")[0]) < 1:
        raise ValueError("Publishing starts at 1.0.0rc1")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def identity(tag: str, target: str) -> str:
    if TAG.fullmatch(tag) is None:
        raise ValueError("Invalid tag")
    # Re-read remote refs rather than trusting a local branch or tag.
    git(
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        f"refs/tags/{tag}",
    )
    remote = git("ls-remote", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    refs = dict(line.split()[::-1] for line in remote.splitlines())
    remote_tag = refs.get(f"refs/tags/{tag}^{{}}", refs.get(f"refs/tags/{tag}", ""))
    head = git("rev-parse", "HEAD")
    tree = ast.parse(Path("src/librus_python_api/__init__.py").read_text())
    (version,) = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(item, ast.Name) and item.id == "__version__"
            for item in node.targets
        )
    ]
    if not isinstance(version, str):
        raise ValueError("Package version must be a string literal")
    on_main = (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", head, "origin/main"], check=False
        ).returncode
        == 0
    )
    check_identity(tag, version, head, remote_tag, on_main, target)
    if f"## {version} (" not in Path("CHANGELOG.md").read_text():
        raise ValueError("Missing versioned changelog entry")
    if (
        re.search(
            rf"^\s*version: {re.escape(version)}\s*$",
            Path("contracts/upstream.openapi.yaml").read_text(),
            re.MULTILINE,
        )
        is None
    ):
        raise ValueError("OpenAPI version differs")
    print(f"Validated {tag} at remote commit {head}")
    return version


def seal(directory: Path, version: str, commit: str) -> str:
    expected = {
        f"librus_python_api-{version}-py3-none-any.whl",
        f"librus_python_api-{version}.tar.gz",
    }
    files = {item.name for item in directory.iterdir()}
    if files != expected:
        raise ValueError("Exactly the versioned wheel and sdist are required")
    data = {
        "version": version,
        "commit": commit,
        "files": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in sorted(expected)
        },
    }
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    (directory / "release-manifest.json").write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def verify(directory: Path, digest: str) -> dict[str, str]:
    payload = (directory / "release-manifest.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Manifest digest differs from build job")
    data = json.loads(payload)
    version = data["version"]
    expected = {
        f"librus_python_api-{version}-py3-none-any.whl",
        f"librus_python_api-{version}.tar.gz",
    }
    if set(data["files"]) != expected or {
        item.name for item in directory.iterdir()
    } != expected | {"release-manifest.json"}:
        raise ValueError("Unexpected artifact contents")
    for name, checksum in data["files"].items():
        if Path(name).name != name or (directory / name).is_symlink():
            raise ValueError("Unsafe distribution path")
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Distribution digest differs")
    return dict(data["files"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("identity", "seal", "verify"))
    parser.add_argument("--tag", default="")
    parser.add_argument("--target", default="verify")
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    parser.add_argument("--digest", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "identity":
        result = identity(args.tag, args.target)
    elif args.action == "seal":
        result = seal(
            args.directory, args.tag.removeprefix("v"), git("rev-parse", "HEAD")
        )
    else:
        verify(args.directory, args.digest)
        result = "verified"
    if args.output:
        with args.output.open("a") as output:
            output.write(f"{args.action}={result}\n")
