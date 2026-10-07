"""Committed coverage expectations per account slot.

The file holds only slot indexes, a role label, check names and coverage
values, so it is safe in a public repository.
"""

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from librus_python_api.exceptions import ErrorKind
from scripts.live_check.report import (
    STEP,
    Coverage,
    Report,
    Status,
    StepResult,
    problem,
)

ROLES = frozenset({"parent", "student", "unknown"})
# Errors that describe availability rather than a broken read.
COVERAGE_ERRORS = {
    ErrorKind.VIEW_DISABLED.value: Coverage.DISABLED,
    ErrorKind.ACCESS_DENIED.value: Coverage.UNAVAILABLE,
    ErrorKind.UNSUPPORTED_CAPABILITY.value: Coverage.UNAVAILABLE,
}


class Expected(StrEnum):
    POPULATED = "populated"
    EMPTY = "empty"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    ANY = "any"


def observed(step: StepResult) -> Coverage | None:
    if step.status is Status.OK:
        return step.coverage
    if step.status is Status.ERROR and step.kind is not None:
        return COVERAGE_ERRORS.get(step.kind)
    return None


def _matches(expected: Expected, coverage: Coverage) -> bool:
    if expected is Expected.ANY:
        return coverage in (Coverage.POPULATED, Coverage.EMPTY)
    return expected.value == coverage.value


def load(text: str) -> dict[int, dict[str, Expected]]:
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("slots"), dict):
        raise ValueError("expectations need a slots object")
    result: dict[int, dict[str, Expected]] = {}
    for key, slot in data["slots"].items():
        if not (isinstance(key, str) and key.isdigit()) or not isinstance(slot, dict):
            raise ValueError("slots are keyed by index")
        if slot.get("role") not in ROLES or not isinstance(slot.get("checks"), dict):
            raise ValueError("each slot needs a known role and checks")
        checks: dict[str, Expected] = {}
        for name, value in slot["checks"].items():
            if not (isinstance(name, str) and STEP.fullmatch(name)):
                raise ValueError("check names are fixed identifiers")
            checks[name] = Expected(value)
        result[int(key)] = checks
    return result


def compare(
    report: Report, expectations: Mapping[int, Mapping[str, Expected]]
) -> list[str]:
    problems: list[str] = []
    for slot in report.slots:
        expected = expectations.get(slot.slot)
        if expected is None:
            problems.append(problem(slot.slot, "slot", "no_expectations"))
            continue
        seen: set[str] = set()
        for step in slot.steps:
            seen.add(step.step)
            coverage = observed(step)
            if coverage is None:
                problems.append(
                    problem(slot.slot, step.step, step.kind or step.status.value)
                )
                continue
            want = expected.get(step.step)
            if want is None:
                problems.append(problem(slot.slot, step.step, "no_expectation"))
            elif not _matches(want, coverage):
                problems.append(
                    problem(
                        slot.slot,
                        step.step,
                        f"expected_{want.value}_got_{coverage.value}",
                    )
                )
        for name in sorted(set(expected) - seen):
            problems.append(problem(slot.slot, name, "not_executed"))
    return problems


def record(report: Report) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    for slot in report.slots:
        checks = {
            step.step: coverage.value
            for step in slot.steps
            if (coverage := observed(step)) is not None
        }
        slots[str(slot.slot)] = {"role": "unknown", "checks": checks}
    return {"slots": slots}


def record_problems(report: Report) -> list[str]:
    return [
        problem(slot.slot, step.step, step.kind or step.status.value)
        for slot in report.slots
        for step in slot.steps
        if observed(step) is None
    ]
