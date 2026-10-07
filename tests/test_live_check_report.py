"""Only fixed identifiers, enums and numbers can reach a public live-check log."""

import json
from collections.abc import Callable

import pytest

from scripts.live_check.report import (
    Coverage,
    Report,
    SlotReport,
    Status,
    StepResult,
    problem,
    render_json,
    render_summary,
)

FREE_TEXT: list[Callable[[], object]] = [
    lambda: StepResult("Fixture Teacher", Status.OK),
    lambda: StepResult("grades", Status.ERROR, kind="Fixture Teacher"),
    lambda: StepResult("grades", Status.OK, facts=(("name", "Fixture"),)),  # type: ignore[arg-type]
    lambda: StepResult("grades", Status.OK, facts=(("Bad Name", 1),)),
    lambda: StepResult("grades", Status.OK, facts=(("ratio", 0.5),)),  # type: ignore[arg-type]
]


@pytest.mark.parametrize("build", FREE_TEXT)
def test_free_text_cannot_enter_a_step_result(build: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        build()


def test_problem_reasons_are_identifiers() -> None:
    assert problem(1, "modern_page sent", "parse") == "slot 1 modern_page sent: parse"
    with pytest.raises(ValueError):
        problem(0, "grades", "Fixture message text")


def sample() -> Report:
    report = Report(
        "weekly", "1.2.1", "installed", "a" * 40, "2026-10-07T05:17:00+00:00"
    )
    report.slots.append(
        SlotReport(
            0,
            31,
            4.2,
            [
                StepResult(
                    "grades",
                    Status.OK,
                    coverage=Coverage.POPULATED,
                    facts=(("numeric", 3),),
                ),
                StepResult("completed_lessons", Status.ERROR, kind="view_disabled"),
                StepResult("session_alive", Status.NOT_RUN),
            ],
        )
    )
    report.problems.append(problem(0, "session_alive", "not_run"))
    return report


def test_json_report_has_only_the_documented_fields() -> None:
    data = json.loads(render_json(sample()))
    assert set(data) == {
        "profile",
        "version",
        "location",
        "commit",
        "started_at",
        "passed",
        "problems",
        "violations",
        "slots",
    }
    assert data["passed"] is False
    assert data["slots"][0]["steps"][0] == {
        "step": "grades",
        "status": "ok",
        "coverage": "populated",
        "numeric": 3,
    }
    assert data["slots"][0]["steps"][1] == {
        "step": "completed_lessons",
        "status": "error",
        "kind": "view_disabled",
    }


def test_summary_is_markdown_built_from_the_same_fields() -> None:
    text = render_summary(sample())
    assert text.startswith("## Live check: weekly failed")
    assert "| 0 | grades | ok | populated |" in text
    assert "- slot 0 session_alive: not_run" in text


def test_a_report_with_a_guard_violation_never_passes() -> None:
    report = Report(
        "weekly", "1.2.1", "installed", "unknown", "2026-10-07T05:17:00+00:00"
    )
    report.violations.append("modern_content_received")
    assert report.passed is False
