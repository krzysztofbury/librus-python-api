"""Explicit optional notification state, raw checkpoints and two-phase delivery."""

import base64
import hashlib
import hmac
import os
import sqlite3
import stat
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from pydantic import Field

from librus_python_api._notification_codec import (
    ARCHIVE_BYTES,
    HEX,
    META_BYTES,
    WIRE_BYTES,
    canonical_notification_id,
    dump,
    empty_state,
    encode_batch,
    encode_envelope,
    load,
    restore_batch,
    restore_envelope,
    restore_state,
    state_bytes,
)
from librus_python_api._storage import _SQLiteStore, _StorageLimits
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    AccountContext,
    NotificationCategory,
    ScheduleEventResponse,
)
from librus_python_api.notification_models import (
    NotificationArchive,
    NotificationBatch,
    NotificationItem,
    NotificationSeen,
    NotificationState,
)
from librus_python_api.notifications import decode_payload, parse_schedule_events

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

_CONTEXT_SCHEMA = """CREATE TABLE notification_contexts (
    context TEXT PRIMARY KEY CHECK(length(context)=64)
)"""
_STATE_SCHEMA = """CREATE TABLE notification_state (
    context TEXT PRIMARY KEY REFERENCES notification_contexts(context),
    payload BLOB NOT NULL,
    last_receipt TEXT CHECK(last_receipt IS NULL OR length(last_receipt)=64)
)"""
_RAW_SCHEMA = """CREATE TABLE notification_raw (
    context TEXT PRIMARY KEY REFERENCES notification_contexts(context),
    identifier TEXT NOT NULL CHECK(length(identifier)=64),
    metadata BLOB NOT NULL,
    body BLOB NOT NULL,
    cursor INTEGER NOT NULL CHECK(cursor>=0 AND cursor<=1024),
    total INTEGER CHECK(total IS NULL OR (total>=cursor AND total<=1024))
)"""
_RESERVATION_SCHEMA = """CREATE TABLE notification_reservations (
    context TEXT PRIMARY KEY REFERENCES notification_contexts(context),
    bytes INTEGER NOT NULL CHECK(bytes>0 AND bytes<=8388608)
)"""
_DELIVERY_SCHEMA = """CREATE TABLE notification_deliveries (
    context TEXT PRIMARY KEY REFERENCES notification_contexts(context),
    receipt TEXT NOT NULL CHECK(length(receipt)=64),
    payload BLOB NOT NULL,
    state_after BLOB NOT NULL,
    raw_identifier TEXT CHECK(raw_identifier IS NULL OR length(raw_identifier)=64),
    cursor_after INTEGER CHECK(cursor_after IS NULL OR (
        cursor_after>=0 AND cursor_after<=1024))
)"""


class NotificationLimits(_StorageLimits):
    contexts: int = Field(default=16, ge=1, le=64)
    checkpoint_records: int = Field(default=32, ge=1, le=256)
    checkpoint_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=32 * 1024 * 1024)
    seen_ids_per_category: int = Field(default=4096, ge=1, le=4096)
    state_bytes: int = Field(default=4 * 1024 * 1024, ge=1, le=4 * 1024 * 1024)
    batch_items: int = Field(default=500, ge=1, le=4096)
    batch_bytes: int = Field(default=1024 * 1024, ge=1, le=4 * 1024 * 1024)
    replay_events: int = Field(default=500, ge=1, le=1024)
    replay_bytes: int = Field(default=128 * 1024, ge=1, le=1024 * 1024)


