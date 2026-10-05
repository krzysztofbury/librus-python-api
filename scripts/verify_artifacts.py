"""Check actual release archive contents and user-facing package metadata."""

import sys
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from librus_python_api import __version__


def verify(directory: Path) -> None:
    (wheel,) = directory.glob("*.whl")
    (sdist,) = directory.glob("*.tar.gz")
    with zipfile.ZipFile(wheel) as archive:
        (metadata_path,) = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        metadata = BytesParser().parsebytes(archive.read(metadata_path))
        assert "librus_python_api/py.typed" in archive.namelist()
        assert all(
            name.startswith(
                ("librus_python_api/", f"librus_python_api-{__version__}.dist-info/")
            )
            for name in archive.namelist()
        )
    assert metadata["Version"] == __version__
    assert metadata["Requires-Python"] == ">=3.13"
    assert metadata["License-Expression"] == "MIT"
    requirements = metadata.get_all("Requires-Dist", [])
    assert not any("loguru" in value.lower() for value in requirements)
    assert {
        "Framework :: AsyncIO",
        "Operating System :: POSIX",
        "Development Status :: 4 - Beta",
    } <= set(metadata.get_all("Classifier", []))
    with tarfile.open(sdist) as archive:
        paths = {PurePosixPath(member.name) for member in archive.getmembers()}
        roots = {path.parts[0] for path in paths}
        assert len(roots) == 1
        allowed = {
            ".gitignore",  # Hatch includes VCS ignore rules in source archives.
            "src",
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "SECURITY.md",
            "API.md",
            "CHANGELOG.md",
            "LICENSE",
            "PKG-INFO",
        }
        unexpected = {
            path.parts[1]
            for path in paths
            if len(path.parts) >= 2 and path.parts[1] not in allowed
        }
        assert not unexpected, sorted(unexpected)
        assert not any(
            "__pycache__" in path.parts or path.suffix == ".pyc" for path in paths
        )
        assert any(
            path.parts[1:] == ("src", "librus_python_api", "py.typed") for path in paths
        )
    print(f"Verified {wheel.name} and {sdist.name}: metadata and lean archive contents")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
