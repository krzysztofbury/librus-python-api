"""Offline browser cross-check verdicts, with Chromium's rendering given as data."""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.crosscheck import check_directory, check_lessons, check_profile
from tests.completed_lessons_support import whiteboard_html
from tests.http_support import profile_html

LESSONS_FORM = {"data1": "2026-10-01", "data2": "2026-10-31", "numer_strony1001": "0"}
# What LESSONS_DOM returns for whiteboard_html(): the filter table is excluded,
# column 6 is the empty e-Tablica cell and the last row is the blank spacer.
WHITEBOARD_VIEW: dict[str, Any] = {
    "pagination": ["Strona\xa01\xa0z\xa01\xa0\xa0\xa0Pozycje\xa01..1\xa0z\xa01"],
    "optional": [6],
    "rows": [
        [
            {"cls": "center small", "text": "2026-10-05"},
            {"cls": "tiny", "text": "pn."},
            {"cls": "", "text": "3"},
            {"cls": "", "text": "Fixture Chemistry,\nTeacher Fixture"},
            {"cls": "", "text": "Fixture variant topic"},
            {"cls": "", "text": "\xa0"},
            {"cls": "", "text": "\xa0"},
            {"cls": "", "text": "ob"},
        ],
        [{"cls": "", "text": "\xa0"}],
    ],
}


def capture(directory: Path, endpoints: list[str]) -> Path:
    directory.mkdir()
    entries = [
        {"file": f"{i:02d}-{name}.html", "endpoint": name, "form": None}
        for i, name in enumerate(endpoints)
    ]
    (directory / "index.json").write_text(json.dumps({"captured": entries}))
    return directory


def test_captured_page_without_comparator_fails_and_json_reads_are_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Neither path renders anything, so no browser page is needed.
    json_only = capture(tmp_path / "json", ["identity", "gateway_attendance"])
    assert asyncio.run(check_directory(None, json_only))
    assert "not a rendered page, skipped" in capsys.readouterr().out
    with_grades = capture(tmp_path / "grades", ["identity", "grades"])
    assert not asyncio.run(check_directory(None, with_grades))
    assert "NOT COMPARED, no comparator for grades" in capsys.readouterr().out


def test_profile_resolves_every_label_alias_the_parser_accepts() -> None:
    view = {
        "Uczeń": "Fixture Student",
        "Klasa": "1 TEST",
        "Numer w dzienniku": "12",
        "Wychowawca": "Fixture Tutor",
        "Szkoła": "Synthetic School",
    }
    body = profile_html().encode()
    check_profile(body, {}, view)
    with pytest.raises(AssertionError, match="tutor"):
        check_profile(body, {}, view | {"Wychowawca": "Other Tutor"})


def test_lessons_compare_every_cell_and_the_page_count() -> None:
    body = whiteboard_html().encode()
    assert "cells and pagination agree" in check_lessons(
        body, LESSONS_FORM, WHITEBOARD_VIEW
    )
    # Same row count, different subject: a row-count check alone passes this.
    wrong_subject = copy.deepcopy(WHITEBOARD_VIEW)
    wrong_subject["rows"][0][3]["text"] = "Fixture Physics,\nTeacher Fixture"
    with pytest.raises(AssertionError, match="lesson cells"):
        check_lessons(body, LESSONS_FORM, wrong_subject)
    more_pages = WHITEBOARD_VIEW | {"pagination": ["Strona 1 z 2"]}
    with pytest.raises(AssertionError, match="page count"):
        check_lessons(body, LESSONS_FORM, more_pages)
