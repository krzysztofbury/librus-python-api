"""Private local-NTFS guards using documented Win32 APIs, loaded on Windows only."""

import os
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import pywintypes
import win32api
import win32con
import win32file
import win32security
import winerror

from librus_python_api.exceptions import ErrorKind, LibrusError

_TRUSTED_SYSTEM_SIDS = {"S-1-5-18", "S-1-5-32-544"}
_MAX_PATH_COMPONENTS = 128
_MAX_ACES = 16


def _call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except pywintypes.error:
        raise OSError("Windows filesystem operation failed") from None


def _principal() -> tuple[str, str]:
    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
    )
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        owner = win32security.GetTokenInformation(token, win32security.TokenOwner)
        return win32security.ConvertSidToStringSid(
            user
        ), win32security.ConvertSidToStringSid(owner)
    finally:
        win32api.CloseHandle(token)


def _descriptor(native: int) -> int:
    if sys.platform == "win32":
        import msvcrt

        return msvcrt.open_osfhandle(native, os.O_RDWR | os.O_BINARY | os.O_NOINHERIT)
    raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _handle(descriptor: int) -> int:
    if sys.platform == "win32":
        import msvcrt

        return msvcrt.get_osfhandle(descriptor)
    raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _attributes(user: str) -> Any:
    descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        f"O:{user}D:P(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)",
        win32security.SDDL_REVISION_1,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    attributes.bInheritHandle = False
    return attributes


def _private(
    handle: Any, user: str, default_owner: str, *, directory: bool = False
) -> None:
    descriptor = win32security.GetSecurityInfo(
        handle,
        win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION
        | win32security.DACL_SECURITY_INFORMATION,
    )
    owner = win32security.ConvertSidToStringSid(descriptor.GetSecurityDescriptorOwner())
    if owner not in {user, default_owner}:
        raise LibrusError(ErrorKind.STORAGE)
    acl = descriptor.GetSecurityDescriptorDacl()
    if acl is None or not 1 <= acl.GetAceCount() <= _MAX_ACES:
        raise LibrusError(ErrorKind.STORAGE)
    trusted = _TRUSTED_SYSTEM_SIDS | {user}
    inheritable_user = False
    for index in range(acl.GetAceCount()):
        ace = acl.GetAce(index)
        if ace[0][0] != win32security.ACCESS_ALLOWED_ACE_TYPE or len(ace) != 3:
            raise LibrusError(ErrorKind.STORAGE)
        if win32security.ConvertSidToStringSid(ace[2]) not in trusted:
            raise LibrusError(ErrorKind.STORAGE)
        if (
            win32security.ConvertSidToStringSid(ace[2]) == user
            and ace[0][1] & 3 == 3  # OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
            and not ace[0][1] & 4  # NO_PROPAGATE_INHERIT_ACE
            and ace[1] & 0x1F01FF == 0x1F01FF  # FILE_ALL_ACCESS
        ):
            inheritable_user = True
    if directory and (
        not descriptor.GetSecurityDescriptorControl()[0] & 0x1000  # SE_DACL_PROTECTED
        or not inheritable_user
    ):
        # SQLite creates its own journal files. A private directory without an
        # inheritable ACL can give those files the process's broader default DACL.
        raise LibrusError(ErrorKind.STORAGE)


