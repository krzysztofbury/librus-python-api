"""Private-data-in-memory checks; reports contain only fixed reason counters."""

import re
from collections import Counter
from collections.abc import Iterable
from typing import Any


class ComparisonFailure(Exception):
    """Fixed classification only, never an upstream value or chained exception."""


def normalized(value: str) -> str:
    return " ".join(value.split())


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ComparisonFailure(reason)


def text_difference(native: str, baseline: str) -> str:
    if native == baseline:
        return "equal"
    if normalized(native) == normalized(baseline):
        return "whitespace"
    if native.replace("\n", "") == baseline:
        return "joined_line_boundaries"
    return "unresolved"


def tooltip_differences(event: Any, baseline: dict[str, str]) -> Counter[str]:
    result: Counter[str] = Counter()
    fields = dict(event.metadata)
    for key, value in baseline.items():
        # Baseline labels are compared in memory, never placed in report keys.
        normalized_key = key.strip().rstrip(":").strip()
        if normalized_key in fields:
            difference = text_difference(fields[normalized_key], value)
            if difference == "unresolved":
                # Business parser can split only on exact BR spellings. Diagnose
                # markup variants by decoding to text, not by guessing live cause.
                decoded = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
                if normalized(decoded) == normalized(fields[normalized_key]):
                    difference = "baseline_br_markup"
            result[difference] += 1
        elif value == "unknown" and (
            not normalized_key or normalized_key in event.metadata_notes
        ):
            result["baseline_invented_note_or_empty"] += 1
        else:
            result["unresolved"] += 1
    missing = set(fields) - {key.strip().rstrip(":").strip() for key in baseline}
    result["baseline_missing_fields"] += len(missing)
    return result


def assert_rendered_agenda(result: Any, rendered: list[dict[str, Any]]) -> None:
    require(len(result.days) == len(rendered), "agenda_day_count")
    for day, view in zip(result.days, rendered, strict=True):
        require(day.day.day == view["day"], "agenda_day_number")
        require(len(day.events) == len(view["events"]), "agenda_event_count")
        for event, cell in zip(day.events, view["events"], strict=True):
            require(normalized(event.text) == normalized(cell["text"]), "agenda_text")
            require(
                normalized(event.metadata_text) == normalized(cell["tooltip"]),
                "agenda_tooltip",
            )
            require(
                event.subject is None
                if cell["subject"] is None
                else event.subject is not None
                and normalized(event.subject) == normalized(cell["subject"]),
                "agenda_subject",
            )
            require(
                any(
                    normalized(event.title) == normalized(line)
                    for line in cell["text"].splitlines()
                ),
                "agenda_title",
            )
            require(
                (event.reference.identifier if event.reference else None)
                == cell["reference"],
                "agenda_reference",
            )


