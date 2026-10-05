"""Compare a public PyPI version with sealed archive hashes, without uploading."""

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def check_publication(manifest: dict[str, Any], remote: dict[str, Any]) -> None:
    version = manifest["version"]
    published = {item["filename"]: item["digests"]["sha256"] for item in remote["urls"]}
    if remote["info"]["version"] != version or published != manifest["files"]:
        raise ValueError("Published version/files differ from verified release")
    if any(item["yanked"] for item in remote["urls"]):
        raise ValueError("Published version is yanked")


def verify(directory: Path) -> str:
    manifest = json.loads((directory / "release-manifest.json").read_bytes())
    version = manifest["version"]
    with urlopen(
        f"https://pypi.org/pypi/librus-python-api/{version}/json", timeout=30
    ) as response:
        remote = json.load(response)
    check_publication(manifest, remote)
    print(f"PyPI confirms exact wheel and sdist checksums for {version}")
    return str(version)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    verify(parser.parse_args().directory)
