"""Compare a public PyPI version with sealed archive hashes, without uploading."""

import argparse
import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

SIMPLE_URL = "https://pypi.org/simple/librus-python-api/"
INDEX_WAIT_SECONDS = 600.0
INDEX_POLL_SECONDS = 15.0


def check_publication(manifest: dict[str, Any], remote: dict[str, Any]) -> None:
    version = manifest["version"]
    published = {item["filename"]: item["digests"]["sha256"] for item in remote["urls"]}
    if remote["info"]["version"] != version or published != manifest["files"]:
        raise ValueError("Published version/files differ from verified release")
    if any(item["yanked"] for item in remote["urls"]):
        raise ValueError("Published version is yanked")


def simple_index_files() -> set[str]:
    """Filenames the installer-facing simple index lists, bypassing caches."""
    request = Request(
        SIMPLE_URL,
        headers={
            "Accept": "application/vnd.pypi.simple.v1+json",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=30) as response:
        return {item["filename"] for item in json.load(response)["files"]}


def wait_for_simple_index(
    filenames: Iterable[str],
    *,
    fetch: Callable[[], set[str]] = simple_index_files,
    timeout: float = INDEX_WAIT_SECONDS,
    interval: float = INDEX_POLL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Poll until installers can see every file; the JSON API updates first.

    Returns the number of polls. A version the simple index never lists within
    the bound is a failed confirmation, not a reason to keep waiting.
    """
    wanted = set(filenames)
    deadline = clock() + timeout
    polls = 0
    while True:
        polls += 1
        if wanted <= fetch():
            return polls
        if clock() + interval > deadline:
            raise TimeoutError("PyPI simple index never listed the release files")
        sleep(interval)


def verify(directory: Path, *, wait_index: bool = False) -> str:
    manifest = json.loads((directory / "release-manifest.json").read_bytes())
    version = manifest["version"]
    with urlopen(
        f"https://pypi.org/pypi/librus-python-api/{version}/json", timeout=30
    ) as response:
        remote = json.load(response)
    check_publication(manifest, remote)
    print(f"PyPI confirms exact wheel and sdist checksums for {version}")
    if wait_index:
        polls = wait_for_simple_index(manifest["files"])
        print(f"PyPI simple index lists {version} after {polls} poll(s)")
    return str(version)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--wait-index",
        action="store_true",
        help="also wait (bounded) until the simple index lists both files",
    )
    args = parser.parse_args()
    verify(args.directory, wait_index=args.wait_index)
