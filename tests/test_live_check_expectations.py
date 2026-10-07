"""Coverage expectations turn silent upstream changes into failures."""

from pathlib import Path

import pytest

from scripts.live_check.expectations import (
    Expected,
    compare,
    load,
    record,
    record_problems,
)
from scripts.live_check.report import Coverage, Report, SlotReport, Status, StepResult

ROOT = Path(__file__).resolve().parents[1]


def report_of(*steps: StepResult) -> Report:
    report = Report(
        "weekly", "1.2.1", "installed", "unknown", "2026-10-07T05:17:00+00:00"
    )
    report.slots.append(SlotReport(0, 10, 1.0, list(steps)))
    return report


OK_POPULATED = StepResult("grades", Status.OK, coverage=Coverage.POPULATED)
OK_EMPTY = StepResult("timetable", Status.OK, coverage=Coverage.EMPTY)
DISABLED = StepResult("completed_lessons", Status.ERROR, kind="view_disabled")


def test_matching_expectations_pass() -> None:
    expected = {
        0: {
            "grades": Expected.POPULATED,
            "timetable": Expected.ANY,
            "completed_lessons": Expected.DISABLED,
        }
    }
    assert compare(report_of(OK_POPULATED, OK_EMPTY, DISABLED), expected) == []


@pytest.mark.parametrize(
    "steps,expected,reason",
    [
        (
            (OK_EMPTY,),
            {"timetable": Expected.POPULATED},
            "slot 0 timetable: expected_populated_got_empty",
        ),
        ((OK_POPULATED,), {}, "slot 0 grades: no_expectation"),
        ((), {"grades": Expected.POPULATED}, "slot 0 grades: not_executed"),
        (
            (StepResult("grades", Status.ERROR, kind="parse"),),
            {"grades": Expected.ANY},
            "slot 0 grades: parse",
        ),
        (
            (StepResult("grades", Status.NOT_RUN),),
            {"grades": Expected.ANY},
            "slot 0 grades: not_run",
        ),
        (
            (StepResult("grades", Status.SKIPPED),),
            {"grades": Expected.ANY},
            "slot 0 grades: skipped",
        ),
        (
            (DISABLED,),
            {"completed_lessons": Expected.ANY},
            "slot 0 completed_lessons: expected_any_got_disabled",
        ),
    ],
)
def test_drift_is_reported_by_fixed_reason(
    steps: tuple[StepResult, ...], expected: dict[str, Expected], reason: str
) -> None:
    assert compare(report_of(*steps), {0: expected}) == [reason]


def test_an_expected_slot_that_did_not_run_fails() -> None:
    # For example, all slot 1 secrets were removed after expectations existed.
    expected = {0: {"grades": Expected.POPULATED}, 1: {"grades": Expected.ANY}}
    assert compare(report_of(OK_POPULATED), expected) == ["slot 1 slot: not_executed"]


def test_a_slot_without_expectations_fails() -> None:
    assert compare(report_of(OK_POPULATED), {}) == ["slot 0 slot: no_expectations"]


def test_record_prints_enum_values_only_and_fails_on_unexecuted_steps() -> None:
    report = report_of(
        OK_POPULATED, DISABLED, StepResult("session_alive", Status.NOT_RUN)
    )
    assert record(report) == {
        "slots": {
            "0": {
                "role": "unknown",
                "checks": {"grades": "populated", "completed_lessons": "disabled"},
            }
        }
    }
    assert record_problems(report) == ["slot 0 session_alive: not_run"]


@pytest.mark.parametrize(
    "text",
    [
        '{"slots": {"0": {"role": "teacher", "checks": {}}}}',
        '{"slots": {"0": {"role": "parent", "checks": {"grades": "full"}}}}',
        '{"slots": {"0": {"role": "parent", "checks": {"Fixture Name": "any"}}}}',
        '{"slots": {"x": {"role": "parent", "checks": {}}}}',
        '{"slots": {"0": {"role": "parent"}}}',
    ],
)
def test_malformed_expectations_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        load(text)


def test_the_committed_expectations_file_is_valid() -> None:
    # Starts as {"slots": {}}; later holds the owner's recorded map.
    load((ROOT / "contracts/live-check-expectations.json").read_text())


def test_committed_expectations_name_exactly_the_weekly_checks() -> None:
    # Drift here would only surface live as no_expectation or not_executed.
    from scripts.live_check.profiles import WEEKLY

    expected = load((ROOT / "contracts/live-check-expectations.json").read_text())
    names = {check.name for check in WEEKLY.checks}
    assert expected, "the weekly run needs at least one configured slot"
    for checks in expected.values():
        assert set(checks) == names