def _context_id(context: AccountContext) -> str:
    if (
        not isinstance(context, AccountContext)
        or type(context.identifier) is not str
        or HEX.fullmatch(context.identifier) is None
        or type(context.alias) is not str
        or not 1 <= len(context.alias) <= 80
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    return context.identifier


def _raw_id(context: str, metadata: bytes, body: bytes) -> str:
    digest = hashlib.sha256(context.encode("ascii"))
    digest.update(len(metadata).to_bytes(8, "big"))
    digest.update(metadata)
    digest.update(body)
    return digest.hexdigest()


def _seen_after(
    state: NotificationState, items: tuple[NotificationItem, ...], limit: int
) -> NotificationState:
    seen = {entry.category: list(entry.identifiers) for entry in state.seen}
    for item in items:
        identifiers = seen[item.category]
        if item.identifier not in identifiers:
            if len(identifiers) >= limit:
                raise LibrusError(ErrorKind.LIMIT)
            identifiers.append(item.identifier)
    return NotificationState(
        True,
        tuple(
            NotificationSeen(entry.category, tuple(seen[entry.category]))
            for entry in state.seen
        ),
    )


class NotificationStore(_SQLiteStore):
    """Private native recovery store. No MCP files, auto migration or live access.

    Context locks require POSIX flock. Unsupported platforms fail explicitly.
    Raw checkpoints contain private account/content metadata, never HTTP cookies.
    """

    _filename = "notifications.sqlite3"
    _database_bytes = 64 * 1024 * 1024
    _schema = (
        _CONTEXT_SCHEMA,
        _STATE_SCHEMA,
        _RAW_SCHEMA,
        _RESERVATION_SCHEMA,
        _DELIVERY_SCHEMA,
    )

    def __init__(
        self, directory: Path, *, limits: NotificationLimits | None = None
    ) -> None:
        self._notification_limits = (
            limits if limits is not None else NotificationLimits()
        )
        if not isinstance(self.limits, NotificationLimits):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        super().__init__(directory, limits=self.limits)

    @property
    def limits(self) -> NotificationLimits:
        return self._notification_limits

    def _validate_contents(self, connection: sqlite3.Connection) -> None:
        contexts = connection.execute(
            "SELECT context FROM notification_contexts LIMIT ?",
            (self.limits.contexts + 1,),
        ).fetchall()
        if len(contexts) > self.limits.contexts:
            raise LibrusError(ErrorKind.LIMIT)
        if any(
            type(row[0]) is not str or HEX.fullmatch(row[0]) is None for row in contexts
        ):
            raise LibrusError(ErrorKind.PARSE)
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LibrusError(ErrorKind.PARSE)
        records, used = connection.execute(
            "SELECT count(*), coalesce(sum(length(metadata)+length(body)),0) "
            "FROM notification_raw"
        ).fetchone()
        reservations, reserved = connection.execute(
            "SELECT count(*), coalesce(sum(bytes),0) FROM notification_reservations"
        ).fetchone()
        if (
            records + reservations > self.limits.checkpoint_records
            or used + reserved > self.limits.checkpoint_bytes
        ):
            raise LibrusError(ErrorKind.LIMIT)
        state_size = connection.execute(
            "SELECT coalesce(sum(length(payload)),0) FROM notification_state"
        ).fetchone()[0]
        delivery_size = connection.execute(
            "SELECT coalesce(sum(length(payload)+length(state_after)),0) "
            "FROM notification_deliveries"
        ).fetchone()[0]
        if state_size > self.limits.state_bytes or delivery_size > 16 * 1024 * 1024:
            raise LibrusError(ErrorKind.LIMIT)

    def _register(self, context: str) -> None:
        context = self._context_key(context)
        with self._connection() as connection:
            self._validate_contents(connection)
            if (
                connection.execute(
                    "SELECT 1 FROM notification_contexts WHERE context=?", (context,)
                ).fetchone()
                is None
            ):
                count = connection.execute(
                    "SELECT count(*) FROM notification_contexts"
                ).fetchone()[0]
                if count >= self.limits.contexts:
                    raise LibrusError(ErrorKind.LIMIT)
                connection.execute(
                    "INSERT INTO notification_contexts VALUES (?)", (context,)
                )

    def _lock_context(self, context: str, held: list[int]) -> None:
        context = self._context_key(context)
        if fcntl is None:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        path = self._directory / f"notification-{context}.lock"
        if path.is_symlink():
            raise LibrusError(ErrorKind.STORAGE)
        descriptor = os.open(
            path, os.O_CREAT | os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW, 0o600
        )
        try:
            status = os.fstat(descriptor)
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_nlink != 1
                or status.st_size != 0
                or status.st_uid != os.geteuid()
                or stat.S_IMODE(status.st_mode) & 0o077
            ):
                raise LibrusError(ErrorKind.STORAGE)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LibrusError(ErrorKind.LIMIT) from None
            held.append(descriptor)
            descriptor = -1
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @asynccontextmanager
    async def _context(self, context: AccountContext) -> AsyncIterator[None]:
        identifier = _context_id(context)
        held: list[int] = []
        try:
            await self._io(lambda: self._register(identifier))
            await self._io(lambda: self._lock_context(identifier, held))
            yield
        finally:
            # A resource-release syscall, not a new queued storage operation.
            # The acquisition worker is joined before this point, even on cancel.
            if held:
                os.close(held.pop())

    async def _transaction[T](
        self, context: AccountContext, operation: Callable[[], Coroutine[Any, Any, T]]
    ) -> T:
        async def run() -> T:
            async with self._context(context):
                return await operation()

        return await self._owned(run)

    def _state(
        self, connection: sqlite3.Connection, context: str
    ) -> tuple[NotificationState, str | None]:
        row = connection.execute(
            "SELECT payload,last_receipt FROM notification_state WHERE context=?",
            (self._context_key(context),),
        ).fetchone()
        if row is None:
            return empty_state(), None
        if type(row[0]) is not bytes or (
            row[1] is not None
            and (type(row[1]) is not str or HEX.fullmatch(row[1]) is None)
        ):
            raise LibrusError(ErrorKind.PARSE)
        return restore_state(
            row[0], self.limits.seen_ids_per_category, self.limits.state_bytes
        ), row[1]

    async def state(self, *, context: AccountContext) -> NotificationState:
        async def read() -> NotificationState:
            return await self._io(lambda: self._read_state(context.identifier))

        return await self._transaction(context, read)

    def _read_state(self, context: str) -> NotificationState:
        with self._connection() as connection:
            self._validate_contents(connection)
            return self._state(connection, context)[0]

    async def prune_seen(
        self,
        *,
        context: AccountContext,
        category: NotificationCategory,
        identifiers: tuple[str, ...],
    ) -> int:
        """Explicit retention; forgotten IDs may be notified again.

        Staged delivery and uncertain reservations must be resolved first. Raw
        checkpoints/progress are retained unchanged, including at seen saturation.
        No age-based expiry, background pruning or first-run reset is performed.
        """
        if (
            not isinstance(category, NotificationCategory)
            or type(identifiers) is not tuple
            or not 1 <= len(identifiers) <= self.limits.seen_ids_per_category
            or any(
                type(value) is not str or HEX.fullmatch(value) is None
                for value in identifiers
            )
            or len(set(identifiers)) != len(identifiers)
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)

        async def prune() -> int:
            return await self._io(
                lambda: self._prune_seen(context, category, identifiers)
            )

        return await self._transaction(context, prune)

    def _prune_seen(
        self,
        context: AccountContext,
        category: NotificationCategory,
        identifiers: tuple[str, ...],
    ) -> int:
        with self._connection() as connection:
            self._validate_contents(connection)
            key = self._context_key(context.identifier)
            for table in (
                "notification_deliveries",
                "notification_reservations",
            ):
                if connection.execute(
                    f"SELECT 1 FROM {table} WHERE context=?", (key,)
                ).fetchone():
                    raise LibrusError(ErrorKind.INVALID_INPUT)
            state, last = self._state(connection, context.identifier)
            removed = set(identifiers)
            current = next(entry for entry in state.seen if entry.category is category)
            if not removed.issubset(current.identifiers):
                raise LibrusError(ErrorKind.INVALID_INPUT)
            raw = self._raw(connection, context)
            if category is NotificationCategory.AGENDA and raw is not None and raw[2]:
                response = raw[1]
                events = parse_schedule_events(
                    decode_payload(response.wire.body, response.wire, WIRE_BYTES)
                )
                protected = {
                    canonical_notification_id(NotificationCategory.AGENDA, value)
                    for value in events[: raw[2]]
                }
                if removed & protected:
                    # Prefix membership proves acknowledged cursor progress during
                    # archive import. Retain it until the raw receipt is drained.
                    raise LibrusError(ErrorKind.INVALID_INPUT)
            after = replace(
                state,
                seen=tuple(
                    replace(
                        entry,
                        identifiers=tuple(
                            value for value in entry.identifiers if value not in removed
                        ),
                    )
                    if entry.category is category
                    else entry
                    for entry in state.seen
                ),
            )
            connection.execute(
                "UPDATE notification_state SET payload=? WHERE context=?",
                (
                    state_bytes(
                        after,
                        self.limits.seen_ids_per_category,
                        self.limits.state_bytes,
                    ),
                    key,
                ),
            )
            assert self._state(connection, context.identifier) == (after, last)
        return len(identifiers)

    def _raw(
        self, connection: sqlite3.Connection, context: AccountContext
    ) -> tuple[str, ScheduleEventResponse, int, int | None] | None:
        row = connection.execute(
            "SELECT identifier,metadata,body,cursor,total FROM notification_raw "
            "WHERE context=?",
            (self._context_key(context.identifier),),
        ).fetchone()
        if row is None:
            return None
        identifier, metadata, body, cursor, total = row
        if (
            type(metadata) is not bytes
            or type(body) is not bytes
            or type(cursor) is not int
            or not 0 <= cursor <= 1024
            or (
                total is not None
                and (type(total) is not int or not cursor <= total <= 1024)
            )
            or identifier
            != _raw_id(self._context_key(context.identifier), metadata, body)
        ):
            raise LibrusError(ErrorKind.PARSE)
        return (
            identifier,
            restore_envelope(metadata, body, context.alias),
            cursor,
            total,
        )

    def _pending(
        self, context: AccountContext
    ) -> tuple[
        NotificationBatch | None,
        tuple[str, ScheduleEventResponse, int, int | None] | None,
        bool,
    ]:
        with self._connection() as connection:
            self._validate_contents(connection)
            delivery = self._delivery(connection, context)
            raw = self._raw(connection, context)
            reservation = (
                connection.execute(
                    "SELECT 1 FROM notification_reservations WHERE context=?",
                    (self._context_key(context.identifier),),
                ).fetchone()
                is not None
            )
            if reservation and raw is not None:
                raise LibrusError(ErrorKind.PARSE)
            return delivery[0] if delivery else None, raw, reservation

    def _reserve(self, context: str, body_bytes: int) -> None:
        context = self._context_key(context)
        if type(body_bytes) is not int or not 1 <= body_bytes <= WIRE_BYTES:
            raise LibrusError(ErrorKind.LIMIT)
        with self._connection() as connection:
            self._validate_contents(connection)
            if (
                connection.execute(
                    "SELECT 1 FROM notification_raw WHERE context=?", (context,)
                ).fetchone()
                or connection.execute(
                    "SELECT 1 FROM notification_reservations WHERE context=?",
                    (context,),
                ).fetchone()
            ):
                raise LibrusError(ErrorKind.CHECKPOINT)
            connection.execute(
                "INSERT INTO notification_reservations VALUES (?,?)",
                (context, body_bytes + META_BYTES),
            )
            self._validate_contents(connection)

    def _checkpoint(
        self, context: AccountContext, response: ScheduleEventResponse
    ) -> None:
        metadata, body = encode_envelope(response, context.alias)
        key = self._context_key(context.identifier)
        with self._connection() as connection:
            self._validate_contents(connection)
            row = connection.execute(
                "SELECT bytes FROM notification_reservations WHERE context=?",
                (key,),
            ).fetchone()
            if row is None or len(metadata) + len(body) > row[0]:
                raise LibrusError(ErrorKind.CHECKPOINT)
            identifier = _raw_id(key, metadata, body)
            connection.execute(
                "INSERT INTO notification_raw VALUES (?,?,?,?,0,NULL)",
                (key, identifier, metadata, body),
            )
            connection.execute(
                "DELETE FROM notification_reservations WHERE context=?",
                (key,),
            )
            self._validate_contents(connection)

    def _stage(
        self,
        batch: NotificationBatch,
        raw_identifier: str | None,
        cursor_after: int | None,
        total: int | None,
    ) -> None:
        stored_context = replace(
            batch.context, identifier=self._context_key(batch.context.identifier)
        )
        payload = encode_batch(
            replace(batch, context=stored_context), self.limits.batch_bytes
        )
        if len(batch.items) > self.limits.batch_items:
            raise LibrusError(ErrorKind.LIMIT)
        with self._connection() as connection:
            self._validate_contents(connection)
            state, _ = self._state(connection, batch.context.identifier)
            after = state_bytes(
                _seen_after(state, batch.items, self.limits.seen_ids_per_category),
                self.limits.seen_ids_per_category,
                self.limits.state_bytes,
            )
            if raw_identifier is not None:
                raw = self._raw(connection, batch.context)
                if (
                    raw is None
                    or raw[0] != raw_identifier
                    or cursor_after is None
                    or total is None
                    or not raw[2] <= cursor_after <= total <= 1024
                ):
                    raise LibrusError(ErrorKind.PARSE)
                connection.execute(
                    "UPDATE notification_raw SET total=? WHERE context=?",
                    (total, stored_context.identifier),
                )
            connection.execute(
                "INSERT INTO notification_deliveries VALUES (?,?,?,?,?,?)",
                (
                    stored_context.identifier,
                    batch.receipt,
                    payload,
                    after,
                    raw_identifier,
                    cursor_after,
                ),
            )
            self._validate_contents(connection)
            self._delivery(connection, batch.context)

    def _delivery(
        self, connection: sqlite3.Connection, context: AccountContext
    ) -> tuple[NotificationBatch, NotificationState, str | None, int | None] | None:
        row = connection.execute(
            "SELECT receipt,payload,state_after,raw_identifier,cursor_after "
            "FROM notification_deliveries WHERE context=?",
            (self._context_key(context.identifier),),
        ).fetchone()
        if row is None:
            return None
        if type(row[1]) is not bytes or type(row[2]) is not bytes:
            raise LibrusError(ErrorKind.PARSE)
        batch = restore_batch(row[1], self.limits.batch_bytes)
        if batch.context != replace(
            context, identifier=self._context_key(context.identifier)
        ):
            raise LibrusError(ErrorKind.PARSE)
        batch = replace(batch, context=context)
        after = restore_state(
            row[2], self.limits.seen_ids_per_category, self.limits.state_bytes
        )
        before, _ = self._state(connection, context.identifier)
        seen = {entry.category: set(entry.identifiers) for entry in before.seen}
        keys = [(item.category, item.identifier) for item in batch.items]
        if (
            batch.context != context
            or batch.receipt != row[0]
            or batch.first_run == before.initialized
            or len(batch.items) > self.limits.batch_items
            or len(set(keys)) != len(keys)
            or any(identifier in seen[category] for category, identifier in keys)
            or after
            != _seen_after(before, batch.items, self.limits.seen_ids_per_category)
        ):
            raise LibrusError(ErrorKind.PARSE)
        raw = self._raw(connection, context)
        if row[3] is None:
            if (
                row[4] is not None
                or batch.has_more_schedule
                or NotificationCategory.AGENDA in batch.categories
            ):
                raise LibrusError(ErrorKind.PARSE)
        elif (
            raw is None
            or raw[0] != row[3]
            or type(row[4]) is not int
            or raw[3] is None
            or not raw[2] <= row[4] <= raw[3]
            or batch.has_more_schedule != (row[4] < raw[3])
        ):
            raise LibrusError(ErrorKind.PARSE)
        return batch, after, row[3], row[4]

    async def acknowledge(self, receipt: str, *, context: AccountContext) -> None:
        if type(receipt) is not str or HEX.fullmatch(receipt) is None:
            raise LibrusError(ErrorKind.INVALID_INPUT)

        async def commit() -> None:
            await self._io(lambda: self._ack(context, receipt), finishing=True)

        await self._transaction(context, commit)

    def _ack(self, context: AccountContext, receipt: str) -> None:
        with self._connection() as connection:
            self._validate_contents(connection)
            delivery = self._delivery(connection, context)
            if self._state(connection, context.identifier)[1] == receipt:
                # A late acknowledgement retry must leave a newer batch intact.
                return
            if delivery is None:
                raise LibrusError(ErrorKind.INVALID_INPUT)
            batch, after, raw_identifier, cursor_after = delivery
            if batch.receipt != receipt:
                raise LibrusError(ErrorKind.INVALID_INPUT)
            payload = state_bytes(
                after, self.limits.seen_ids_per_category, self.limits.state_bytes
            )
            connection.execute(
                "INSERT OR REPLACE INTO notification_state VALUES (?,?,?)",
                (self._context_key(context.identifier), payload, receipt),
            )
            if raw_identifier is not None:
                raw = self._raw(connection, context)
                assert raw is not None
                if cursor_after == raw[3]:
                    connection.execute(
                        "DELETE FROM notification_raw WHERE context=?",
                        (self._context_key(context.identifier),),
                    )
                else:
                    connection.execute(
                        "UPDATE notification_raw SET cursor=? WHERE context=?",
                        (cursor_after, self._context_key(context.identifier)),
                    )
            connection.execute(
                "DELETE FROM notification_deliveries WHERE context=?",
                (self._context_key(context.identifier),),
            )
            self._validate_contents(connection)

    async def resolve_uncertain_consume(
        self, *, context: AccountContext, accept_possible_loss: bool = False
    ) -> None:
        if type(accept_possible_loss) is not bool or not accept_possible_loss:
            raise LibrusError(ErrorKind.INVALID_INPUT)

        async def resolve() -> None:
            await self._io(lambda: self._resolve(context))

        await self._transaction(context, resolve)

    def _resolve(self, context: AccountContext) -> None:
        with self._connection() as connection:
            self._validate_contents(connection)
            if (
                self._raw(connection, context) is not None
                or self._delivery(connection, context) is not None
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)
            if (
                connection.execute(
                    "DELETE FROM notification_reservations WHERE context=?",
                    (self._context_key(context.identifier),),
                ).rowcount
                != 1
            ):
                raise LibrusError(ErrorKind.INVALID_INPUT)

    async def export_archive(self, *, context: AccountContext) -> NotificationArchive:
        async def export() -> NotificationArchive:
            payload = await self._io(lambda: self._export(context))
            return NotificationArchive(2, context, payload)

        return await self._transaction(context, export)

    def _export(self, context: AccountContext) -> bytes:
        with self._connection() as connection:
            self._validate_contents(connection)
            state, last = self._state(connection, context.identifier)
            raw = self._raw(connection, context)
            delivery = self._delivery(connection, context)
            reservation = connection.execute(
                "SELECT bytes FROM notification_reservations WHERE context=?",
                (self._context_key(context.identifier),),
            ).fetchone()
            raw_record = None
            if raw:
                metadata, body = encode_envelope(raw[1], context.alias)
                raw_record = {
                    "identifier": raw[0],
                    "metadata": load(metadata, META_BYTES),
                    "body": base64.b64encode(body).decode("ascii"),
                    "cursor": raw[2],
                    "total": raw[3],
                }
            delivery_record = None
            if delivery:
                delivery_record = {
                    "batch": load(
                        encode_batch(
                            replace(
                                delivery[0],
                                context=replace(
                                    context,
                                    identifier=self._context_key(context.identifier),
                                ),
                            ),
                            self.limits.batch_bytes,
                        ),
                        self.limits.batch_bytes,
                    ),
                    "state_after": asdict(delivery[1]),
                    "raw_identifier": delivery[2],
                    "cursor_after": delivery[3],
                }
            return dump(
                {
                    "state": asdict(state),
                    "version": 2,
                    "context": asdict(
                        replace(
                            context, identifier=self._context_key(context.identifier)
                        )
                    ),
                    "context_salt": self._context_salt.hex()
                    if self._context_salt
                    else None,
                    "last_receipt": last,
                    "raw": raw_record,
                    "delivery": delivery_record,
                    "reservation": reservation[0] if reservation else None,
                },
                ARCHIVE_BYTES,
            )

    async def import_archive(self, archive: NotificationArchive) -> None:
        if (
            not isinstance(archive, NotificationArchive)
            or type(archive.version) is not int
            or archive.version != 2
            or type(archive.payload) is not bytes
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)

        async def restore() -> None:
            await self._io(lambda: self._import(archive))

        await self._transaction(archive.context, restore)

    def _rebind_archive(self, record: dict[str, Any], context: AccountContext) -> None:
        """Validate source namespace before rebinding to this empty target store."""
        salt = record["context_salt"]
        if type(salt) is not str or HEX.fullmatch(salt) is None:
            raise LibrusError(ErrorKind.PARSE)
        source_key = hmac.new(
            bytes.fromhex(salt), bytes.fromhex(context.identifier), hashlib.sha256
        ).hexdigest()
        source_context = replace(context, identifier=source_key)
        if record["context"] != asdict(source_context):
            raise LibrusError(ErrorKind.PARSE)
        target_context = replace(
            context, identifier=self._context_key(context.identifier)
        )
        record["context"] = asdict(target_context)
        raw, delivery = record["raw"], record["delivery"]
        source_raw: str | None = None
        target_raw: str | None = None
        if raw is not None:
            if (
                type(raw) is not dict
                or set(raw) != {"identifier", "metadata", "body", "cursor", "total"}
                or type(raw["body"]) is not str
            ):
                raise LibrusError(ErrorKind.PARSE)
            try:
                body = base64.b64decode(raw["body"], validate=True)
            except (ValueError, UnicodeError):
                raise LibrusError(ErrorKind.PARSE) from None
            metadata = dump(raw["metadata"], META_BYTES)
            source_raw = _raw_id(source_key, metadata, body)
            if raw["identifier"] != source_raw:
                raise LibrusError(ErrorKind.PARSE)
            target_raw = _raw_id(target_context.identifier, metadata, body)
            raw["identifier"] = target_raw
        if delivery is not None:
            if type(delivery) is not dict or set(delivery) != {
                "batch",
                "state_after",
                "raw_identifier",
                "cursor_after",
            }:
                raise LibrusError(ErrorKind.PARSE)
            batch = restore_batch(
                dump(delivery["batch"], self.limits.batch_bytes),
                self.limits.batch_bytes,
            )
            if (
                batch.context != source_context
                or delivery["raw_identifier"] != source_raw
            ):
                # Ordinary-only batches may coexist with pending raw recovery.
                if (
                    batch.context != source_context
                    or delivery["raw_identifier"] is not None
                ):
                    raise LibrusError(ErrorKind.PARSE)
            if delivery["raw_identifier"] is not None:
                delivery["raw_identifier"] = target_raw
            delivery["batch"] = load(
                encode_batch(
                    replace(batch, context=target_context), self.limits.batch_bytes
                ),
                self.limits.batch_bytes,
            )

    def _import(self, archive: NotificationArchive) -> None:
        record = load(archive.payload, ARCHIVE_BYTES)
        if type(record) is not dict or set(record) != {
            "state",
            "last_receipt",
            "raw",
            "delivery",
            "reservation",
            "version",
            "context",
            "context_salt",
        }:
            raise LibrusError(ErrorKind.PARSE)
        context = archive.context
        if type(record["version"]) is not int or record["version"] != 2:
            raise LibrusError(ErrorKind.PARSE)
        self._rebind_archive(record, context)
        with self._connection() as connection:
            self._validate_contents(connection)
            # Import is empty-target only, never a silent history reset.
            for table in (
                "notification_state",
                "notification_raw",
                "notification_deliveries",
                "notification_reservations",
            ):
                if connection.execute(
                    f"SELECT 1 FROM {table} WHERE context=?",
                    (self._context_key(context.identifier),),
                ).fetchone():
                    raise LibrusError(ErrorKind.INVALID_INPUT)
            state = restore_state(
                dump(record["state"], self.limits.state_bytes),
                self.limits.seen_ids_per_category,
                self.limits.state_bytes,
            )
            last = record["last_receipt"]
            if last is not None and (
                type(last) is not str
                or HEX.fullmatch(last) is None
                or not state.initialized
            ):
                raise LibrusError(ErrorKind.PARSE)
            if state.initialized or last is not None:
                connection.execute(
                    "INSERT INTO notification_state VALUES (?,?,?)",
                    (
                        self._context_key(context.identifier),
                        state_bytes(
                            state,
                            self.limits.seen_ids_per_category,
                            self.limits.state_bytes,
                        ),
                        last,
                    ),
                )
            raw = record["raw"]
            if raw is not None:
                self._import_raw(connection, context, raw)
            reservation = record["reservation"]
            if reservation is not None:
                if (
                    raw is not None
                    or type(reservation) is not int
                    or not 1 <= reservation <= WIRE_BYTES + META_BYTES
                ):
                    raise LibrusError(ErrorKind.PARSE)
                connection.execute(
                    "INSERT INTO notification_reservations VALUES (?,?)",
                    (self._context_key(context.identifier), reservation),
                )
            delivery = record["delivery"]
            if delivery is not None:
                if type(delivery) is not dict or set(delivery) != {
                    "batch",
                    "state_after",
                    "raw_identifier",
                    "cursor_after",
                }:
                    raise LibrusError(ErrorKind.PARSE)
                batch = restore_batch(
                    dump(delivery["batch"], self.limits.batch_bytes),
                    self.limits.batch_bytes,
                )
                if batch.context != replace(
                    context, identifier=self._context_key(context.identifier)
                ):
                    raise LibrusError(ErrorKind.PARSE)
                public_batch = replace(batch, context=context)
                after = restore_state(
                    dump(delivery["state_after"], self.limits.state_bytes),
                    self.limits.seen_ids_per_category,
                    self.limits.state_bytes,
                )
                connection.execute(
                    "INSERT INTO notification_deliveries VALUES (?,?,?,?,?,?)",
                    (
                        self._context_key(context.identifier),
                        batch.receipt,
                        encode_batch(batch, self.limits.batch_bytes),
                        state_bytes(
                            after,
                            self.limits.seen_ids_per_category,
                            self.limits.state_bytes,
                        ),
                        delivery["raw_identifier"],
                        delivery["cursor_after"],
                    ),
                )
                self._delivery(connection, context)
                self._validate_import_delivery(connection, context, public_batch)
            self._validate_contents(connection)

    def _validate_import_delivery(
        self,
        connection: sqlite3.Connection,
        context: AccountContext,
        batch: NotificationBatch,
    ) -> None:
        """Prove imported cursor progress does not discard an undelivered event."""
        raw = self._raw(connection, context)
        if NotificationCategory.AGENDA not in batch.categories:
            return
        if raw is None:
            raise LibrusError(ErrorKind.PARSE)
        delivery = self._delivery(connection, context)
        assert delivery is not None and delivery[3] is not None
        response = raw[1]
        events = parse_schedule_events(
            decode_payload(response.wire.body, response.wire, WIRE_BYTES)
        )
        before, _ = self._state(connection, context.identifier)
        seen = {
            identifier
            for entry in before.seen
            if entry.category is NotificationCategory.AGENDA
            for identifier in entry.identifiers
        }
        expected = []
        for value in events[raw[2] : delivery[3]]:
            identifier = canonical_notification_id(NotificationCategory.AGENDA, value)
            if identifier not in seen:
                expected.append(
                    NotificationItem(
                        NotificationCategory.AGENDA,
                        identifier,
                        value,
                        response.identity,
                        response.observation,
                    )
                )
                seen.add(identifier)
        actual = [
            item for item in batch.items if item.category is NotificationCategory.AGENDA
        ]
        if actual != expected:
            raise LibrusError(ErrorKind.PARSE)

    def _import_raw(
        self, connection: sqlite3.Connection, context: AccountContext, raw: Any
    ) -> None:
        if (
            type(raw) is not dict
            or set(raw) != {"identifier", "metadata", "body", "cursor", "total"}
            or type(raw["body"]) is not str
        ):
            raise LibrusError(ErrorKind.PARSE)
        failed = False
        body = b""
        try:
            body = base64.b64decode(raw["body"], validate=True)
        except (ValueError, UnicodeError):
            failed = True
        if (
            failed
            or type(raw["cursor"]) is not int
            or (raw["total"] is not None and type(raw["total"]) is not int)
        ):
            raise LibrusError(ErrorKind.PARSE)
        metadata = dump(raw["metadata"], META_BYTES)
        response = restore_envelope(metadata, body, context.alias)
        if raw["total"] is None and raw["cursor"] != 0:
            raise LibrusError(ErrorKind.PARSE)
        if raw["total"] is not None:
            events = parse_schedule_events(
                decode_payload(body, response.wire, WIRE_BYTES)
            )
            if raw["total"] != len(events):
                raise LibrusError(ErrorKind.PARSE)
            # Acknowledged progress marks every event before the cursor seen; an
            # unseen one there would be skipped without ever being delivered.
            state, _ = self._state(connection, context.identifier)
            seen = {
                identifier
                for entry in state.seen
                if entry.category is NotificationCategory.AGENDA
                for identifier in entry.identifiers
            }
            if any(
                canonical_notification_id(NotificationCategory.AGENDA, value)
                not in seen
                for value in events[: raw["cursor"]]
            ):
                raise LibrusError(ErrorKind.PARSE)
        if raw["identifier"] != _raw_id(
            self._context_key(context.identifier), metadata, body
        ):
            raise LibrusError(ErrorKind.PARSE)
        connection.execute(
            "INSERT INTO notification_raw VALUES (?,?,?,?,?,?)",
            (
                self._context_key(context.identifier),
                raw["identifier"],
                metadata,
                body,
                raw["cursor"],
                raw["total"],
            ),
        )
        self._raw(connection, context)
