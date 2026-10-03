"""Explicit optional durable workflows, independent of MCP and core transport.

The application owns human approval and path selection. Claims are conservative:
process loss after a claim never makes a send replayable. No HTTP data or cookies
are persisted, and construction/import perform no filesystem or network I/O.
"""

import asyncio
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self, cast

from pydantic import Field, model_validator

from librus_python_api.budget import RequestBudget
from librus_python_api.config import _ValidatedConfig
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.lifecycle import join_owned
from librus_python_api.models import AccountContext, SendResult, SendStatus
from librus_python_api.sending import SendAttempt

__all__ = [
    "DurableSendOutcome",
    "DurableSendPhase",
    "DurableSendRecord",
    "PersistenceLimits",
    "PersistenceStore",
    "SendConfirmation",
]

_SCHEMA_VERSION = 1
_PAGE_BYTES = 4096
_DATABASE_BYTES = 8 * 1024 * 1024
_STATUS_VALUES = frozenset(
    {"pending", "claimed", "invalidated", *(s.value for s in SendStatus)}
)
_HEX = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,128}")
_SendRow = tuple[str, str, str, int, int, str]
_SEND_SCHEMA = """CREATE TABLE send_attempts (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
    context TEXT NOT NULL CHECK(length(context)=64),
    payload_digest TEXT NOT NULL CHECK(length(payload_digest)=64),
    created_at INTEGER NOT NULL CHECK(created_at>=0),
    expires_at INTEGER NOT NULL CHECK(
        expires_at>created_at AND expires_at<=created_at+300),
    status TEXT NOT NULL CHECK(status IN (
        'pending','claimed','invalidated','not_dispatched',
        'unknown','accepted','rejected'))
)"""


class PersistenceLimits(_ValidatedConfig):
    operations: int = Field(default=8, ge=1, le=64)
    send_records: int = Field(default=256, ge=1, le=4096)
    pending_confirmations: int = Field(default=32, ge=1, le=256)
    confirmation_ttl_seconds: int = Field(default=300, ge=1, le=300)
    busy_timeout_seconds: float = Field(default=0.1, gt=0, le=5, allow_inf_nan=False)

    @model_validator(mode="after")
    def pending_bound(self) -> Self:
        if self.pending_confirmations > self.send_records:
            raise ValueError("Pending confirmations exceed history capacity")
        return self


@dataclass(frozen=True, slots=True)
class SendConfirmation:
    token: str = field(repr=False)
    expires_at: datetime


