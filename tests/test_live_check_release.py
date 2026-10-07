"""The release profile keeps the pre-publication check's reads and verdicts."""

import asyncio
from datetime import date
from typing import Any

from librus_python_api import AccountCredentials, ConnectionSettings, RequestBudget
from librus_python_api.exceptions import ErrorKind, LibrusError
from scripts.live_check.checks import Check, Context, Observed, check
from scripts.live_check.expectations import Expected, compare
from scripts.live_check.profiles import RELEASE
from scripts.live_check.report import (
    Report,
    SlotReport,
    Status,
    StepResult,
    render_json,
)
from scripts.live_check.runner import release_problems, run_profile, run_slot
from tests.http_support import FIXTURE_SECRET, serve
from tests.test_modern_communication import CommunicationFixture

LOGINS = ("student", "parent")
# Captured from the retired single-purpose script before porting.
RELEASE_STEPS = [
    "identity",
    "notification_counts",
    "modern_identity",
    "modern_unread_counts",
    "modern_page received",
    "modern_archive_page received",
    "modern_page sent",
    "modern_archive_page sent",
    "modern_correspondents received",
    "filtered_page received",
    "modern_correspondents sent",
    "filtered_page sent",
    "unread_only_page",
    "modern_teacher_subjects",
    "session_alive",
]


def run_release(
    fixture: CommunicationFixture, identities: dict[str, str] | None = None
) -> Report:
    async def scenario() -> Report:
        fixture.aliases = LOGINS
        async with (
            serve(fixture.app()) as native,
            serve(fixture.modern_app()) as modern,
        ):
            fixture.origin, fixture.modern_origin = native, modern
            report = await run_profile(
                RELEASE,
                {
                    f"slot-{index}": AccountCredentials(
                        login=login, password=FIXTURE_SECRET
                    )
                    for index, login in enumerate(LOGINS)
                },
                today=date(2026, 10, 7),
                identities=identities,
                connection=ConnectionSettings(
                    synergia_origin=native,
                    api_origin=native,
                    messages_origin=modern,
                    download_origin=fixture.download_origin,
                ),
            )
        report.problems = release_problems(report)
        return report

    return asyncio.run(scenario())


def test_release_profile_passes_without_opening_sending_or_consuming() -> None:
    fixture = CommunicationFixture()
    report = run_release(fixture)
    assert report.passed, report.problems
    for slot in report.slots:
        assert [s.step for s in slot.steps] == RELEASE_STEPS
        assert {s.status for s in slot.steps} == {Status.OK}
        assert 0 < slot.requests <= RELEASE.max_requests
    stages = {stage for stage, _, _ in fixture.modern_calls}
    assert not any(stage.rstrip("/").split("/")[-1].isdigit() for stage in stages)
    assert not fixture.sends
    assert all(path != "/uczen/index" for path, _ in fixture.calls)
    assert "Fixture" not in render_json(report)


def test_a_failed_check_fails_the_release_run() -> None:
    fixture = CommunicationFixture()
    fixture.message_count = 0  # A sender filter can then never narrow.
    report = run_release(fixture)
    assert not report.passed
    failed = [
        s for slot in report.slots for s in slot.steps if s.status is Status.FAILED
    ]
    assert failed and all(s.step.startswith("filtered_page") for s in failed)
    assert {s.kind for s in failed} == {"filter_not_narrowed"}


def test_a_wrong_identity_stops_the_slot_before_any_other_read() -> None:
    report = run_release(
        CommunicationFixture(), identities={"slot-0": "999:someone-else"}
    )
    first = report.slots[0].steps
    assert (first[0].status, first[0].kind) == (Status.FAILED, "identity_mismatch")
    assert {s.status for s in first[1:]} == {Status.NOT_RUN}
    assert not report.passed


def test_the_expected_identity_is_accepted() -> None:
    # ModernFixture serves account id 301 + login index; the student id is shared.
    report = run_release(
        CommunicationFixture(),
        identities={"slot-0": "301:student-shared", "slot-1": "302:student-shared"},
    )
    assert report.passed, report.problems


class SessionLost:
    """Stub client: identity works, then the session is gone mid-run."""

    def __init__(self) -> None:
        self.later_calls = 0

    async def identity(self, **_: Any) -> Any:
        return object()

    async def notification_counts(self, **_: Any) -> Any:
        raise LibrusError(ErrorKind.SESSION_EXPIRED)

    async def modern_identity(self, **_: Any) -> Any:
        self.later_calls += 1


def test_a_lost_session_marks_every_later_check_not_run_without_calling_it() -> None:
    client = SessionLost()
    context = Context(client, RequestBudget(max_requests=5), date(2026, 10, 7))
    steps = asyncio.run(run_slot(RELEASE.checks, context))
    assert steps[0].status is Status.OK
    assert (steps[1].status, steps[1].kind) == (Status.ERROR, "session_expired")
    assert {s.status for s in steps[2:]} == {Status.NOT_RUN}  # includes session_alive
    assert client.later_calls == 0


def stub_profile(kind: ErrorKind) -> tuple[Check, ...]:
    @check("parent_view")
    async def parent(_: Context) -> Observed:
        raise LibrusError(kind)

    @check("child_view", after="parent_view")
    async def child(_: Context) -> Observed:
        raise AssertionError("a dependent of a failed check must not run")

    return (parent, child)


def run_stub(checks: tuple[Check, ...]) -> list[StepResult]:
    context = Context(object(), RequestBudget(max_requests=5), date(2026, 10, 7))
    return asyncio.run(run_slot(checks, context))


def test_dependents_of_an_unavailable_view_share_its_expected_coverage() -> None:
    steps = run_stub(stub_profile(ErrorKind.VIEW_DISABLED))
    assert [(s.step, s.status, s.kind) for s in steps] == [
        ("parent_view", Status.ERROR, "view_disabled"),
        ("child_view", Status.ERROR, "view_disabled"),
    ]
    report = Report("weekly", "1.2.1", "installed", "unknown", "now")
    report.slots.append(SlotReport(0, 1, 0.0, steps))
    expected = {0: {"parent_view": Expected.DISABLED, "child_view": Expected.DISABLED}}
    assert compare(report, expected) == []


def test_dependents_of_a_broken_check_are_not_run() -> None:
    steps = run_stub(stub_profile(ErrorKind.PARSE))
    assert [(s.status, s.kind) for s in steps] == [
        (Status.ERROR, "parse"),
        (Status.NOT_RUN, None),
    ]
