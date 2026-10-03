"""Optional native category orchestration with durable at-least-once replay."""

import secrets
from dataclasses import asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from librus_python_api._notification_codec import (
    META_BYTES,
    canonical_notification_id,
    dump,
    encode_batch,
)
from librus_python_api.budget import RequestBudget
from librus_python_api.checkpoint import validate_checkpoint
from librus_python_api.config import homework_form
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import (
    AttendanceView,
    GradeView,
    MessageFolder,
    NotificationCategory,
    ScheduleEventResponse,
    ScheduleEvents,
)
from librus_python_api.notification_models import (
    NotificationBatch,
    NotificationItem,
    NotificationState,
    NotificationValue,
)
from librus_python_api.notification_persistence import NotificationStore
from librus_python_api.service import AccountClient


class NotificationWorkflow:
    """Explicit selected-category poll and acknowledgement, without MCP schemas.

    A pending batch is returned without network until explicitly acknowledged.
    Replay of raw schedule bytes requires no fresh consume consent. New read-once
    retrieval requires allow_consume_events=True every time; no hidden retry.
    """

    def __init__(self, client: AccountClient, store: NotificationStore) -> None:
        if not isinstance(client, AccountClient) or not isinstance(
            store, NotificationStore
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self.client, self.store = client, store

    async def poll(
        self,
        *,
        categories: tuple[NotificationCategory, ...],
        allow_consume_events: bool = False,
        homework_window: tuple[date, date] | None = None,
        checkpoint_timeout_seconds: float = 5.0,
        budget: RequestBudget | None = None,
    ) -> NotificationBatch:
        if (
            type(categories) is not tuple
            or not 1 <= len(categories) <= 6
            or any(
                not isinstance(category, NotificationCategory)
                for category in categories
            )
            or len(set(categories)) != len(categories)
            or type(allow_consume_events) is not bool
            or (budget is not None and not isinstance(budget, RequestBudget))
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        validate_checkpoint(self.store._checkpoint, checkpoint_timeout_seconds)
        if homework_window is None:
            today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
            homework_window = (today - timedelta(days=7), today)
        if type(homework_window) is not tuple or len(homework_window) != 2:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        homework_form(*homework_window)
        actual = budget if budget is not None else self.client._service._budget()
        actual._bind_loop()
        actual.remaining_seconds()
        window = homework_window
        return await self.store._transaction(
            self.client.context,
            lambda: self._poll(
                categories,
                allow_consume_events,
                window,
                checkpoint_timeout_seconds,
                actual,
            ),
        )

    async def acknowledge(self, receipt: str) -> None:
        await self.store.acknowledge(receipt, context=self.client.context)

    async def _poll(
        self,
        categories: tuple[NotificationCategory, ...],
        consume: bool,
        window: tuple[date, date],
        seconds: float,
        budget: RequestBudget,
    ) -> NotificationBatch:
        context, store = self.client.context, self.store
        pending, raw, uncertain = await store._io(lambda: store._pending(context))
        if pending is not None:
            if pending.categories != categories:
                raise LibrusError(ErrorKind.INVALID_INPUT)
            return pending
        agenda = NotificationCategory.AGENDA in categories
        if agenda and raw is None:
            if uncertain:
                raise LibrusError(ErrorKind.CHECKPOINT)
            if not consume:
                raise LibrusError(ErrorKind.INVALID_INPUT)
        state = await store._io(lambda: store._read_state(context.identifier))
        ordinary = await self._ordinary(categories, window, budget)
        # Validate whole ordinary results and state capacity before consuming.
        items = self._new_items(ordinary, state)
        if len(items) > store.limits.batch_items:
            raise LibrusError(ErrorKind.LIMIT)
        for entry in state.seen:
            if (
                len(entry.identifiers)
                + sum(item.category == entry.category for item in items)
                > store.limits.seen_ids_per_category
            ):
                raise LibrusError(ErrorKind.LIMIT)
        provisional = NotificationBatch(
            "0" * 64, context, not state.initialized, categories, items, False
        )
        encode_batch(provisional, store.limits.batch_bytes)
        events: ScheduleEvents | None = None
        if agenda and raw is None:
            reserve = min(
                self.client._service._transport_limits.response_max_bytes,
                budget.remaining_response_bytes,
            )
            await store._io(lambda: store._reserve(context.identifier, reserve))

            async def persist(response: ScheduleEventResponse) -> None:
                await store._io(
                    lambda: store._checkpoint(context, response), finishing=True
                )

            events = await self.client.consume_schedule_events(
                checkpoint=persist,
                allow_consume_events=True,
                checkpoint_timeout_seconds=seconds,
                budget=budget,
            )
            _, raw, uncertain = await store._io(lambda: store._pending(context))
            assert raw is not None and not uncertain
        raw_identifier: str | None = None
        cursor: int | None = None
        total: int | None = None
        more = False
        if agenda:
            assert raw is not None
            if events is None:
                events = await self.client.decode_schedule_events(raw[1], budget=budget)
            if raw[3] is not None and raw[3] != len(events.items):
                raise LibrusError(ErrorKind.PARSE)
            schedule, cursor = self._slice_schedule(
                events, raw[2], state, store.limits.batch_items - len(items)
            )
            items += schedule
            raw_identifier, total = raw[0], len(events.items)
            more = cursor < total
        batch = NotificationBatch(
            secrets.token_hex(32),
            context,
            not state.initialized,
            categories,
            items,
            more,
        )
        await store._io(
            lambda: store._stage(batch, raw_identifier, cursor, total), finishing=True
        )
        return batch

    async def _ordinary(
        self,
        categories: tuple[NotificationCategory, ...],
        window: tuple[date, date],
        budget: RequestBudget,
    ) -> tuple[NotificationItem, ...]:
        items = []
        for category in categories:
            values: tuple[NotificationValue, ...]
            if category is NotificationCategory.AGENDA:
                continue
            if category is NotificationCategory.GRADES:
                grades = await self.client.grades(
                    view=GradeView.LAST_LOGIN, budget=budget
                )
                values = (*grades.records.numeric, *grades.records.descriptive)
                identity, observation = grades.identity, grades.observation
            elif category is NotificationCategory.ATTENDANCE:
                attendance = await self.client.attendance(
                    view=AttendanceView.LAST_LOGIN, budget=budget
                )
                values, identity, observation = (
                    attendance.items,
                    attendance.identity,
                    attendance.observation,
                )
            elif category is NotificationCategory.MESSAGES:
                messages = await self.client.messages_page(
                    MessageFolder.RECEIVED, budget=budget
                )
                values, identity, observation = (
                    messages.items,
                    messages.identity,
                    messages.observation,
                )
            elif category is NotificationCategory.ANNOUNCEMENTS:
                announcements = await self.client.announcements(budget=budget)
                values, identity, observation = (
                    announcements.items,
                    announcements.identity,
                    announcements.observation,
                )
            else:
                assert category is NotificationCategory.HOMEWORK
                homework = await self.client.homework(*window, budget=budget)
                values, identity, observation = (
                    homework.items,
                    homework.identity,
                    homework.observation,
                )
            for value in values:
                items.append(
                    NotificationItem(
                        category,
                        canonical_notification_id(category, value),
                        value,
                        identity,
                        observation,
                    )
                )
        return tuple(items)

    @staticmethod
    def _new_items(
        items: tuple[NotificationItem, ...], state: NotificationState
    ) -> tuple[NotificationItem, ...]:
        seen = {entry.category: set(entry.identifiers) for entry in state.seen}
        result = []
        for item in items:
            if item.identifier not in seen[item.category]:
                result.append(item)
                seen[item.category].add(item.identifier)
        return tuple(result)

    def _slice_schedule(
        self,
        events: ScheduleEvents,
        cursor: int,
        state: NotificationState,
        available: int,
    ) -> tuple[tuple[NotificationItem, ...], int]:
        if not 0 <= cursor <= len(events.items):
            raise LibrusError(ErrorKind.PARSE)
        seen = {
            identifier
            for entry in state.seen
            if entry.category is NotificationCategory.AGENDA
            for identifier in entry.identifiers
        }
        items: list[NotificationItem] = []
        used = 2
        for index in range(cursor, len(events.items)):
            value = events.items[index]
            identifier = canonical_notification_id(NotificationCategory.AGENDA, value)
            if identifier in seen:
                cursor = index + 1
                continue
            if len(items) >= min(self.store.limits.replay_events, available):
                break
            encoded = dump(asdict(value), META_BYTES)
            size = used + len(encoded) + bool(items)
            if size > self.store.limits.replay_bytes:
                if not items:
                    raise LibrusError(ErrorKind.LIMIT)
                break
            items.append(
                NotificationItem(
                    NotificationCategory.AGENDA,
                    identifier,
                    value,
                    events.identity,
                    events.observation,
                )
            )
            seen.add(identifier)
            used = size
            cursor = index + 1
        if not items and cursor < len(events.items):
            raise LibrusError(ErrorKind.LIMIT)
        return tuple(items), cursor
