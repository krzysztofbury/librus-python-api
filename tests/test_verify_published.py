"""Public registry identity and hashes must match the sealed distributions."""

from typing import Any

import pytest

from scripts.verify_published import check_publication, wait_for_simple_index


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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_simple_index_wait_returns_once_installers_can_see_both_files() -> None:
    listings = iter([set(), {"fixture.whl"}, {"fixture.whl", "fixture.tar.gz", "old"}])
    clock = FakeClock()
    polls = wait_for_simple_index(
        ["fixture.whl", "fixture.tar.gz"],
        fetch=lambda: next(listings),
        timeout=60,
        interval=15,
        clock=clock,
        sleep=clock.sleep,
    )
    assert polls == 3 and clock.now == 30


def test_simple_index_wait_is_bounded() -> None:
    clock = FakeClock()
    calls: list[float] = []

    def empty() -> set[str]:
        calls.append(clock.now)
        return set()

    with pytest.raises(TimeoutError):
        wait_for_simple_index(
            ["fixture.whl"],
            fetch=empty,
            timeout=60,
            interval=15,
            clock=clock,
            sleep=clock.sleep,
        )
    assert calls == [0, 15, 30, 45, 60]
