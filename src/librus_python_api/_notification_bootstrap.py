"""Original bounded validation of caller-established, neutral offline mappings."""

from dataclasses import asdict

from librus_python_api._notification_codec import (
    HEX,
    canonical_notification_id,
    dump,
    validate_historical_item,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import NotificationCategory, RecentScheduleEvent
from librus_python_api.notification_models import (
    NotificationBaselineMapping,
    NotificationBootstrap,
    NotificationItem,
    NotificationProvenance,
    NotificationSeen,
    NotificationState,
)


def prepare_bootstrap(
    plan: NotificationBootstrap, per_category: int, batch_items: int, batch_bytes: int
) -> tuple[
    NotificationState,
    tuple[NotificationItem, ...],
    tuple[NotificationBaselineMapping, ...],
]:
    if type(plan.mappings) is not tuple or type(plan.pending_events) is not tuple:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    if (
        len(plan.mappings) > len(NotificationCategory) * per_category
        or len(plan.pending_events) > batch_items
    ):
        raise LibrusError(ErrorKind.LIMIT)
    seen, unmapped = _mapped_state(plan.mappings, per_category)
    items: list[NotificationItem] = []
    used = 2
    agenda_ids = set(
        next(
            entry.identifiers
            for entry in seen
            if entry.category is NotificationCategory.AGENDA
        )
    )
    for event in plan.pending_events:
        if type(event) is not RecentScheduleEvent:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        item = NotificationItem(
            NotificationCategory.AGENDA,
            "0" * 64,
            event,
            None,
            None,
            NotificationProvenance.IMPORTED_HISTORY,
        )
        try:
            validate_historical_item(item)
        except LibrusError:
            raise LibrusError(ErrorKind.INVALID_INPUT) from None
        identifier = canonical_notification_id(NotificationCategory.AGENDA, event)
        if identifier in agenda_ids:
            # A conflict cannot silently consume an externally pending event.
            raise LibrusError(ErrorKind.INVALID_INPUT)
        agenda_ids.add(identifier)
        final = NotificationItem(
            item.category, identifier, event, None, None, item.provenance
        )
        used += len(
            dump({"kind": "RecentScheduleEvent", "item": asdict(final)}, batch_bytes)
        ) + bool(items)
        if used > batch_bytes:
            raise LibrusError(ErrorKind.LIMIT)
        items.append(final)
    if len(agenda_ids) > per_category:
        raise LibrusError(ErrorKind.LIMIT)
    return NotificationState(True, seen), tuple(items), unmapped


def _mapped_state(
    mappings: tuple[NotificationBaselineMapping, ...], per_category: int
) -> tuple[tuple[NotificationSeen, ...], tuple[NotificationBaselineMapping, ...]]:
    seen: dict[NotificationCategory, list[str]] = {
        category: [] for category in NotificationCategory
    }
    sources: set[tuple[NotificationCategory, str]] = set()
    native: set[tuple[NotificationCategory, str]] = set()
    unmapped = []
    counts = {category: 0 for category in NotificationCategory}
    for mapping in mappings:
        if (
            type(mapping) is not NotificationBaselineMapping
            or not isinstance(mapping.category, NotificationCategory)
            or type(mapping.source_identifier) is not str
            or not 1 <= len(mapping.source_identifier) <= 256
        ):
            raise LibrusError(ErrorKind.INVALID_INPUT)
        try:
            mapping.source_identifier.encode("utf-8")
        except UnicodeError:
            raise LibrusError(ErrorKind.INVALID_INPUT) from None
        source = (mapping.category, mapping.source_identifier)
        if source in sources:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        sources.add(source)
        counts[mapping.category] += 1
        if counts[mapping.category] > per_category:
            raise LibrusError(ErrorKind.LIMIT)
        identifier = mapping.native_identifier
        if identifier is None:
            unmapped.append(mapping)
            continue
        if type(identifier) is not str or HEX.fullmatch(identifier) is None:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        key = (mapping.category, identifier)
        if key in native:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        native.add(key)
        seen[mapping.category].append(identifier)
    return tuple(
        NotificationSeen(category, tuple(identifiers))
        for category, identifiers in seen.items()
    ), tuple(unmapped)
