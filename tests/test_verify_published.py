"""Public registry identity and hashes must match the sealed distributions."""

from typing import Any

import pytest

from scripts.verify_published import check_publication


@pytest.mark.parametrize(
    "damage", [None, "version", "checksum", "extra", "missing", "yanked"]
)
def test_public_index_must_report_exact_non_yanked_archives(damage: str | None) -> None:
    manifest = {
        "version": "1.0.0",
        "files": {"fixture.whl": "a" * 64, "fixture.tar.gz": "b" * 64},
    }
    remote: dict[str, Any] = {
        "info": {"version": "1.0.0"},
        "urls": [
            {
                "filename": "fixture.whl",
                "digests": {"sha256": "a" * 64},
                "yanked": False,
            },
            {
                "filename": "fixture.tar.gz",
                "digests": {"sha256": "b" * 64},
                "yanked": False,
            },
        ],
    }
    if damage == "version":
        remote["info"]["version"] = "1.0.1"
    elif damage == "checksum":
        remote["urls"][0]["digests"]["sha256"] = "c" * 64
    elif damage == "extra":
        remote["urls"].append(
            {
                "filename": "unexpected.whl",
                "digests": {"sha256": "c" * 64},
                "yanked": False,
            }
        )
    elif damage == "missing":
        remote["urls"].pop()
    elif damage == "yanked":
        remote["urls"][0]["yanked"] = True
    if damage is None:
        check_publication(manifest, remote)
    else:
        with pytest.raises(ValueError):
            check_publication(manifest, remote)
