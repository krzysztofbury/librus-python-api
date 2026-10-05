"""Local publication proofs using the real bounded HTTP attachment stream."""

import asyncio
import hashlib
import os
import sys
import threading
from pathlib import Path

import pytest

from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.files import (
    prepare_attachment_directory,
    publish_attachment,
    safe_attachment_filename,
)
from tests.attachments_support import reference, rig


@pytest.fixture
def tmp_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("publication")
    if sys.platform == "win32":
        root = root / "private"
        asyncio.run(prepare_attachment_directory(root))
    return root


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("../report.txt", "report.txt"),
        (r"C:\private\report.txt", "report.txt"),
        (" .hidden\x00.txt ", "hidden_.txt"),
        ("...", "attachment"),
        ("CON.txt", "_CON.txt"),
        ("COM¹.txt", "_COM¹.txt"),
        ("file\u202ename.txt", "file_name.txt"),
        ("fixture α.txt", "fixture α.txt"),
    ],
)
def test_filename_is_a_bounded_portable_basename(original: str, expected: str) -> None:
    assert safe_attachment_filename(original) == expected
    assert len(safe_attachment_filename("α" * 1024).encode()) <= 180


def test_explicit_private_directory_preparation_is_inert_until_called(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        destination = tmp_path / "private-new"
        assert not destination.exists()
        await prepare_attachment_directory(destination)
        await prepare_attachment_directory(destination)
        assert destination.is_dir() and list(destination.iterdir()) == []
        with pytest.raises(LibrusError) as error:
            await prepare_attachment_directory(Path("relative-fixture"))
        assert error.value.kind is ErrorKind.INVALID_INPUT
        if sys.platform != "win32":
            assert destination.stat().st_mode & 0o777 == 0o700
            destination.chmod(0o755)
            with pytest.raises(LibrusError) as error:
                await prepare_attachment_directory(destination)
            assert error.value.kind is ErrorKind.STORAGE
            assert destination.stat().st_mode & 0o777 == 0o755

    asyncio.run(scenario())


def test_publication_never_overwrites_files_or_symlink_targets(tmp_path: Path) -> None:
    async def scenario() -> None:
        existing = tmp_path / "report.txt"
        existing.write_bytes(b"keep existing")
        if sys.platform == "win32":
            # An NTFS directory collision needs no symlink privilege. Real
            # reparse-point targets are separately required by Windows tests.
            (tmp_path / "report (1).txt").mkdir()
        else:
            (tmp_path / "report (1).txt").symlink_to(existing)
        async with rig() as (fixture, service):
            result = await publish_attachment(
                service.account("student").stream_attachment(reference()),
                tmp_path,
                filename="../../report.txt",
            )
            assert result.path == tmp_path / "report (2).txt"
            assert result.path.read_bytes() == fixture.body
            assert result.size_bytes == len(fixture.body)
            assert result.sha256 == hashlib.sha256(fixture.body).hexdigest()
            if sys.platform != "win32":
                assert result.path.stat().st_mode & 0o777 == 0o600
            assert "report" not in repr(result)
            assert fixture.downloads and "Cookie" not in fixture.downloads[0]
        assert existing.read_bytes() == b"keep existing"
        assert sorted(os.listdir(tmp_path)) == [
            "report (1).txt",
            "report (2).txt",
            "report.txt",
        ]

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["truncated", "size", "cancel"])
def test_incomplete_stream_never_publishes_and_cleans_owned_temp(
    tmp_path: Path, failure: str
) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            fixture.declared = len(fixture.body) + 1 if failure == "truncated" else None
            fixture.truncate = failure == "truncated"
            if failure == "cancel":
                fixture.body_hold = asyncio.Event()
            task = asyncio.create_task(
                publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    tmp_path,
                    filename="fixture.txt",
                    max_bytes=1 if failure == "size" else 1024,
                )
            )
            if failure == "cancel":
                await fixture.body_started.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(LibrusError):
                    await task
            assert os.listdir(tmp_path) == []
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_concurrent_publications_are_complete_unique_and_bounded(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        aliases = tuple(f"fixture-{i}" for i in range(4))
        async with rig(aliases) as (fixture, service):
            fixture.body = b"x" * 131072
            results = await asyncio.gather(
                *(
                    publish_attachment(
                        service.account(alias).stream_attachment(reference(alias)),
                        tmp_path,
                        filename="fixture.bin",
                    )
                    for alias in aliases
                )
            )
            assert len({result.path for result in results}) == 4
            assert all(result.path.read_bytes() == fixture.body for result in results)
            assert len(os.listdir(tmp_path)) == 4
            assert len(fixture.downloads) == 4

    asyncio.run(scenario())


def test_repeated_cancellation_joins_disk_write_before_temp_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release, finished = (threading.Event() for _ in range(3))
    original = os.write

    def slow_write(descriptor: int, chunk: bytes | memoryview) -> int:
        started.set()
        assert release.wait(5)
        try:
            return original(descriptor, chunk)
        finally:
            finished.set()

    monkeypatch.setattr(os, "write", slow_write)

    async def scenario() -> None:
        async with rig() as (_, service):
            task = asyncio.create_task(
                publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    tmp_path,
                    filename="fixture.txt",
                )
            )
            try:
                for _ in range(1000):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.001)
                assert started.is_set()
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                assert not finished.is_set() and not task.done()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set() and os.listdir(tmp_path) == []

    asyncio.run(scenario())


def test_disk_failure_is_redacted_and_does_not_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_write(descriptor: int, chunk: bytes | memoryview) -> int:
        raise OSError("private filename and local filesystem details")

    monkeypatch.setattr(os, "write", fail_write)

    async def scenario() -> None:
        async with rig() as (_, service):
            with pytest.raises(LibrusError) as error:
                await publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    tmp_path,
                    filename="fixture.txt",
                )
            assert error.value.kind is ErrorKind.STORAGE
            assert str(error.value) == "storage" and error.value.__suppress_context__
            assert os.listdir(tmp_path) == []

    asyncio.run(scenario())


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX symlink; NTFS junction tested separately"
)
def test_directory_symlink_is_rejected_before_network(tmp_path: Path) -> None:
    async def scenario() -> None:
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target, target_is_directory=True)
        async with rig() as (fixture, service):
            with pytest.raises(LibrusError) as error:
                await publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    link,
                    filename="fixture.txt",
                )
            assert error.value.kind is ErrorKind.STORAGE
            assert fixture.calls == [] and fixture.downloads == []

    asyncio.run(scenario())


@pytest.mark.parametrize("flag", ["O_DIRECTORY", "O_NOFOLLOW"])
@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX open flags; Windows uses handles"
)
def test_platform_without_safe_open_flags_is_unsupported_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    # Without these flags the directory/symlink guarantees cannot hold, so the
    # call must fail with a typed error instead of a raw AttributeError.
    monkeypatch.delattr(os, flag)

    async def scenario() -> None:
        async with rig() as (fixture, service):
            with pytest.raises(LibrusError) as error:
                await publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    tmp_path,
                    filename="fixture.txt",
                )
            assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
            assert fixture.calls == [] and fixture.downloads == []
        assert os.listdir(tmp_path) == []

    asyncio.run(scenario())
