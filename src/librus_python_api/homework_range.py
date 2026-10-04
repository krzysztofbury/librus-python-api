"""Bounded aggregation by upstream identity, without guessed date-filter semantics."""

from librus_python_api.config import SCHOOL_MAX_TOTAL_TEXT_LENGTH
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import HomeworkItem, SchoolReference


class HomeworkAccumulator:
    def __init__(self, max_items: int) -> None:
        self.items: list[HomeworkItem] = []
        self._references: dict[SchoolReference, HomeworkItem] = {}
        self._max_items = max_items
        self._text_length = 0

    def extend(self, items: tuple[HomeworkItem, ...]) -> None:
        for item in items:
            if item.reference is not None:
                previous = self._references.get(item.reference)
                if previous is not None:
                    if previous != item:
                        # The selection is not a server-side snapshot. Never
                        # silently prefer a stale or changed duplicate.
                        raise LibrusError(ErrorKind.PARSE)
                    continue
                self._references[item.reference] = item
            self._text_length += sum(
                len(value)
                for value in (
                    item.subject,
                    item.teacher,
                    item.topic,
                    item.category,
                    item.submission_status or "",
                )
            )
            if (
                len(self.items) >= self._max_items
                or self._text_length > SCHOOL_MAX_TOTAL_TEXT_LENGTH
            ):
                raise LibrusError(ErrorKind.LIMIT)
            self.items.append(item)
