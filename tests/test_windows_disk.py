"""Mandatory real NTFS, ACL and reparse-point boundaries on Windows runners."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.files import publish_attachment
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
    from librus_python_api._windows_filesystem import WindowsDirectory

    async def scenario() -> None:
        private = tmp_path / "private"
        WindowsDirectory(private, create=True).close()
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
    from librus_python_api._windows_filesystem import WindowsDirectory

    async def scenario() -> None:
        directory = tmp_path / "private"
        WindowsDirectory(directory, create=True).close()
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


@pytest.mark.parametrize("kind", [NotificationStore, PersistenceStore])
def test_network_namespace_is_unsupported_before_creating_files(kind: Any) -> None:
    async def scenario() -> None:
        with pytest.raises(LibrusError) as error:
            async with kind(Path(r"\\localhost\C$\librus-original-fixture")):
                pass
        assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["acl", "junction"])
def test_notification_lock_validation_stops_before_registration_work(
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
