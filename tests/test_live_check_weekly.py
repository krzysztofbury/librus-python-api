"""The weekly profile reaches every safe read and nothing else."""

from datetime import date

import pytest

from librus_python_api import AccountClient
from scripts.live_check.profiles import RELEASE, WEEKLY, month_bounds
from scripts.live_check.report import Status, render_json, render_summary
from scripts.live_check.runner import Profile
from tests.http_support import FIXTURE_SECRET
from tests.live_check_support import WeeklyFixture, run_fixture
from tests.school_year_archive_support import CANARY_NAME

CANARY_LOGINS = ("canary-login-a", "canary-login-b")
WEEKLY_ONLY = [
    "student_information",
    "grades",
    "grades_window",
    "final_grades",
    "school_year_archive",
    "attendance",
    "attendance_window",
    "attendance_detail",
    "attendance_frequency",
    "subject_frequency",
    "timetable",
    "agenda",
    "agenda_detail",
    "homework",
    "homework_detail",
    "announcements",
    "completed_lessons",
    "legacy_messages received",
    "legacy_messages sent",
    "legacy_sent_content",
    "recipient_groups",
    "recipients",
    "modern_recipient_types",
    "modern_recipients",
    "modern_sent_content",
]


@pytest.mark.parametrize(
    "day,bounds",
    [
        (date(2026, 10, 7), (date(2026, 10, 1), date(2026, 10, 31))),
        (date(2026, 12, 15), (date(2026, 12, 1), date(2026, 12, 31))),
        (date(2028, 2, 29), (date(2028, 2, 1), date(2028, 2, 29))),
    ],
)
def test_month_bounds_cover_the_whole_calendar_month(
    day: date, bounds: tuple[date, date]
) -> None:
    assert month_bounds(day) == bounds


def test_weekly_extends_release_and_ends_with_session_alive() -> None:
    names = [c.name for c in WEEKLY.checks]
    release = [c.name for c in RELEASE.checks]
    assert names[: len(release) - 1] == release[:-1]
    assert names[len(release) - 1 : -1] == WEEKLY_ONLY
    assert names[-1] == "session_alive"


def test_weekly_profile_runs_every_check_without_side_effects() -> None:
    fixture = WeeklyFixture()
    report = run_fixture(WEEKLY, fixture, CANARY_LOGINS)
    assert report.violations == []
    for slot in report.slots:
        bad = [
            (s.step, s.status, s.kind) for s in slot.steps if s.status is not Status.OK
        ]
        assert bad == []
        assert slot.requests <= WEEKLY.max_requests
    # Detail and sent-content reads used items from this run's lists.
    for operation in (
        "attendance_detail",
        "agenda_detail",
        "homework_detail",
        "message_content_sent",
        "school_year_archive",
    ):
        assert fixture.count(operation) == len(CANARY_LOGINS), operation
    assert fixture.count("message_content_received") == 0
    stages = [stage for stage, _, _ in fixture.modern_calls]
    assert any(
        s.startswith("/api/outbox/messages/") and s.split("/")[-1].isdigit()
        for s in stages
    )
    assert not any(
        s.startswith("/api/inbox/messages/") and s.split("/")[-1].isdigit()
        for s in stages
    )
    assert not fixture.sends


def test_weekly_skips_archive_when_an_older_library_lacks_the_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(AccountClient, "school_year_archive")
    fixture = WeeklyFixture()
    report = run_fixture(WEEKLY, fixture, ("student",))
    steps = report.slots[0].steps
    archive = next(step for step in steps if step.step == "school_year_archive")
    assert archive.status is Status.SKIPPED
    assert fixture.count("school_year_archive") == 0
    assert steps[-1].status is Status.OK
    assert report.violations == []


def test_weekly_output_carries_no_credentials_or_school_text() -> None:
    report = run_fixture(WEEKLY, WeeklyFixture(), CANARY_LOGINS)
    output = render_json(report) + render_summary(report)
    for canary in (
        *CANARY_LOGINS,
        FIXTURE_SECRET,
        "Fixture",
        "Synthetic",
        "student-shared",
        CANARY_NAME,
    ):
        assert canary not in output


@pytest.mark.parametrize("profile", [RELEASE, WEEKLY], ids=lambda p: p.name)
def test_a_lost_session_is_never_repaired_by_logging_in_again(
    profile: Profile,
) -> None:
    fixture = WeeklyFixture()
    # The counter page redirects to login, as after an upstream logout.
    fixture.failures["student_information"] = [302]
    report = run_fixture(profile, fixture, ("student",))
    assert fixture.logins == {"student": 1}
    assert report.violations == ["login_submit"]
    steps = report.slots[0].steps
    assert steps[0].status is Status.OK
    assert (steps[1].step, steps[1].status) == ("notification_counts", Status.ERROR)
    assert {s.status for s in steps[2:]} == {Status.NOT_RUN}
    assert not report.passed
