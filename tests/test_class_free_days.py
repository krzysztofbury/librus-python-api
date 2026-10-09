"""Civil-date and malformed-collection contracts; shared HTTP proofs own reads."""

import json
from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from librus_python_api.class_free_days import parse_class_free_days
from librus_python_api.exceptions import LimitError, ParseError
from tests.class_free_days_support import free_day, free_days_body


def test_observed_optional_periods_civil_dates_and_inert_references() -> None:
    whole, partial = parse_class_free_days(free_days_body())
    assert (whole.identifier, whole.class_id, whole.type_id) == ("101", "201", "301")
    assert (whole.date_from, whole.date_to) == (date(2026, 12, 21), date(2026, 12, 22))
    assert (whole.lesson_no_from, whole.lesson_no_to) == (None, None)
    assert (partial.lesson_no_from, partial.lesson_no_to) == (2, 4)
    assert "2026" not in repr(whole) and "201" not in repr(whole)
    with pytest.raises(FrozenInstanceError):
        whole.class_id = "999"  # type: ignore[misc]
    assert parse_class_free_days(b'{"ClassFreeDays": []}') == ()


@pytest.mark.parametrize(
    "change",
    [
        {"Id": True},
        {"Id": "101"},
        {"Class": None},
        {"Type": {"Id": -1}},
        {"DateFrom": "2026-02-30"},
        {"DateFrom": "20261221"},
        {"DateTo": "2026-12-20"},
        {"DateTo": "2026-12-22T00:00:00Z"},
        {"LessonNoFrom": 1},
        {"LessonNoFrom": None, "LessonNoTo": None},
        {"LessonNoFrom": 4, "LessonNoTo": 2},
        {"LessonNoFrom": True, "LessonNoTo": 2},
        {"LessonNoFrom": 0, "LessonNoTo": 100},
    ],
)
def test_invalid_record_fails_the_whole_collection(change: dict[str, object]) -> None:
    bad = free_day(102) | change
    with pytest.raises(ParseError):
        parse_class_free_days(json.dumps({"ClassFreeDays": [free_day(), bad]}).encode())


@pytest.mark.parametrize(
    "body", [b"{}", b"[]", b'{"ClassFreeDays": null}', b'{"ClassFreeDays": [null]}']
)
def test_missing_collection_is_not_empty_success(body: bytes) -> None:
    with pytest.raises(ParseError):
        parse_class_free_days(body)


def test_duplicates_and_collection_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ParseError):
        parse_class_free_days(
            json.dumps({"ClassFreeDays": [free_day(), free_day()]}).encode()
        )
    monkeypatch.setattr(
        "librus_python_api.class_free_days.CLASS_FREE_DAYS_MAX_RECORDS", 1
    )
    with pytest.raises(LimitError):
        parse_class_free_days(free_days_body())
