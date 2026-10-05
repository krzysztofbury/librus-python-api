"""Mandatory real NTFS, ACL and reparse-point boundaries on Windows runners."""

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, cast

import pytest

from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.files import prepare_attachment_directory, publish_attachment
from librus_python_api.persistence import NotificationStore, PersistenceStore
from tests.attachments_support import reference, rig
from tests.test_notification_persistence import offline_service

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Requires real Windows NTFS"
)


def junction(link: Path, target: Path) -> None:
    subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
    )
    assert link.is_junction()


def allow_everyone(path: Path) -> None:
    import win32con
    import win32security

    everyone = win32security.ConvertStringSidToSid("S-1-1-0")
    descriptor = win32security.GetNamedSecurityInfo(
        str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
    )
    acl = descriptor.GetSecurityDescriptorDacl()
    assert acl is not None
    acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_READ, everyone)
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION
        | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None,
        None,
        acl,
        None,
    )


def assert_private(path: Path) -> None:
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
    )
    try:
        user = win32security.ConvertSidToStringSid(
            win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        )
    finally:
        win32api.CloseHandle(token)
    descriptor = win32security.GetNamedSecurityInfo(
        str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
    )
    acl = descriptor.GetSecurityDescriptorDacl()
    assert acl is not None
    assert {
        win32security.ConvertSidToStringSid(acl.GetAce(i)[2])
        for i in range(acl.GetAceCount())
    } <= {user, "S-1-5-18", "S-1-5-32-544"}


@pytest.mark.parametrize(
    "damage",
    [
        "directory_acl",
        "directory_no_inheritance",
        "database_acl",
        "database_hardlink",
        "sidecar_acl",
        "directory_junction",
        "ancestor_junction",
    ],
)
def test_unsafe_storage_is_rejected_without_modifying_originals(
    tmp_path: Path, damage: str
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "state"
        async with PersistenceStore(directory):
            pass
        database = directory / "state.sqlite3"
        assert_private(directory)
        assert_private(database)
        if damage == "directory_acl":
            allow_everyone(directory)
        elif damage == "directory_no_inheritance":
            import win32security

            descriptor = win32security.GetNamedSecurityInfo(
                str(directory),
                win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION,
            )
            old = descriptor.GetSecurityDescriptorDacl()
            assert old is not None
            acl = win32security.ACL()
            for index in range(old.GetAceCount()):
                ace = old.GetAce(index)
                acl.AddAccessAllowedAce(win32security.ACL_REVISION, ace[1], ace[2])
            win32security.SetNamedSecurityInfo(
                str(directory),
                win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION
                | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                acl,
                None,
            )
        elif damage == "database_acl":
            allow_everyone(database)
        elif damage == "database_hardlink":
            os.link(database, tmp_path / "linked-database")
        elif damage == "sidecar_acl":
            sidecar = directory / "state.sqlite3-journal"
            sidecar.write_bytes(b"Original sidecar fixture")
            allow_everyone(sidecar)
        elif damage == "directory_junction":
            original = tmp_path / "original"
            directory.rename(original)
            junction(directory, original)
        else:
            alias = tmp_path / "alias"
            junction(alias, tmp_path)
            directory = alias / "state"
        before = database.read_bytes()
        with pytest.raises(LibrusError) as error:
            async with PersistenceStore(directory):
                pass
        assert error.value.kind is ErrorKind.STORAGE
        assert database.read_bytes() == before
        # Failed opens release every pinned parent/directory handle.
        if damage not in {"directory_junction", "ancestor_junction"}:
            directory.rename(tmp_path / "after-failed-open")

    asyncio.run(scenario())


@pytest.mark.parametrize("target", ["directory", "ancestor", "unprivate"])
def test_publication_rejects_unsafe_destination_before_http(
    tmp_path: Path, target: str
) -> None:
    async def scenario() -> None:
        private = tmp_path / "private"
        await prepare_attachment_directory(private)
        if target == "directory":
            destination = tmp_path / "junction"
            junction(destination, private)
        elif target == "ancestor":
            alias = tmp_path / "alias"
            junction(alias, tmp_path)
            destination = alias / "private"
        else:
            allow_everyone(private)
            destination = private
        async with rig() as (fixture, service):
            with pytest.raises(LibrusError) as error:
                await publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    destination,
                    filename="fixture.txt",
                )
            assert error.value.kind is ErrorKind.STORAGE
            assert fixture.calls == [] and fixture.downloads == []
        assert list(private.iterdir()) == []

    asyncio.run(scenario())


