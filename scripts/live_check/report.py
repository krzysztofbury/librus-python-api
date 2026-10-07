"""Redacted live-check results.

Only fixed step names, enum values, integers and booleans leave the process.
Nothing here accepts free text from upstream data or from exceptions, because
public repository logs and job summaries are readable by anyone.
"""

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}")
STEP = re.compile(r"[a-z][a-z0-9_]{0,63}( (received|sent))?")


class Status(StrEnum):
    OK = "ok"
    ERROR = "error"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_RUN = "not_run"


class Coverage(StrEnum):
    POPULATED = "populated"
    EMPTY = "empty"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


# Error kinds that describe whether a view exists for an account rather than a
# broken read; they map to a coverage value an expectation can name.
AVAILABILITY_KINDS = {
    "view_disabled": Coverage.DISABLED,
    "access_denied": Coverage.UNAVAILABLE,
    "unsupported_capability": Coverage.UNAVAILABLE,
}


@dataclass(frozen=True, slots=True)
class StepResult:
    step: str
    status: Status
    kind: str | None = None
    coverage: Coverage | None = None
    facts: tuple[tuple[str, int | bool], ...] = ()

    def __post_init__(self) -> None:
        if not STEP.fullmatch(self.step):
            raise ValueError("step names are fixed identifiers")
        if self.kind is not None and not IDENTIFIER.fullmatch(self.kind):
            raise ValueError("kinds are fixed identifiers")
        for name, value in self.facts:
            if not IDENTIFIER.fullmatch(name) or type(value) not in (int, bool):
                raise ValueError("facts are named integers or booleans")

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {"step": self.step, "status": self.status.value}
        if self.kind is not None:
            record["kind"] = self.kind
        if self.coverage is not None:
            record["coverage"] = self.coverage.value
        return record | dict(self.facts)


@dataclass(slots=True)
class SlotReport:
    slot: int
    requests: int
    seconds: float
    steps: list[StepResult]


@dataclass(slots=True)
class Report:
    profile: str
    version: str
    location: str
    commit: str
    started_at: str
    slots: list[SlotReport] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems and not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "version": self.version,
            "location": self.location,
            "commit": self.commit,
            "started_at": self.started_at,
            "passed": self.passed,
            "problems": list(self.problems),
            "violations": list(self.violations),
            "slots": [
                {
                    "slot": slot.slot,
                    "requests": slot.requests,
                    "seconds": slot.seconds,
                    "steps": [step.as_dict() for step in slot.steps],
                }
                for slot in self.slots
            ],
        }


def problem(slot: int, step: str, reason: str) -> str:
    if not STEP.fullmatch(step) or not IDENTIFIER.fullmatch(reason):
        raise ValueError("problems are built from fixed identifiers")
    return f"slot {slot} {step}: {reason}"


def render_json(report: Report) -> str:
    return json.dumps(report.as_dict(), indent=2)


def render_summary(report: Report) -> str:
    verdict = "passed" if report.passed else "failed"
    lines = [
        f"## Live check: {report.profile} {verdict}",
        "",
        f"Version {report.version} ({report.location}), commit {report.commit}, "
        f"started {report.started_at}.",
        "",
        "| Slot | Step | Status | Coverage or kind |",
        "| --- | --- | --- | --- |",
    ]
    for slot in report.slots:
        for step in slot.steps:
            detail = step.coverage.value if step.coverage else (step.kind or "")
            lines.append(
                f"| {slot.slot} | {step.step} | {step.status.value} | {detail} |"
            )
    if report.problems or report.violations:
        lines += ["", "### Problems", ""]
        lines += [f"- {item}" for item in report.problems]
        lines += [f"- guard violation: {name}" for name in report.violations]
    return "\n".join(lines) + "\n"