class DurableSendPhase(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    INVALIDATED = "invalidated"
    NOT_DISPATCHED = "not_dispatched"
    UNKNOWN = "unknown"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class DurableSendOutcome:
    status: SendStatus | None
    phase: DurableSendPhase
    requires_reconciliation: bool


@dataclass(frozen=True, slots=True)
class DurableSendRecord:
    identifier: str = field(repr=False)
    payload_digest: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    outcome: DurableSendOutcome


def _valid_digest(value: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return value


def _token_hash(token: str) -> str:
    if type(token) is not str or _TOKEN.fullmatch(token) is None:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _now() -> int:
    return time.time_ns() // 1_000_000_000


def _binding(attempt: SendAttempt) -> tuple[str, str]:
    if not isinstance(attempt, SendAttempt) or attempt.used:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    context = _valid_digest(attempt.account_context.identifier)
    encoded = json.dumps(
        [1, context, attempt.outcome.backend.value, asdict(attempt.submission)],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return context, hashlib.sha256(encoded).hexdigest()


class PersistenceStore:
    """Explicit SQLite lifecycle with bounded/joined workers and durable claims.

    The selected directory's parent must already exist. Existing private files
    are validated, never reset, silently migrated or removed to recover capacity.
    In-flight recovery snapshots are conservative, not proof a process stopped.
    """

    def __init__(
        self, directory: Path, *, limits: PersistenceLimits | None = None
    ) -> None:
        if not isinstance(directory, Path) or not directory.is_absolute():
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._directory = directory
        self._path = directory / "state.sqlite3"
        self._limits = limits if limits is not None else PersistenceLimits()
        if not isinstance(self._limits, PersistenceLimits):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._opened = self._opening = self._closing = self._closed = False
        self._operations = 0
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._send_tasks: set[asyncio.Task[SendResult]] = set()
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
            or asyncio.current_task() in self._send_tasks
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
        # Cancel network workflows first, and let their owned final saves finish.
        # Canceling those storage children first would discard acknowledged state.
        for task in tuple(self._send_tasks):
            task.cancel()
        for task in tuple(self._send_tasks):
            await join_owned(task)
        # New ordinary operations are closed; final saves were joined above.
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            await join_owned(task)
        self._closed = True
        self._opened = False

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
        if self._operations >= self._limits.operations:
            raise LibrusError(ErrorKind.LIMIT)
        self._operations += 1
        task = asyncio.create_task(self._worker(operation))
        self._tasks.add(task)
        cancelled = False
        try:
            await asyncio.wait((task,))
            return task.result()
        except asyncio.CancelledError:
            cancelled = True
            # Once finishing is admitted, even cancellation while waiting for
            # another storage worker must join it, not discard an acknowledgement.
            if not finishing:
                task.cancel()
            raise
        finally:
            interrupted = await join_owned(task)
            self._tasks.discard(task)
            self._operations -= 1
            if cancelled or interrupted:
                raise asyncio.CancelledError

    async def _worker[T](self, operation: Callable[[], T]) -> T:
        kind: ErrorKind | None = None
        async with self._lock:
            task = asyncio.create_task(asyncio.to_thread(operation))
            interrupted = await join_owned(task)
            if interrupted:
                raise asyncio.CancelledError
            try:
                return task.result()
            except LibrusError:
                raise
            except Exception:
                kind = ErrorKind.STORAGE
        assert kind is not None
        raise LibrusError(kind)

    def _check_directory(self) -> None:
        # Private immediate parent plus a fixed filename is the trust boundary.
        # Same-user malicious filesystem writers are not an isolation promise.
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
                or status.st_size > _DATABASE_BYTES
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
                or status.st_size > _DATABASE_BYTES + 1024 * 1024
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
            connection = sqlite3.connect(
                self._path, timeout=self._limits.busy_timeout_seconds
            )
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                f"PRAGMA max_page_count={_DATABASE_BYTES // _PAGE_BYTES}"
            )
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
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' LIMIT 8"
            ).fetchall()
            if (
                version not in (0, _SCHEMA_VERSION)
                or (version == 0 and tables)
                or (version == _SCHEMA_VERSION and tables != [("send_attempts",)])
            ):
                raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
            if version == 0:
                connection.execute(_SEND_SCHEMA)
                connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            self._validate_schema(connection)
            self._rows(connection)
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

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        objects = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name LIMIT 8"
        ).fetchall()
        if (
            connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION
            or connection.execute("PRAGMA page_size").fetchone()[0] != _PAGE_BYTES
            or connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
            or objects
            != [
                ("table", "send_attempts", _SEND_SCHEMA),
                ("index", "sqlite_autoindex_send_attempts_1", None),
            ]
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    def _rows(self, connection: sqlite3.Connection) -> list[_SendRow]:
        rows = cast(
            list[_SendRow],
            connection.execute(
                "SELECT token_hash, context, payload_digest, created_at, "
                "expires_at, status FROM send_attempts LIMIT ?",
                (self._limits.send_records + 1,),
            ).fetchall(),
        )
        if len(rows) > self._limits.send_records:
            raise LibrusError(ErrorKind.LIMIT)
        for row in rows:
            if (
                any(
                    type(value) is not str or _HEX.fullmatch(value) is None
                    for value in row[:3]
                )
                or type(row[3]) is not int
                or type(row[4]) is not int
                or not 0 <= row[3] < row[4] <= row[3] + 300
                or row[4] > 253402300799
                or type(row[5]) is not str
                or row[5] not in _STATUS_VALUES
            ):
                raise LibrusError(ErrorKind.PARSE)
        return rows

    async def preview_send(self, attempt: SendAttempt) -> SendConfirmation:
        context, digest = _binding(attempt)
        return await self._io(lambda: self._issue(context, digest))

    def _issue(self, context: str, digest: str) -> SendConfirmation:
        now = _now()
        with self._connection() as connection:
            self._rows(connection)
            connection.execute(
                "DELETE FROM send_attempts WHERE status='pending' AND expires_at<=?",
                (now,),
            )
            rows = self._rows(connection)
            if self._duplicate(rows, context, digest):
                raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
            if (
                len(rows) >= self._limits.send_records
                or sum(row[5] == "pending" for row in rows)
                >= self._limits.pending_confirmations
            ):
                raise LibrusError(ErrorKind.LIMIT)
            token = secrets.token_urlsafe(32)
            deadline = now + self._limits.confirmation_ttl_seconds
            connection.execute(
                "INSERT INTO send_attempts VALUES (?,?,?,?,?,?)",
                (_token_hash(token), context, digest, now, deadline, "pending"),
            )
        return SendConfirmation(token, datetime.fromtimestamp(deadline, UTC))

    @staticmethod
    def _duplicate(rows: list[_SendRow], context: str, digest: str) -> bool:
        return any(
            row[1] == context
            and row[2] == digest
            and row[5] in {"claimed", "unknown", "accepted"}
            for row in rows
        )

    def _claim(self, token_hash: str, context: str, digest: str) -> None:
        invalid = False
        with self._connection() as connection:
            rows = self._rows(connection)
            row = next((row for row in rows if row[0] == token_hash), None)
            if row is None or row[5] != "pending":
                raise LibrusError(ErrorKind.INVALID_INPUT)
            invalid = (
                row[1] != context
                or row[2] != digest
                or not row[3] <= _now() < row[4]
                or self._duplicate(rows, context, digest)
            )
            connection.execute(
                "UPDATE send_attempts SET status=? WHERE token_hash=?",
                ("invalidated" if invalid else "claimed", token_hash),
            )
        if invalid:
            raise LibrusError(ErrorKind.INVALID_INPUT)

    async def execute_send(
        self, token: str, attempt: SendAttempt, *, budget: RequestBudget | None = None
    ) -> SendResult:
        token_hash = _token_hash(token)
        context, digest = _binding(attempt)
        if not self._opened or self._closing or self._closed:
            raise LibrusError(ErrorKind.CLOSED)
        if len(self._send_tasks) >= self._limits.operations:
            raise LibrusError(ErrorKind.LIMIT)
        task = asyncio.create_task(
            self._execute_send(token_hash, context, digest, attempt, budget)
        )
        self._send_tasks.add(task)
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
            self._send_tasks.discard(task)
            if cancelled or interrupted:
                raise asyncio.CancelledError

    async def _execute_send(
        self,
        token_hash: str,
        context: str,
        digest: str,
        attempt: SendAttempt,
        budget: RequestBudget | None,
    ) -> SendResult:
        await self._io(lambda: self._claim(token_hash, context, digest))
        try:
            return await attempt.execute(budget=budget)
        finally:
            await self._io(
                lambda: self._finish(
                    token_hash, context, digest, attempt.outcome.status
                ),
                finishing=True,
            )

    def _finish(
        self, token_hash: str, context: str, digest: str, status: SendStatus
    ) -> None:
        with self._connection() as connection:
            self._rows(connection)
            changed = connection.execute(
                "UPDATE send_attempts SET status=? WHERE token_hash=? "
                "AND context=? AND payload_digest=? AND status='claimed'",
                (status.value, token_hash, context, digest),
            ).rowcount
            if changed != 1:
                raise LibrusError(ErrorKind.INVALID_INPUT)

    async def send_outcome(
        self, token: str, *, context: AccountContext
    ) -> DurableSendOutcome:
        token_hash = _token_hash(token)
        if not isinstance(context, AccountContext):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        identifier = _valid_digest(context.identifier)
        return await self._io(lambda: self._outcome(token_hash, identifier))

    def _outcome(self, token_hash: str, context: str) -> DurableSendOutcome:
        with self._connection() as connection:
            row = next(
                (row for row in self._rows(connection) if row[0] == token_hash), None
            )
            if row is None or row[1] != context:
                raise LibrusError(ErrorKind.INVALID_INPUT)
            return self._snapshot(row[5])

    @staticmethod
    def _snapshot(value: str) -> DurableSendOutcome:
        phase = DurableSendPhase(value)
        status = (
            SendStatus.UNKNOWN
            if phase is DurableSendPhase.CLAIMED
            else SendStatus(phase)
            if phase in {s.value for s in SendStatus}
            else None
        )
        return DurableSendOutcome(status, phase, phase in {"claimed", "unknown"})

    async def send_history(
        self, *, context: AccountContext
    ) -> tuple[DurableSendRecord, ...]:
        """Bounded context-bound recovery, even if plaintext tokens were lost."""
        if not isinstance(context, AccountContext):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        identifier = _valid_digest(context.identifier)
        return await self._io(lambda: self._history(identifier))

    def _history(self, context: str) -> tuple[DurableSendRecord, ...]:
        with self._connection() as connection:
            rows = sorted(
                (row for row in self._rows(connection) if row[1] == context),
                key=lambda row: (row[3], row[0]),
            )
            return tuple(
                DurableSendRecord(
                    row[0],
                    row[2],
                    datetime.fromtimestamp(row[3], UTC),
                    datetime.fromtimestamp(row[4], UTC),
                    self._snapshot(row[5]),
                )
                for row in rows
            )