def test_reparse_collision_is_not_overwritten_and_final_acl_is_private(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "private"
        await prepare_attachment_directory(directory)
        target = tmp_path / "untouched"
        target.mkdir()
        (target / "original").write_bytes(b"Keep original fixture")
        junction(directory / "fixture.txt", target)
        async with rig() as (fixture, service):
            result = await publish_attachment(
                service.account("student").stream_attachment(reference()),
                directory,
                filename="fixture.txt",
            )
            assert result.path == directory / "fixture (1).txt"
            assert result.path.read_bytes() == fixture.body
            assert_private(result.path)
        assert (target / "original").read_bytes() == b"Keep original fixture"
        assert (directory / "fixture.txt").is_junction()
        directory.rename(tmp_path / "after-publication")

    asyncio.run(scenario())


def test_private_parent_stays_pinned_until_store_close(tmp_path: Path) -> None:
    async def scenario() -> None:
        parent = tmp_path / "parent"
        parent.mkdir()
        async with NotificationStore(parent / "state"):
            with pytest.raises(OSError):
                parent.rename(tmp_path / "moved")
        parent.rename(tmp_path / "moved")
        assert (tmp_path / "moved" / "state" / "notifications.sqlite3").is_file()

    asyncio.run(scenario())


def test_failure_validating_new_temp_deletes_only_the_owned_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import win32file
    import win32security

    original = win32security.GetSecurityInfo

    def fail_temp(handle: Any, *args: Any) -> Any:
        name = win32file.GetFinalPathNameByHandle(int(handle), 0)
        if ".librus-attachment-" in name:
            raise OSError("Original fixture ACL-query failure")
        return original(handle, *args)

    async def scenario() -> None:
        directory = tmp_path / "private"
        await prepare_attachment_directory(directory)
        (directory / "original.txt").write_bytes(b"Keep original fixture")
        monkeypatch.setattr(win32security, "GetSecurityInfo", fail_temp)
        async with rig() as (fixture, service):
            with pytest.raises(LibrusError) as error:
                await publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    directory,
                    filename="original.txt",
                )
            assert error.value.kind is ErrorKind.STORAGE
            assert fixture.calls == [] and fixture.downloads == []
        assert list(directory.glob(".librus-attachment-*")) == []
        assert (directory / "original.txt").read_bytes() == b"Keep original fixture"
        directory.rename(tmp_path / "after-failure")

    asyncio.run(scenario())


def test_commit_point_cancellation_preserves_complete_file_and_releases_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import win32file

    entered, release = threading.Event(), threading.Event()
    original = win32file.SetFileInformationByHandle

    def after_commit(*args: Any) -> Any:
        result = original(*args)
        entered.set()
        if not release.wait(5):
            raise TimeoutError("Original fixture commit barrier")
        return result

    monkeypatch.setattr(win32file, "SetFileInformationByHandle", after_commit)

    async def scenario() -> None:
        directory = tmp_path / "private"
        await prepare_attachment_directory(directory)
        async with rig() as (fixture, service):
            task = asyncio.create_task(
                publish_attachment(
                    service.account("student").stream_attachment(reference()),
                    directory,
                    filename="fixture.txt",
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                for _ in range(4):
                    task.cancel()
                    await asyncio.sleep(0)
                assert not task.done()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (directory / "fixture.txt").read_bytes() == fixture.body
            assert list(directory.glob(".librus-attachment-*")) == []
            assert_private(directory / "fixture.txt")
        directory.rename(tmp_path / "after-cancellation")

    asyncio.run(scenario())


@pytest.mark.parametrize("capability", ["filesystem", "drive", "acl_support"])
def test_unsupported_volume_capability_stops_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capability: str
) -> None:
    import win32api
    import win32con
    import win32file

    original = win32api.GetVolumeInformation

    def volume(root: str) -> Any:
        info = list(original(root))
        if capability == "filesystem":
            info[4] = "FAT32"
        else:
            info[3] = cast(int, info[3]) & ~win32con.FILE_PERSISTENT_ACLS
        return tuple(info)

    if capability == "drive":
        monkeypatch.setattr(win32file, "GetDriveType", lambda _: win32con.DRIVE_REMOTE)
    else:
        monkeypatch.setattr(win32api, "GetVolumeInformation", volume)

    async def scenario() -> None:
        directory = tmp_path / "uncreated"
        with pytest.raises(LibrusError) as error:
            async with NotificationStore(directory):
                pass
        assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
        assert not directory.exists()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", [NotificationStore, PersistenceStore])
def test_network_namespace_is_unsupported_before_creating_files(kind: Any) -> None:
    async def scenario() -> None:
        with pytest.raises(LibrusError) as error:
            async with kind(Path(r"\\localhost\C$\librus-original-fixture")):
                pass
        assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY

    asyncio.run(scenario())


@pytest.mark.parametrize("name", ["CON", "COM¹", "alias:stream", "trailing."])
def test_ambiguous_windows_path_is_invalid_before_creating_files(
    tmp_path: Path, name: str
) -> None:
    async def scenario() -> None:
        with pytest.raises(LibrusError) as error:
            await prepare_attachment_directory(tmp_path / name)
        assert error.value.kind is ErrorKind.INVALID_INPUT

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["acl", "junction"])
def test_notification_lock_validation_stops_before_reading_or_network(
    tmp_path: Path, damage: str
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "state"
        async with offline_service("http://127.0.0.1:9") as service:
            context = service.account("student").context
            async with NotificationStore(directory) as store:
                # State lookup exercises supported per-context exclusion.
                await store.state(context=context)
            lock = next(directory.glob("notification-*.lock"))
            if damage == "acl":
                allow_everyone(lock)
            else:
                lock.unlink()
                target = tmp_path / "untouched"
                target.mkdir()
                junction(lock, target)
            async with NotificationStore(directory) as store:
                with pytest.raises(LibrusError) as error:
                    await store.state(context=context)
                assert error.value.kind is ErrorKind.STORAGE
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())