def agenda_baseline(result: Any, legacy: dict[int, list[Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    require(len(result.days) == len(legacy), "baseline_agenda_days")
    for day in result.days:
        old = legacy.get(day.day.day, [])
        require(len(day.events) == len(old), "baseline_agenda_items")
        for event, item in zip(day.events, old, strict=True):
            counts["title_" + text_difference(event.title, item.title)] += 1
            if event.subject is None:
                counts["optional_subject"] += 1
            else:
                counts["subject_" + text_difference(event.subject, item.subject)] += 1
            counts.update(
                {
                    "tooltip_" + k: v
                    for k, v in tooltip_differences(event, item.data).items()
                }
            )
            if event.lesson_number is not None:
                counts[
                    "lesson_number_equal"
                    if event.lesson_number == item.number
                    else "lesson_number_unresolved"
                ] += 1
            if event.at_time is not None:
                counts[
                    "clock_equal"
                    if event.at_time.isoformat(timespec="minutes") == item.hour
                    else "clock_unresolved"
                ] += 1
    return dict(counts)


def assert_rendered_details(result: Any, rendered: list[dict[str, Any]]) -> None:
    fields = [row["cells"] for row in rendered if len(row["cells"]) == 2]
    require(len(fields) == len(result.fields), "detail_field_count")
    for (key, value), cells in zip(result.fields, fields, strict=True):
        require(
            [normalized(key), normalized(value)] == list(map(normalized, cells)),
            "detail_rendered_fields",
        )
    headings = [
        row["cells"][0] for row in rendered if row["header"] and len(row["cells"]) == 1
    ]
    notes = [
        row["cells"][0]
        for row in rendered
        if not row["header"] and len(row["cells"]) == 1 and normalized(row["cells"][0])
    ]
    require(
        list(map(normalized, result.notes)) == list(map(normalized, notes)),
        "detail_notes",
    )
    require(
        ([normalized(result.title)] if result.title else [])
        == list(map(normalized, headings)),
        "detail_heading",
    )


def fields_baseline(
    fields: Iterable[tuple[str, str]], legacy: dict[str, str]
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    native = dict(fields)
    require(set(native) == set(legacy), "baseline_detail_labels")
    for key, value in native.items():
        counts[text_difference(value, legacy[key])] += 1
    return dict(counts)


def assert_rendered_homework(result: Any, rendered: dict[str, Any]) -> None:
    require(len(result.items) == len(rendered["rows"]), "homework_row_count")
    if not result.items:
        require(rendered["empty"] == 1, "homework_explicit_empty")
    for item, row in zip(result.items, rendered["rows"], strict=True):
        values = [
            item.lesson,
            item.teacher,
            item.subject,
            item.category,
            item.assigned.raw_day,
            item.assigned.raw_clock,
            item.due.raw_day,
            item.due.raw_clock,
            *item.extra_cells,
        ]
        require(
            list(map(normalized, values)) == list(map(normalized, row)),
            "homework_rendered_values",
        )


def homework_baseline(result: Any, legacy: list[Any]) -> dict[str, int]:
    require(len(result.items) == len(legacy), "baseline_homework_count")
    counts: Counter[str] = Counter()
    for item, old in zip(result.items, legacy, strict=True):
        pairs = [
            (item.lesson, old.lesson),
            (item.teacher, old.teacher),
            (item.subject, old.subject),
            (item.category, old.category),
            (item.assigned.raw_day + " " + item.assigned.raw_clock, old.task_date),
            (item.due.raw_day + " " + item.due.raw_clock, old.completion_date),
        ]
        for native, baseline in pairs:
            counts[text_difference(native, baseline)] += 1
        counts[
            "reference_equal"
            if (item.reference.identifier if item.reference else "") == old.href
            else "reference_unresolved"
        ] += 1
    return dict(counts)


def assert_rendered_lessons(result: Any, rendered: dict[str, Any]) -> None:
    require(len(result.items) == len(rendered["rows"]), "lesson_row_count")
    if rendered["pagination"]:
        require(len(rendered["pagination"]) == 1, "lesson_pagination_count")
        numbers = list(map(int, re.findall(r"\d+", rendered["pagination"][0])))
        require(numbers == [result.page + 1, result.page_count], "lesson_current_total")
    else:
        require(result.page == 0 and result.page_count == 1, "lesson_single_page")
    if not result.items:
        require(rendered["empty"] == 1, "lesson_explicit_empty")
    for item, row in zip(result.items, rendered["rows"], strict=True):
        days = [c["text"] for c in row["cells"] if c["day"]]
        weekdays = [c["text"] for c in row["cells"] if c["weekday"]]
        data = [c["text"] for c in row["cells"] if not c["day"] and not c["weekday"]]
        require(
            list(map(normalized, days)) == [normalized(item.raw_day)], "lesson_date"
        )
        require(
            list(map(normalized, weekdays)) == [normalized(item.weekday)],
            "lesson_weekday",
        )
        values = [
            item.raw_lesson_number,
            item.subject_teacher_text,
            item.topic,
            item.z_value,
            item.attendance_symbol,
        ]
        require(
            list(map(normalized, data)) == list(map(normalized, values)),
            "lesson_values",
        )
        require(
            row["references"]
            == ([item.attendance_detail_id] if item.attendance_detail_id else []),
            "lesson_reference",
        )


def lessons_baseline(result: Any, legacy: list[Any], page_count: int) -> dict[str, int]:
    require(len(result.items) == len(legacy), "baseline_lesson_count")
    counts: Counter[str] = Counter()
    counts[
        "page_count_equal"
        if result.page_count == page_count
        else "page_count_rendered_native"
    ] += 1
    for item, old in zip(result.items, legacy, strict=True):
        pairs = [
            (item.subject, old.subject),
            (item.topic, old.topic),
            (item.z_value, old.z_value),
            (item.weekday, old.weekday),
            (item.raw_day, old.date),
            (item.attendance_symbol, old.attendance_symbol),
            (item.raw_lesson_number, str(old.lesson_number)),
        ]
        for native, baseline in pairs:
            counts[text_difference(native, baseline)] += 1
        if item.teacher is None:
            counts["optional_teacher"] += 1
        else:
            counts[text_difference(item.teacher, old.teacher)] += 1
        counts[
            "reference_equal"
            if (item.attendance_detail_id or "") == old.attendance_href
            else "reference_rendered_native"
        ] += 1
    return dict(counts)
