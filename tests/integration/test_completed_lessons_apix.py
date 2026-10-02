"""Original-response business comparison, not live or pagination qualification."""

import importlib
from datetime import date
from types import ModuleType, SimpleNamespace

import pytest

from librus_python_api.completed_lessons import parse_completed_lessons
from tests.completed_lessons_support import lesson_row, lessons_html
from tests.integration.test_school_reads_apix import baseline as baseline
from tests.integration.test_school_reads_apix import (
    no_external_connections as no_external_connections,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("no_external_connections"),
]


class ResponseClient:
    COMPLETED_LESSONS_URL = "https://offline.invalid/zrealizowane_lekcje"

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    def post(self, url: str, data: dict[str, str | int]) -> SimpleNamespace:
        assert url == self.COMPLETED_LESSONS_URL
        assert data == {
            "data1": "2026-10-01",
            "data2": "2026-10-31",
            "filtruj_id_przedmiotu": -1,
            "numer_strony1001": 0,
            "porcjowanie_pojemnik1001": 1001,
        }
        self.calls += 1
        return SimpleNamespace(text=self.body.decode())


@pytest.mark.parametrize(
    "variant",
    [
        "plain",
        "long",
        "missing_teacher",
        "line_break",
        "date_class_order",
        "pagination_spaces",
    ],
)
def test_completed_lesson_common_fields_and_explicit_departures(
    baseline: tuple[ModuleType, ModuleType],
    variant: str,
) -> None:
    # The baseline fixture verifies the external distribution hashes before import.
    module = importlib.import_module("librus_apix.completed_lessons")
    body = lessons_html(0, 3, lesson_row()).replace("extra decorated", "decorated")
    body = body.replace("small center", "center small").replace("z 3", "z\u00a03")
    if variant == "long":
        body = body.replace("Fixture topic", "Fixture " + "x" * 2048)
    elif variant == "missing_teacher":
        body = body.replace("Fixture Biology, Fixture Teacher", "Fixture Biology")
    elif variant == "line_break":
        body = body.replace("Fixture topic", "Fixture<br>topic")
    elif variant == "date_class_order":
        body = body.replace("center small", "small center")
    elif variant == "pagination_spaces":
        body = body.replace("z\u00a03", "z 3")
    data = body.encode()
    rows, count, _ = parse_completed_lessons(
        data, date(2026, 10, 1), date(2026, 10, 31), 0
    )
    client = ResponseClient(data)
    old = module.get_completed(client, "2026-10-01", "2026-10-31")[0]
    native = rows[0]
    assert native.subject == old.subject == "Fixture Biology"
    assert native.weekday == old.weekday == "pt."
    assert native.raw_lesson_number == old.lesson_number == "2"
    assert native.z_value == old.z_value == "Fixture Z"
    assert native.attendance_symbol == old.attendance_symbol == "nb"
    assert native.attendance_detail_id == old.attendance_href == "123"
    if variant == "missing_teacher":
        assert native.teacher is None and old.teacher == "Fixture Biology"
    else:
        assert native.teacher == old.teacher == "Fixture Teacher"
    if variant == "date_class_order":
        assert native.raw_day == "2026-10-02" and old.date == "01-01-2000"
    else:
        assert native.raw_day == old.date == "2026-10-02"
    if variant == "line_break":
        assert native.topic == "Fixture\ntopic" and old.topic == "Fixturetopic"
    else:
        assert native.topic == old.topic
    baseline_count = module.get_max_page_number(client, "2026-10-01", "2026-10-31")
    assert count == 3 and baseline_count == (0 if variant == "pagination_spaces" else 3)
    assert client.calls == 2