def _path_boundary(path: Path) -> None:
    if (
        not path.is_absolute()
        or len(path.parts) > _MAX_PATH_COMPONENTS
        or len(str(path)) > 4096
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if (
        len(path.drive) != 2
        or path.drive[1] != ":"
        or not path.drive[0].isascii()
        or not path.drive[0].isalpha()
    ):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    if any(
        part in {".", ".."} or ":" in part or part.endswith((" ", "."))
        for part in path.parts[1:]
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    root = path.anchor
    if win32file.GetDriveType(root) != win32con.DRIVE_FIXED:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    volume = win32api.GetVolumeInformation(root)
    if volume[4].upper() != "NTFS" or not volume[3] & win32con.FILE_PERSISTENT_ACLS:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _pin(path: Path, *, private: bool) -> Any:
    handle = win32file.CreateFile(
        str(path),
        (win32con.READ_CONTROL if private else 0) | 0x80,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
        None,
        win32con.OPEN_EXISTING,
        win32con.FILE_FLAG_BACKUP_SEMANTICS | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    try:
        information = win32file.GetFileInformationByHandle(int(handle))
        if (
            not information[0] & win32con.FILE_ATTRIBUTE_DIRECTORY
            or information[0] & win32con.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise LibrusError(ErrorKind.STORAGE)
        return handle
    except BaseException:
        handle.Close()
        raise


class WindowsDirectory:
    """Pin a private directory against rename/delete while owning its child handles."""

    def __init__(self, path: Path, *, create: bool) -> None:
        self.path = path
        self._handle: Any = None
        self._parents: list[Any] = []
        self._user, self._owner = _call(_principal)
        _call(lambda: _path_boundary(path))
        try:
            # Pin top-down before opening any child by path. Checking ancestors
            # without retaining their handles leaves an ancestor-rename race.
            for parent in reversed(path.parents):
                self._parents.append(_call(partial(_pin, parent, private=False)))
            if create:
                try:
                    win32file.CreateDirectory(str(path), _attributes(self._user))
                except pywintypes.error as error:
                    if error.winerror != winerror.ERROR_ALREADY_EXISTS:
                        raise OSError("Windows directory creation failed") from None
            self._handle = _call(lambda: _pin(path, private=True))
            self.validate()
        except BaseException:
            self.close()
            raise

    def validate(self) -> None:
        assert self._handle is not None
        information = _call(lambda: win32file.GetFileInformationByHandle(self._handle))
        if (
            not information[0] & win32con.FILE_ATTRIBUTE_DIRECTORY
            or information[0] & win32con.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise LibrusError(ErrorKind.STORAGE)
        actual = _call(lambda: win32file.GetFinalPathNameByHandle(self._handle, 0))
        if os.path.normcase(actual.removeprefix("\\\\?\\")) != os.path.normcase(
            str(self.path)
        ):
            raise LibrusError(ErrorKind.STORAGE)
        _call(lambda: _private(self._handle, self._user, self._owner, directory=True))

    def close(self) -> None:
        handles = [*reversed(self._parents)]
        if self._handle is not None:
            handles.insert(0, self._handle)
        self._parents.clear()
        self._handle = None
        failed = False
        for handle in handles:
            try:
                _call(handle.Close)
            except OSError:
                failed = True
        if failed:
            raise OSError("Windows directory handle cleanup failed")

    def open_file(
        self, name: str, *, create: bool = False, exclusive: bool = False
    ) -> int:
        if (
            type(name) is not str
            or not name
            or Path(name).name != name
            or any(c in name for c in "\\/:")
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self.validate()
        disposition = (
            win32con.CREATE_NEW
            if exclusive
            else win32con.OPEN_ALWAYS
            if create
            else win32con.OPEN_EXISTING
        )
        handle = _call(
            lambda: win32file.CreateFile(
                str(self.path / name),
                win32con.GENERIC_READ
                | win32con.GENERIC_WRITE
                | win32con.READ_CONTROL
                | (win32con.DELETE if exclusive else 0),
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                _attributes(self._user) if create or exclusive else None,
                disposition,
                win32con.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        )
        detached = False
        try:
            information = _call(
                lambda: win32file.GetFileInformationByHandle(int(handle))
            )
            if (
                information[0]
                & (
                    win32con.FILE_ATTRIBUTE_DIRECTORY
                    | win32con.FILE_ATTRIBUTE_REPARSE_POINT
                )
                or information[7] != 1
                or _call(lambda: win32file.GetFileType(int(handle)))
                != win32con.FILE_TYPE_DISK
            ):
                raise LibrusError(ErrorKind.STORAGE)
            _call(lambda: _private(handle, self._user, self._owner))
            native = int(handle.Detach())
            detached = True
            try:
                return _descriptor(native)
            except BaseException:
                win32api.CloseHandle(native)
                raise
        finally:
            if not detached:
                handle.Close()

    def check_file(
        self, name: str, maximum: int, *, create: bool = False
    ) -> tuple[int, int]:
        descriptor = self.open_file(name, create=create)
        try:
            information = _call(
                lambda: win32file.GetFileInformationByHandle(_handle(descriptor))
            )
            if ((information[5] << 32) | information[6]) > maximum:
                raise LibrusError(ErrorKind.STORAGE)
            return information[4], (information[8] << 32) | information[9]
        finally:
            os.close(descriptor)

    def check_sidecar(self, name: str, maximum: int) -> None:
        # A private pinned parent excludes other OS principals from replacement.
        # Same-user writers remain outside the threat boundary on both platforms.
        try:
            (self.path / name).lstat()
        except FileNotFoundError:
            return
        self.check_file(name, maximum)


def acquire_lock(directory: WindowsDirectory, name: str, held: list[int]) -> None:
    descriptor = directory.open_file(name, create=True)
    try:
        if os.fstat(descriptor).st_size != 0:
            raise LibrusError(ErrorKind.STORAGE)
        try:
            win32file.LockFileEx(
                _handle(descriptor),
                win32con.LOCKFILE_EXCLUSIVE_LOCK | win32con.LOCKFILE_FAIL_IMMEDIATELY,
                1,
                0,
                pywintypes.OVERLAPPED(),
            )
        except pywintypes.error as error:
            if error.winerror == winerror.ERROR_LOCK_VIOLATION:
                raise LibrusError(ErrorKind.LIMIT) from None
            raise OSError("Windows context lock failed") from None
        held.append(descriptor)
        descriptor = -1
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def release_lock(descriptor: int) -> None:
    try:
        _call(
            lambda: win32file.UnlockFileEx(
                _handle(descriptor), 1, 0, pywintypes.OVERLAPPED()
            )
        )
    finally:
        os.close(descriptor)


def publish_file(
    directory: WindowsDirectory, descriptor: int, name: str, attempts: int
) -> str:
    """Rename the complete owned file by handle; never replace a destination."""
    directory.validate()
    os.fsync(descriptor)
    path = Path(name)
    for index in range(attempts):
        candidate = name if index == 0 else f"{path.stem} ({index}){path.suffix}"
        try:
            win32file.SetFileInformationByHandle(
                _handle(descriptor),
                win32file.FileRenameInfo,
                {
                    "ReplaceIfExists": False,
                    "RootDirectory": None,
                    "FileName": str(directory.path / candidate),
                },
            )
        except pywintypes.error as error:
            if error.winerror in (
                winerror.ERROR_ALREADY_EXISTS,
                winerror.ERROR_FILE_EXISTS,
            ):
                continue
            # NTFS can report ACCESS_DENIED for an existing directory or link.
            # This check only decides whether to try another name after a failed
            # no-replace commit; it never authorizes replacement.
            if error.winerror == winerror.ERROR_ACCESS_DENIED and os.path.lexists(
                directory.path / candidate
            ):
                continue
            raise OSError("Windows publication failed") from None
        os.fsync(descriptor)
        return candidate
    raise LibrusError(ErrorKind.LIMIT)
