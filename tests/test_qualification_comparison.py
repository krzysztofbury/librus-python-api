"""Owning safety checks for one-shot traffic and privacy-safe classification."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from librus_python_api import RequestBudget
from librus_python_api.config import ENDPOINTS, UPSTREAM_ORIGINS
from librus_python_api.models import (
    AgendaSelection,
    CompletedLessonsPageSelection,
    HomeworkSelection,
)
from scripts.qualify_school_reads import (
    END,
    HOMEWORK_START,
    START,
    ScopeGuard,
    failure_site,
    main,
    structure_only,
)
from scripts.school_read_comparison import (
    ComparisonFailure,
    text_difference,
    tooltip_differences,
)
from tests.completed_lessons_support import lessons_html
from tests.http_support import serve


def admit(
    guard: ScopeGuard, operation: str, form: object = None, reference: str = "123"
) -> None:
    endpoint = ENDPOINTS[operation]
    url = UPSTREAM_ORIGINS[endpoint.origin] + endpoint.path.replace("{id}", reference)
    guard.admit(endpoint, url, form)


def test_guard_authentication_global_request_ceiling_and_failure_close() -> None:
    guard = ScopeGuard()
    admit(guard, "login_submit")
    with pytest.raises(ComparisonFailure, match="scope_login_ceiling"):
        admit(guard, "login_submit")
    assert guard.requests == guard.logins == 1
    guard.failed = True
    with pytest.raises(ComparisonFailure, match="scope_closed_after_failure"):
        admit(guard, "login_portal")
    other = ScopeGuard()
    for _ in range(24):
        admit(other, "login_portal")
    with pytest.raises(ComparisonFailure, match="scope_request_ceiling"):
        admit(other, "login_portal")
    assert other.requests == 24


@pytest.mark.parametrize(
    "operation,form",
    [
        ("announcements", None),
        ("student_information", None),
        ("completed_lessons", CompletedLessonsPageSelection(START, END, 3)),
        ("completed_lessons", CompletedLessonsPageSelection(HOMEWORK_START, END, 0)),
        ("agenda", AgendaSelection(2026, 8)),
        ("homework", HomeworkSelection(START, END)),
        ("agenda_detail", None),
        ("homework_detail", None),
    ],
)
def test_outside_scope_fails_before_counting_a_dispatch(
    operation: str, form: object
) -> None:
    guard = ScopeGuard()
    with pytest.raises(ComparisonFailure):
        admit(guard, operation, form)
    assert guard.requests == guard.logins == 0


def test_scope_family_counts_and_only_returned_detail_references() -> None:
    guard = ScopeGuard()
    for _ in range(5):
        admit(guard, "completed_lessons", CompletedLessonsPageSelection(START, END, 0))
    with pytest.raises(ComparisonFailure, match="scope_lesson_request_ceiling"):
        admit(guard, "completed_lessons", CompletedLessonsPageSelection(START, END, 0))
    guard.references["agenda_detail"] = {"123", "456"}
    admit(guard, "agenda_detail")
    admit(guard, "agenda_detail", reference="456")
    with pytest.raises(ComparisonFailure):
        admit(guard, "agenda_detail", reference="789")
    with pytest.raises(ComparisonFailure, match="scope_detail_ceiling"):
        admit(guard, "agenda_detail")
    admit(guard, "behaviour_notes_probe")
    with pytest.raises(ComparisonFailure, match="scope_notes_ceiling"):
        admit(guard, "behaviour_notes_probe")


def test_fixed_destination_cannot_be_replaced_by_another_origin_or_path() -> None:
    guard = ScopeGuard()
    with pytest.raises(ComparisonFailure, match="scope_origin"):
        guard.admit(
            ENDPOINTS["agenda"],
            "https://example.invalid/terminarz/",
            AgendaSelection(2026, 10),
        )
    with pytest.raises(ComparisonFailure, match="scope_fixed_path"):
        guard.admit(
            ENDPOINTS["agenda"],
            UPSTREAM_ORIGINS["synergia"] + "/fixture",
            AgendaSelection(2026, 10),
        )
    with pytest.raises(ComparisonFailure, match="scope_catalogued_operation"):
        endpoint = replace(ENDPOINTS["agenda"], path="/fixture")
        guard.admit(
            endpoint,
            UPSTREAM_ORIGINS["synergia"] + "/fixture",
            AgendaSelection(2026, 10),
        )
    assert guard.requests == 0


def test_tooltip_empty_trailing_notes_and_colon_spacing_are_reason_counters() -> None:
    event = SimpleNamespace(
        metadata=(("Opis", "Fixture detail"),), metadata_notes=("Fixture note",)
    )
    result = tooltip_differences(
        event, {"Opis ": "Fixture detail", "Fixture note": "unknown", "": "unknown"}
    )
    assert result == {
        "equal": 1,
        "baseline_invented_note_or_empty": 2,
        "baseline_missing_fields": 0,
    }
    assert "Fixture" not in str(result)
    assert text_difference("Fixture\nvalue", "Fixturevalue") == "joined_line_boundaries"
    assert text_difference("Fixture\nvalue", "Fixture value") == "whitespace"


def test_unclassified_tooltip_preserves_reason_count_without_values_or_throwing() -> (
    None
):
    event = SimpleNamespace(
        metadata=(("Fixture private label", "Fixture private value"),),
        metadata_notes=(),
    )
    result = tooltip_differences(
        event, {"Fixture private label": "Fixture different private value"}
    )
    assert result["unresolved"] == 1
    assert "Fixture" not in str(result)


def test_failure_diagnostics_are_structure_only() -> None:
    result = structure_only(lessons_html().replace("Strona 1", "Strona: 1").encode())
    assert result == {
        "decorated_tables": 1,
        "empty_markers": 0,
        "row_column_counts": {"7": 1},
        "pagination_spans": 1,
        "pagination_has_colon": True,
        "pagination_digit_group_counts": [2],
    }
    assert "Fixture" not in str(result) and "2026" not in str(result)


def test_failure_site_does_not_serialize_private_exception_messages() -> None:
    try:
        admit(ScopeGuard(), "agenda_detail", reference="987654321")
    except ComparisonFailure as error:
        result = failure_site(error)
    assert result == {"module_file": "school_read_comparison.py", "function": "require"}
    assert "987654321" not in str(result)


def test_internal_notes_probe_exact_wire_and_shared_request_budget() -> None:
    from tests.integration.test_qualification_harness import QualificationFixture

    async def scenario() -> None:
        fixture = QualificationFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                budget = RequestBudget(max_requests=6)
                await client.identity(budget=budget)
                before = budget.requests_dispatched
                response = await client._transport.request(
                    "behaviour_notes_probe", budget
                )
                assert response.status == 200 and b"Brak uwag" in response.body
                assert budget.requests_dispatched == before + 1 == 6
                assert fixture.logins == {"student": 1}
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_cli_failed_preflight_is_nonzero_and_marker_prevents_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "qualification",
            "--authorized",
            "--credentials",
            str(tmp_path / "absent.json"),
            "--account-position",
            "1",
            "--apix",
            str(tmp_path / "absent-reference"),
            "--report",
            str(report),
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 1
    saved = json.loads(report.read_text())
    assert saved["status"] == "interrupted_or_preflight_failed" and saved["pages"] == []
    assert "absent.json" not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        main()
    assert json.loads(report.read_text()) == saved
