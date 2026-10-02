"""Private live captures must never land inside this public repository."""

from pathlib import Path

import pytest

from scripts.live_capture import REPOSITORY, private_directory


@pytest.mark.parametrize("inside", [REPOSITORY, REPOSITORY / "captures" / "run"])
def test_capture_directory_inside_repository_is_refused(inside: Path) -> None:
    with pytest.raises(SystemExit):
        private_directory(inside)
    assert not (REPOSITORY / "captures").exists()


def test_capture_directory_inside_any_git_work_tree_is_refused(tmp_path: Path) -> None:
    (tmp_path / "other-repo" / ".git").mkdir(parents=True)
    with pytest.raises(SystemExit):
        private_directory(tmp_path / "other-repo" / "captures")
    assert not (tmp_path / "other-repo" / "captures").exists()


def test_capture_directory_is_new_and_owner_only(tmp_path: Path) -> None:
    created = private_directory(tmp_path / "run")
    assert created.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        private_directory(tmp_path / "run")
