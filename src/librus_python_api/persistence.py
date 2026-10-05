"""Explicit optional durable sending, independent of MCP and core transport."""

import hashlib
import json
import re
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self, cast

from pydantic import Field, model_validator

from librus_python_api._notification_codec import canonical_notification_id
from librus_python_api._storage import _SQLiteStore, _StorageLimits
from librus_python_api.budget import RequestBudget
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import AccountContext, SendResult, SendStatus
from librus_python_api.notification_models import (
    NotificationArchive,
    NotificationBaselineMapping,
    NotificationBatch,
    NotificationBootstrap,
    NotificationBootstrapResult,
    NotificationItem,
    NotificationProvenance,
    NotificationSeen,
    NotificationState,
)
from librus_python_api.notification_persistence import (
    NotificationLimits,
    NotificationStore,
)
from librus_python_api.notification_workflow import NotificationWorkflow
from librus_python_api.sending import SendAttempt

__all__ = [
    "NotificationArchive",
    "NotificationBaselineMapping",
    "NotificationBatch",
    "NotificationBootstrap",
    "NotificationBootstrapResult",
    "NotificationItem",
    "NotificationProvenance",
    "NotificationSeen",
    "NotificationState",
    "NotificationLimits",
    "NotificationStore",
    "NotificationWorkflow",
    "canonical_notification_id",
    "DurableSendOutcome",
    "DurableSendPhase",
    "DurableSendRecord",
    "PersistenceLimits",
    "PersistenceStore",
    "SendConfirmation",
]

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


class PersistenceLimits(_StorageLimits):
    send_records: int = Field(default=256, ge=1, le=4096)
    pending_confirmations: int = Field(default=32, ge=1, le=256)
    confirmation_ttl_seconds: int = Field(default=300, ge=1, le=300)

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


class PersistenceStore(_SQLiteStore):
    """Explicit private durable send claims; core clients require no storage.

    The selected directory's parent must exist. Store only digests and outcomes,
    never send bodies, token plaintext or HTTP cookies. Existing files are
    validated, not reset or automatically migrated. A durable claim is uncertain
    after process loss, even if no HTTP request actually reached the upstream.
    """

    _schema = (_SEND_SCHEMA,)

    def __init__(
        self, directory: Path, *, limits: PersistenceLimits | None = None
    ) -> None:
        self._limits = limits if limits is not None else PersistenceLimits()
        if not isinstance(self._limits, PersistenceLimits):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        super().__init__(directory, limits=self._limits)

    def _validate_contents(self, connection: sqlite3.Connection) -> None:
        self._rows(connection)

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
        context = self.context_identifier(context)
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
        context = self.context_identifier(context)
        return await self._owned(
            lambda: self._execute_send(token_hash, context, digest, attempt, budget)
        )

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
            try:
                await self._io(
                    lambda: self._finish(
                        token_hash, context, digest, attempt.outcome.status
                    ),
                    finishing=True,
                )
            except LibrusError as error:
                # LIMIT means "stopped before upstream work"; after a claim the
                # send may have been dispatched and the claim stays uncertain.
                if error.kind is not ErrorKind.LIMIT:
                    raise
                raise LibrusError(ErrorKind.STORAGE) from None

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
        identifier = self.context_identifier(_valid_digest(context.identifier))
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
        identifier = self.context_identifier(_valid_digest(context.identifier))
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

    async def prune_send_history(
        self,
        *,
        context: AccountContext,
        identifiers: tuple[str, ...],
        allow_accepted: bool = False,
    ) -> int:
        """Explicit atomic retention. Uncertain/claimed/live pending sends stay.

        Removing ACCEPTED records requires explicit duplicate-risk acceptance:
        identical payloads can subsequently receive a new confirmation.
        """
        if (
            not isinstance(context, AccountContext)
            or type(identifiers) is not tuple
            or not 1 <= len(identifiers) <= self._limits.send_records
            or type(allow_accepted) is not bool
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        for identifier in identifiers:
            _valid_digest(identifier)
        if len(set(identifiers)) != len(identifiers):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        key = self.context_identifier(context.identifier)
        return await self._io(
            lambda: self._prune_sends(key, identifiers, allow_accepted)
        )

    def _prune_sends(
        self, context: str, identifiers: tuple[str, ...], allow_accepted: bool
    ) -> int:
        with self._connection() as connection:
            rows = {row[0]: row for row in self._rows(connection) if row[1] == context}
            allowed = {"invalidated", "not_dispatched", "rejected"}
            if allow_accepted:
                allowed.add("accepted")
            now = _now()
            for identifier in identifiers:
                row = rows.get(identifier)
                if row is None or not (
                    row[5] in allowed or (row[5] == "pending" and row[4] <= now)
                ):
                    raise LibrusError(ErrorKind.INVALID_INPUT)
            connection.executemany(
                "DELETE FROM send_attempts WHERE token_hash=? AND context=?",
                [(identifier, context) for identifier in identifiers],
            )
        return len(identifiers)
