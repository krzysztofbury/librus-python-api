"""Runs a profile's checks per login, stopping a login at its first fatal error."""

import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import librus_python_api
from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    RequestBudget,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from scripts.live_check.checks import Check, CheckFailed, Context
from scripts.live_check.guard import guarded
from scripts.live_check.report import (
    AVAILABILITY_KINDS,
    IDENTIFIER,
    Report,
    SlotReport,
    Status,
    StepResult,
    problem,
)

BASE_READS = frozenset({"identity"})
# No retry, no reauthentication: these end the login's run.
FATAL_KINDS = frozenset(
    kind.value
    for kind in (
        ErrorKind.CREDENTIALS_REJECTED,
        ErrorKind.ACCOUNT_ACTION_REQUIRED,
        ErrorKind.SESSION_EXPIRED,
        ErrorKind.THROTTLED,
        ErrorKind.MAINTENANCE,
        ErrorKind.CONNECTION,
        ErrorKind.TIMEOUT,
        ErrorKind.LIMIT,
        ErrorKind.CLOSED,
    )
)
FATAL_CODES = frozenset({"identity_mismatch"})


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    checks: tuple[Check, ...]
    max_requests: int
    timeout_seconds: float


async def execute(
    check: Check, context: Context, done: Mapping[str, StepResult]
) -> StepResult:
    if check.after is not None:
        prerequisite = done.get(check.after)
        if prerequisite is None or prerequisite.status is not Status.OK:
            if (
                prerequisite is not None
                and prerequisite.status is Status.ERROR
                and prerequisite.kind in AVAILABILITY_KINDS
            ):
                # Not reachable for this account, like its prerequisite.
                return StepResult(check.name, Status.ERROR, kind=prerequisite.kind)
            return StepResult(check.name, Status.NOT_RUN)
    if not check.requires(context.client):
        return StepResult(check.name, Status.SKIPPED)
    try:
        observed = await check.probe(context)
    except LibrusError as error:
        return StepResult(check.name, Status.ERROR, kind=error.kind.value)
    except CheckFailed as failure:
        return StepResult(check.name, Status.FAILED, kind=failure.code)
    except Exception as error:  # noqa: BLE001 - reported by class name only
        kind = ("unexpected_" + type(error).__name__.lower())[:63]
        if not IDENTIFIER.fullmatch(kind):
            kind = "unexpected"
        return StepResult(check.name, Status.ERROR, kind=kind)
    return StepResult(
        check.name, Status.OK, coverage=observed.coverage, facts=observed.facts
    )


def _fatal(result: StepResult) -> bool:
    if result.status is Status.ERROR:
        return result.kind in FATAL_KINDS
    return result.status is Status.FAILED and result.kind in FATAL_CODES


async def run_slot(
    checks: Sequence[Check], context: Context, violations: Sequence[str] = ()
) -> list[StepResult]:
    """Run checks in order; a fatal error or a guard refusal ends the login."""
    results: list[StepResult] = []
    done: dict[str, StepResult] = {}
    refused = len(violations)
    stopped = False
    for item in checks:
        result = (
            StepResult(item.name, Status.NOT_RUN)
            if stopped
            else await execute(item, context, done)
        )
        results.append(result)
        done[item.name] = result
        stopped = stopped or _fatal(result) or len(violations) > refused
    return results


async def run_profile(
    profile: Profile,
    accounts: Mapping[str, AccountCredentials],
    *,
    today: date,
    identities: Mapping[str, str] | None = None,
    connection: ConnectionSettings | None = None,
    commit: str = "unknown",
) -> Report:
    transport = guarded(
        BASE_READS.union(*(c.reads for c in profile.checks)),
        frozenset[str]().union(*(c.references for c in profile.checks)),
    )
    report = Report(
        profile=profile.name,
        version=librus_python_api.__version__,
        location="installed"
        if "site-packages" in (librus_python_api.__file__ or "")
        else "source",
        commit=commit,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    async with LibrusService(
        accounts,
        context_key=secrets.token_bytes(32),
        connection=connection,
        transport_factory=transport,
    ) as service:
        for index, alias in enumerate(accounts):
            budget = RequestBudget(
                max_requests=profile.max_requests,
                timeout_seconds=profile.timeout_seconds,
            )
            context = Context(
                service.account(alias), budget, today, (identities or {}).get(alias)
            )
            started = time.monotonic()
            steps = await run_slot(profile.checks, context, transport.violations)
            report.slots.append(
                SlotReport(
                    index,
                    budget.requests_dispatched,
                    round(time.monotonic() - started, 1),
                    steps,
                )
            )
    report.violations = sorted(set(transport.violations))
    return report


def release_problems(report: Report) -> list[str]:
    return [
        problem(slot.slot, step.step, step.kind or step.status.value)
        for slot in report.slots
        for step in slot.steps
        if step.status not in (Status.OK, Status.SKIPPED)
    ]
