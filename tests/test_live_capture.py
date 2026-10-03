"""Private live captures must never land inside this public repository."""

import asyncio
from pathlib import Path

import pytest

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    RecipientReference,
    SchedulerLimits,
    SendStatus,
)
from librus_python_api.exceptions import UnsupportedCapabilityError
from scripts.capture_attachment_streams import StreamCaptureTransport
from scripts.capture_communication_coverage import CoverageTransport
from scripts.capture_message_content import ContentCaptureTransport
from scripts.capture_messages import MessageCaptureTransport
from scripts.capture_notification_counts import CountCaptureTransport
from scripts.live_capture import (
    REPOSITORY,
    CapturingTransport,
    ReadOnlyCaptureTransport,
    private_directory,
    private_file,
)
from tests.http_support import FIXTURE_SECRET, serve
from tests.notification_persistence_support import NotificationWorkflowFixture
from tests.sending_support import SendFixture


@pytest.mark.parametrize("inside", [REPOSITORY, REPOSITORY / "captures" / "run"])
def test_capture_directory_inside_repository_is_refused(inside: Path) -> None:
    with pytest.raises(SystemExit):
        private_directory(inside)
    assert not (REPOSITORY / "captures").exists()


def test_capture_directory_inside_any_git_work_tree_is_refused(tmp_path: Path) -> None:
    (tmp_path / "other-repo" / ".git").mkdir(parents=True)
    with pytest.raises(SystemExit):
        private_directory(tmp_path / "other-repo" / "captures")
    assert not (tmp_path / "other-repo" / "captures").exists()


def test_capture_directory_is_new_and_owner_only(tmp_path: Path) -> None:
    created = private_directory(tmp_path / "run")
    assert created.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        private_directory(tmp_path / "run")


CAPTURE_TRANSPORTS = (
    CapturingTransport,
    MessageCaptureTransport,
    ContentCaptureTransport,
    CoverageTransport,
    StreamCaptureTransport,
    CountCaptureTransport,
)
BYPASSING_METHODS = (
    "send_message",
    "send_modern_message",
    "authenticate_modern",
    "consume_schedule_events",
)


@pytest.mark.parametrize("transport", CAPTURE_TRANSPORTS)
def test_every_capture_transport_keeps_write_and_read_once_refusals(
    transport: type,
) -> None:
    # These paths skip request()/_exchange(), where the capture allowlists live.
    assert issubclass(transport, ReadOnlyCaptureTransport)
    for name in BYPASSING_METHODS:
        assert getattr(transport, name) is getattr(ReadOnlyCaptureTransport, name)


def capture_service(origin: str) -> LibrusService:
    return LibrusService(
        {"student": AccountCredentials(login="student", password=FIXTURE_SECRET)},
        connection=ConnectionSettings(synergia_origin=origin, api_origin=origin),
        scheduler_limits=SchedulerLimits(requests_per_second=1000, burst=16),
        transport_factory=ReadOnlyCaptureTransport,
    )


def test_capture_transport_refuses_sends_before_dispatch() -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with capture_service(origin) as service:
                client = service.account("student")
                attempt = client.prepare_send(
                    recipients=(RecipientReference("101", "student", "nauczyciel"),),
                    subject="Fixture subject",
                    body="Fixture body",
                )
                with pytest.raises(UnsupportedCapabilityError):
                    await attempt.execute()
                assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
                with pytest.raises(UnsupportedCapabilityError):
                    await client.modern_identity()
        assert fixture.send_calls == []
        assert not any(path.startswith("/wiadomosci3") for path, _ in fixture.calls)

    asyncio.run(scenario())


def test_capture_transport_refuses_read_once_consume() -> None:
    async def scenario() -> None:
        fixture = NotificationWorkflowFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin

            async def persist(response: object) -> None:
                raise AssertionError("A refused consume never reaches a checkpoint")

            async with capture_service(origin) as service:
                with pytest.raises(UnsupportedCapabilityError):
                    await service.account("student").consume_schedule_events(
                        checkpoint=persist, allow_consume_events=True
                    )
        assert fixture.calls_by_account == []

    asyncio.run(scenario())


def test_private_output_file_inside_any_git_work_tree_is_refused(
    tmp_path: Path,
) -> None:
    # Crosscheck --expectations files hold browser-rendered private rows.
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    with pytest.raises(SystemExit):
        private_file(tmp_path / "repo" / "nested" / "expectations.json")
    with pytest.raises(SystemExit):
        private_file(REPOSITORY / "expectations.json")
    outside = tmp_path / "private" / "expectations.json"
    assert private_file(outside) == outside.resolve()
