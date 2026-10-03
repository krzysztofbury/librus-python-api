"""Private bounded SQLite ownership shared by explicit optional stores."""

import asyncio
import contextvars
import os
import sqlite3
import stat
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self

from pydantic import Field

from librus_python_api.config import _ValidatedConfig
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.lifecycle import join_owned


class _StorageLimits(_ValidatedConfig):
    operations: int = Field(default=8, ge=1, le=64)
    busy_timeout_seconds: float = Field(default=0.1, gt=0, le=5, allow_inf_nan=False)
    # Final saves follow upstream side effects (a dispatched send or a consumed
    # read-once page), so they wait longer for other contexts' write locks.
    final_busy_timeout_seconds: float = Field(
        default=5, gt=0, le=60, allow_inf_nan=False
    )


# Worker threads inherit the calling task's context through asyncio.to_thread.
_busy_timeout_seconds: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "_busy_timeout_seconds", default=None
)


class _SQLiteStore:
    _filename = "state.sqlite3"
    _database_bytes = 8 * 1024 * 1024
    _schema: tuple[str, ...] = ()

    def __init__(self, directory: Path, *, limits: _StorageLimits) -> None:
        if not isinstance(directory, Path) or not directory.is_absolute():
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._directory = directory
        self._path = directory / self._filename
        self._storage_limits = limits
        self._opened = self._opening = self._closing = self._closed = False
        self._operations = 0
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._workflows: set[asyncio.Task[Any]] = set()
        self._close_task: asyncio.Task[None] | None = None
        self._file_identity: tuple[int, int] | None = None

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def open(self) -> None:
        if self._opened or self._opening or self._closing or self._closed:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._opening = True
        try:
            await self._io(self._initialise, opening=True)
            self._opened = True
        finally:
            self._opening = False

    async def aclose(self) -> None:
        if (
            asyncio.current_task() in self._tasks
            or asyncio.current_task() in self._workflows
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        if self._close_task is None:
            self._closing = True
            self._close_task = asyncio.create_task(self._close())
        interrupted = await join_owned(self._close_task)
        self._close_task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _close(self) -> None:
        # Join workflow-owned final saves before cancelling ordinary workers.
        for task in tuple(self._workflows):
            task.cancel()
        for task in tuple(self._workflows):
            await join_owned(task)
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            await join_owned(task)
        self._closed = True
        self._opened = False

    async def _owned[T](self, operation: Callable[[], Coroutine[Any, Any, T]]) -> T:
        if not self._opened or self._closing or self._closed:
            raise LibrusError(ErrorKind.CLOSED)
        if len(self._workflows) >= self._storage_limits.operations:
            raise LibrusError(ErrorKind.LIMIT)
        task = asyncio.create_task(operation())
        self._workflows.add(task)
        cancelled = False
        try:
            await asyncio.wait((task,))
            return task.result()
        except asyncio.CancelledError:
            cancelled = True
            task.cancel()
            raise
        finally:
            interrupted = await join_owned(task)
            self._workflows.discard(task)
            if cancelled or interrupted:
                raise asyncio.CancelledError

    async def _io[T](
        self,
        operation: Callable[[], T],
        *,
        opening: bool = False,
        finishing: bool = False,
    ) -> T:
        if (
            self._closed
            or (not self._opened and not opening)
            or (self._closing and not finishing)
        ):
            raise LibrusError(ErrorKind.CLOSED)
        if self._operations >= self._storage_limits.operations:
            raise LibrusError(ErrorKind.LIMIT)
        self._operations += 1
        task = asyncio.create_task(
            self._worker(
                operation,
                self._storage_limits.final_busy_timeout_seconds
                if finishing
                else self._storage_limits.busy_timeout_seconds,
            )
        )
        self._tasks.add(task)
        cancelled = False
        try:
            await asyncio.wait((task,))
            return task.result()
        except asyncio.CancelledError:
            cancelled = True
            # Final saves remain owned even while waiting for another worker.
            if not finishing:
                task.cancel()
            raise
        finally:
            interrupted = await join_owned(task)
            self._tasks.discard(task)
            self._operations -= 1
            if cancelled or interrupted:
                raise asyncio.CancelledError

    async def _worker[T](self, operation: Callable[[], T], busy_seconds: float) -> T:
        async with self._lock:
            _busy_timeout_seconds.set(busy_seconds)
            task = asyncio.create_task(asyncio.to_thread(operation))
            interrupted = await join_owned(task)
            if interrupted:
                raise asyncio.CancelledError
            try:
                return task.result()
            except LibrusError:
                raise
            except Exception:
                pass
        raise LibrusError(ErrorKind.STORAGE)

    def _check_directory(self) -> None:
        # A private immediate parent is the trust boundary. Malicious same-user
        # filesystem writers and unsuitable network filesystems are not isolated.
        if self._directory.is_symlink():
            raise LibrusError(ErrorKind.STORAGE)
        self._directory.mkdir(mode=0o700, exist_ok=True)
        status = self._directory.stat()
        if not stat.S_ISDIR(status.st_mode):
            raise LibrusError(ErrorKind.STORAGE)
        if os.name == "posix" and (
            status.st_uid != os.geteuid() or stat.S_IMODE(status.st_mode) & 0o077
        ):
            raise LibrusError(ErrorKind.STORAGE)

    def _check_file(self, *, create: bool = False) -> None:
        if self._path.is_symlink():
            raise LibrusError(ErrorKind.STORAGE)
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if create:
            flags |= os.O_CREAT
        descriptor = os.open(self._path, flags, 0o600)
        try:
            status = os.fstat(descriptor)
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_nlink != 1
                or status.st_size > self._database_bytes
            ):
                raise LibrusError(ErrorKind.STORAGE)
            if os.name == "posix" and (
                status.st_uid != os.geteuid() or stat.S_IMODE(status.st_mode) & 0o077
            ):
                raise LibrusError(ErrorKind.STORAGE)
            identity = (status.st_dev, status.st_ino)
            if self._file_identity is not None and self._file_identity != identity:
                raise LibrusError(ErrorKind.STORAGE)
            self._file_identity = identity
        finally:
            os.close(descriptor)

    def _check_sidecars(self) -> None:
        for suffix in ("-journal", "-wal", "-shm"):
            path = self._path.with_name(self._path.name + suffix)
            try:
                status = path.lstat()
            except FileNotFoundError:
                continue
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_nlink != 1
                or status.st_size > self._database_bytes + 1024 * 1024
                or (
                    os.name == "posix"
                    and (
                        status.st_uid != os.geteuid()
                        or stat.S_IMODE(status.st_mode) & 0o077
                    )
                )
            ):
                raise LibrusError(ErrorKind.STORAGE)

    @contextmanager
    def _connection(self, *, initialise: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        kind: ErrorKind | None = None
        try:
            self._check_directory()
            self._check_file(create=initialise)
            self._check_sidecars()
            busy_seconds = _busy_timeout_seconds.get()
            connection = sqlite3.connect(
                self._path,
                timeout=self._storage_limits.busy_timeout_seconds
                if busy_seconds is None
                else busy_seconds,
            )
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA max_page_count={self._database_bytes // 4096}")
            connection.execute("BEGIN IMMEDIATE")
            if not initialise:
                self._validate_schema(connection)
            yield connection
            connection.commit()
        except LibrusError:
            raise
        except sqlite3.Error as error:
            kind = (
                ErrorKind.LIMIT
                if getattr(error, "sqlite_errorcode", None)
                in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                else ErrorKind.STORAGE
            )
        except OSError:
            kind = ErrorKind.STORAGE
        finally:
            if connection is not None:
                connection.close()
        if kind is not None:
            raise LibrusError(kind)

    def _initialise(self) -> None:
        with self._connection(initialise=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone():
                    raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
                for sql in self._schema:
                    connection.execute(sql)
                connection.execute("PRAGMA user_version=1")
            self._validate_schema(connection)
            self._validate_contents(connection)
        if os.name == "posix":
            descriptor = os.open(
                self._directory,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        expected = []
        for sql in self._schema:
            name = sql.split()[2]
            expected.extend(
                [("table", name, sql), ("index", f"sqlite_autoindex_{name}_1", None)]
            )
        actual = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name LIMIT 32"
        ).fetchall()
        if (
            connection.execute("PRAGMA user_version").fetchone()[0] != 1
            or connection.execute("PRAGMA page_size").fetchone()[0] != 4096
            or connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
            or actual != sorted(expected, key=lambda row: row[1])
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    def _validate_contents(self, connection: sqlite3.Connection) -> None:
        raise NotImplementedError
