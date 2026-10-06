"""Original modern route/selection proofs over isolated real loopback HTTP."""

import asyncio
import base64
import json
from dataclasses import replace
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import (
    MessageFolder,
    MessageReference,
    ModernCorrespondentReference,
    ModernMessageReference,
    ModernRecipientTypeReference,
    RequestBudget,
)
from librus_python_api.config import SchedulerLimits
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.modern_mailbox import (
    parse_correspondents,
    parse_page,
    parse_unread_counts,
)
from librus_python_api.modern_messages import parse_teacher_subjects
from tests.modern_support import ModernFixture, directory

RECEIVED, SENT = MessageFolder.RECEIVED, MessageFolder.SENT

# Invented counters with distinct values, so a misplaced key cannot pass.
UNREAD = {
    "inbox": 1,
    "notes": 2,
    "alerts": 3,
    "substitutions": 4,
    "absences": 5,
    "justifications": 6,
    "trash": 7,
    "archiveInbox": 11,
    "archiveNotes": 12,
    "archiveAlerts": 13,
    "archiveSubstitutions": 14,
    "archiveAbsences": 15,
    "archiveJustifications": 16,
    "archiveTrash": 17,
    "futureCounter": 99,
}


class CommunicationFixture(ModernFixture):
    def __init__(self) -> None:
        super().__init__()
        self.message_count = 23
        self.subject = "Fixture subject"
        self.malformed_page: int | None = None
        # Every live archive page observed on 2026-10-06 reported true.
        self.archiving: Any = True

    async def recipients(self, request: web.Request) -> web.Response:
        self.record_modern(request, "directory")
        return self.response("directory", self.directory_data)

    def modern_app(self) -> web.Application:
        app = super().modern_app()
        for path in (
            "/api/receivers/groups/school-employees",
            "/api/receivers/groups/class-parents",
            "/api/inbox/messages",
            "/api/outbox/messages",
            "/api/archive/inbox/messages",
            "/api/archive/outbox/messages",
            "/api/inbox/unreadMessagesCount",
            "/api/inbox/messages/senders",
            "/api/outbox/messages/receivers",
            "/api/receivers/student-subjects",
            "/api/inbox/messages/{id}",
            "/api/outbox/messages/{id}",
        ):
            app.router.add_get(path, self.communication)
        return app

    async def communication(self, request: web.Request) -> web.Response:
        self.record_modern(request, request.path)
        assert await request.read() == b""
        await self.held_stage("communication")
        default: dict[str, Any] = {"data": [], "total": 0}
        if "/receivers/groups/" in request.path:
            default = {
                "receivers": [
                    {
                        "accountId": "19001",
                        "userId": "19002",
                        "label": "Fixture employee",
                        "availabilityStatus": {"fixture": True},
                    }
                ]
            }
        elif request.path == "/api/inbox/unreadMessagesCount":
            default = {"data": dict(UNREAD)}
        elif request.path.endswith(("/senders", "/receivers")):
            role = "sender" if request.path.endswith("/senders") else "receiver"
            default = {
                "data": [
                    {
                        f"{role}Id": 501,
                        f"{role}FirstName": "",
                        f"{role}LastName": "Office",
                    },
                    {
                        f"{role}Id": 502,
                        f"{role}FirstName": "Fixture",
                        f"{role}LastName": "Teacher",
                    },
                ]
            }
        elif request.path == "/api/receivers/student-subjects":
            default = {
                "data": [
                    {"teacherIdentifier": 502, "subject": "Fixture maths"},
                    {"teacherIdentifier": 502, "subject": "Fixture physics"},
                ]
            }
        elif request.match_info.get("id"):
            default = {
                "data": self.message(int(request.match_info["id"]))
                | {
                    "Message": base64.b64encode(
                        b"<p>Fixture &amp; body</p><p>Second line</p>"
                    ).decode(),
                    "attachments": [{"id": "401", "filename": "Fixture.txt"}],
                }
            }
        else:
            page, size = int(request.query["page"]), int(request.query["limit"])
            count = self.message_count
            if {"senderId", "receiverId", "unreadOnly"} & set(request.query):
                count = 3  # A filtered selection is a different, smaller list.
            first = (page - 1) * size
            default = {
                "data": [
                    self.message(19001 + i)
                    for i in range(first, min(first + size, count))
                ],
                "total": count,
            }
            if page == self.malformed_page:
                default["data"] = []
            if request.path.endswith("/outbox/messages"):
                for item in default["data"]:
                    del item["readDate"]
            if request.path.startswith("/api/archive/"):
                default["archivingInProgress"] = self.archiving
        return self.response(request.path, default)

    def message(self, identifier: int) -> dict[str, Any]:
        return {
            "messageId": str(identifier),
            "senderName": "Fixture sender",
            "receiverName": "Fixture recipient",
            "topic": self.subject,
            "sendDate": "2026-01-15T10:20:30+01:00",
            "readDate": "",
            "isAnyFileAttached": True,
            "content": "Fixture preview, not an opened full body",
        }


@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("folder", list(MessageFolder))
def test_modern_collection_resumes_inside_and_across_pages_without_content_open(
    folder: MessageFolder, archived: bool
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            first = await client.modern_messages(
                folder, page_size=10, limit=7, archived=archived
            )
            assert first.next_cursor is not None and first.next_cursor.offset == 7
            assert first.archived is first.next_cursor.archived is archived
            assert first.archiving_in_progress is (True if archived else None)
            second = await client.modern_messages(
                folder,
                cursor=first.next_cursor,
                page_size=10,
                max_pages=1,
                archived=archived,
            )
            assert (
                second.next_cursor is not None
                and second.next_cursor.page == 2
                and second.next_cursor.offset == 0
            )
            third = await client.modern_messages(
                folder, cursor=second.next_cursor, page_size=10, archived=archived
            )
            assert third.next_cursor is None
            all_items = first.items + second.items + third.items
            assert [i.reference.identifier for i in all_items] == [
                str(19001 + i) for i in range(23)
            ]
            assert all(
                i.reference.account == "student"
                and i.reference.folder is folder
                and i.reference.archived is archived
                for i in all_items
            )
            mailbox = "inbox" if folder is MessageFolder.RECEIVED else "outbox"
            path = f"/api/{'archive/' if archived else ''}{mailbox}/messages"
            assert {p for p, _, _ in fixture.modern_calls if "messages" in p} == {path}
            if folder is MessageFolder.SENT:
                assert all(i.unread is None and i.read_at is None for i in all_items)
            assert fixture.modern_calls[-1][2] == {"page": "3", "limit": "10"}
            assert all("/190" not in path for path, _, _ in fixture.modern_calls)
            assert "Fixture" not in repr(third) and "19001" not in repr(
                first.next_cursor
            )
            assert not fixture.sends

    asyncio.run(scenario())


def test_four_account_mailbox_load_uses_shared_queue_and_isolated_references() -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.block_stage = "communication"
        aliases = tuple(f"fixture-{i}" for i in range(4))
        async with fixture.running(
            aliases,
            scheduler_limits=SchedulerLimits(
                active_requests=2,
                active_requests_per_account=1,
                requests_per_second=1000,
                burst=32,
            ),
        ) as service:
            await asyncio.gather(
                *(service.account(a).modern_identity() for a in aliases)
            )
            tasks = [
                asyncio.create_task(service.account(a).modern_messages())
                for a in aliases
            ]
            try:
                await fixture.started.wait()
                for _ in range(1000):
                    snapshot = service.snapshot()
                    if snapshot.active == 2 and snapshot.queued == 2:
                        break
                    await asyncio.sleep(0.001)
                assert snapshot.active == 2 and snapshot.queued == 2
            finally:
                fixture.release.set()
            results = await asyncio.gather(*tasks)
            assert all(len(result.items) == 23 for result in results)
            assert [result.items[0].reference.account for result in results] == list(
                aliases
            )
            assert {
                login
                for path, login, _ in fixture.modern_calls
                if path == "/api/inbox/messages"
            } == set(aliases)
            assert service.snapshot().active == service.snapshot().queued == 0
            assert not fixture.sends

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["cancel", "timeout", "budget"])
def test_modern_mailbox_cancel_deadline_and_budget_release_slots(mode: str) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            await client.modern_identity()
            if mode != "budget":
                fixture.block_stage = "communication"
            budget = RequestBudget(
                max_requests=1, timeout_seconds=0.1 if mode == "timeout" else 5
            )
            task = asyncio.create_task(
                client.modern_messages(page_size=10, budget=budget)
            )
            try:
                if mode == "cancel":
                    await fixture.started.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(LibrusError) as error:
                        await task
                    assert error.value.kind is (
                        ErrorKind.TIMEOUT if mode == "timeout" else ErrorKind.LIMIT
                    )
                assert budget.requests_dispatched == 1
                assert service.snapshot().active == service.snapshot().queued == 0
                assert not fixture.sends
            finally:
                fixture.release.set()

    asyncio.run(scenario())


def test_cursor_and_content_stay_inside_their_mailbox_before_io() -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            archive = await client.modern_messages(limit=7, archived=True)
            assert archive.next_cursor is not None
            calls = len(fixture.modern_calls)
            # A cursor never continues the other mailbox.
            with pytest.raises(LibrusError) as error:
                await client.modern_messages(cursor=archive.next_cursor)
            assert error.value.kind is ErrorKind.INVALID_INPUT
            current = await client.modern_messages(limit=7)
            assert current.next_cursor is not None
            calls = len(fixture.modern_calls)
            with pytest.raises(LibrusError) as error:
                await client.modern_messages(cursor=current.next_cursor, archived=True)
            assert error.value.kind is ErrorKind.INVALID_INPUT
            # No archived content route or mark-read effect is established.
            for item in archive.items[:1]:
                with pytest.raises(LibrusError) as error:
                    await client.modern_message_content(
                        item.reference, allow_mark_read=True
                    )
                assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
            assert len(fixture.modern_calls) == calls
            assert all("/190" not in path for path, _, _ in fixture.modern_calls)

    asyncio.run(scenario())


@pytest.mark.parametrize("folder", list(MessageFolder))
def test_correspondent_filter_uses_the_web_app_query_and_binds_the_cursor(
    folder: MessageFolder,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            people = await client.modern_correspondents(folder)
            assert [(p.first_name, p.last_name) for p in people.items] == [
                ("", "Office"),
                ("Fixture", "Teacher"),
            ]
            teacher = people.items[1].reference
            assert (teacher.folder, teacher.identifier) == (folder, "502")
            unread = folder is MessageFolder.RECEIVED
            filtered = await client.modern_messages(
                folder, page_size=2, limit=1, correspondent=teacher, unread_only=unread
            )
            key = "senderId" if unread else "receiverId"
            expected = {key: "502"} | ({"unreadOnly": "1"} if unread else {})
            assert fixture.modern_calls[-1][2] == expected | {"page": "1", "limit": "2"}
            assert filtered.correspondent == teacher and filtered.unread_only is unread
            cursor = filtered.next_cursor
            assert cursor is not None and cursor.correspondent == "502"
            calls = len(fixture.modern_calls)
            # The cursor belongs to the filtered list, never the whole mailbox.
            with pytest.raises(LibrusError) as error:
                await client.modern_messages(folder, cursor=cursor, page_size=2)
            assert error.value.kind is ErrorKind.INVALID_INPUT
            assert len(fixture.modern_calls) == calls
            rest = await client.modern_messages(
                folder,
                cursor=cursor,
                page_size=2,
                correspondent=teacher,
                unread_only=unread,
            )
            assert len(filtered.items) + len(rest.items) == 3
            # Filtered and whole-mailbox pages are cached separately.
            whole = await client.modern_messages_page(folder, max_age_seconds=60)
            assert whole.total_count == 23 and whole.correspondent is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "options,kind",
    [
        (
            {"correspondent": ModernCorrespondentReference(SENT, "502", "student")},
            ErrorKind.INVALID_INPUT,
        ),
        (
            {"correspondent": ModernCorrespondentReference(RECEIVED, "502", "parent")},
            ErrorKind.INVALID_INPUT,
        ),
        (
            {"correspondent": ModernCorrespondentReference(RECEIVED, "x", "student")},
            ErrorKind.INVALID_INPUT,
        ),
        ({"folder": SENT, "unread_only": True}, ErrorKind.INVALID_INPUT),
        ({"unread_only": 1}, ErrorKind.INVALID_INPUT),
        ({"archived": True, "unread_only": True}, ErrorKind.UNSUPPORTED_CAPABILITY),
        (
            {
                "archived": True,
                "correspondent": ModernCorrespondentReference(
                    RECEIVED, "502", "student"
                ),
            },
            ErrorKind.UNSUPPORTED_CAPABILITY,
        ),
    ],
)
def test_invalid_or_unobserved_filters_fail_before_io(
    options: dict[str, Any], kind: ErrorKind
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            folder = options.pop("folder", RECEIVED)
            for call in (client.modern_messages, client.modern_messages_page):
                with pytest.raises(LibrusError) as error:
                    await call(folder, **options)
                assert error.value.kind is kind
            assert fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("flag,kind", [(False, None), ("yes", ErrorKind.PARSE)])
def test_archive_status_flag_is_reported_and_must_be_boolean(
    flag: Any, kind: ErrorKind | None
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.archiving = flag
        async with fixture.running() as service:
            client = service.account("student")
            if kind is None:
                page = await client.modern_messages_page(archived=True)
                assert page.archiving_in_progress is False
                assert (
                    await client.modern_messages_page()
                ).archiving_in_progress is None
                return
            with pytest.raises(LibrusError) as error:
                await client.modern_messages_page(archived=True)
            assert error.value.kind is kind

    asyncio.run(scenario())


def test_current_mailbox_still_refuses_an_archiving_flag() -> None:
    body = {"data": [], "total": 0, "archivingInProgress": True}
    with pytest.raises(LibrusError) as error:
        parse_page(json.dumps(body).encode(), MessageFolder.RECEIVED, 1, 10, "student")
    assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY


def test_identical_teacher_subject_rows_collapse_to_one() -> None:
    body = {
        "data": [
            {"teacherIdentifier": 1, "subject": "Fixture maths"},
            {"teacherIdentifier": 2, "subject": "Fixture maths"},
            {"teacherIdentifier": 1, "subject": "Fixture maths"},
        ]
    }
    items = parse_teacher_subjects(json.dumps(body).encode())
    assert [(i.teacher_identifier, i.subject) for i in items] == [
        ("1", "Fixture maths"),
        ("2", "Fixture maths"),
    ]


def test_teacher_subjects_keep_each_teacher_subject_pair() -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            result = await service.account("student").modern_teacher_subjects()
            assert [(i.teacher_identifier, i.subject) for i in result.items] == [
                ("502", "Fixture maths"),
                ("502", "Fixture physics"),
            ]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body",
    [
        {"data": [{"teacherIdentifier": 1, "subject": " "}]},
        {"data": [{"teacherIdentifier": True, "subject": "Fixture"}]},
        {"subjects": []},
    ],
)
def test_teacher_subjects_reject_blank_ambiguous_or_unknown_shapes(
    body: dict[str, Any],
) -> None:
    with pytest.raises(LibrusError) as error:
        parse_teacher_subjects(json.dumps(body).encode())
    assert error.value.kind is ErrorKind.PARSE


@pytest.mark.parametrize(
    "entries",
    [
        [{"senderId": 1, "senderFirstName": " ", "senderLastName": ""}],
        [{"senderId": 1, "senderFirstName": "A", "senderLastName": "B"}] * 2,
        [{"senderId": 1, "senderFirstName": "A"}],
        [{"receiverId": 1, "receiverFirstName": "A", "receiverLastName": "B"}],
    ],
)
def test_correspondents_reject_nameless_duplicate_or_wrong_role_entries(
    entries: list[dict[str, Any]],
) -> None:
    with pytest.raises(LibrusError) as error:
        parse_correspondents(
            json.dumps({"data": entries}).encode(), MessageFolder.RECEIVED, "student"
        )
    assert error.value.kind is ErrorKind.PARSE


def test_unread_counts_keep_current_and_archive_counters_apart() -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            counts = await service.account("student").modern_unread_counts()
            assert counts.identity.owner.id == fixture.account_id("student")
            assert (
                counts.current.inbox,
                counts.current.notes,
                counts.current.alerts,
                counts.current.substitutions,
                counts.current.absences,
                counts.current.justifications,
                counts.current.trash,
            ) == (1, 2, 3, 4, 5, 6, 7)
            assert counts.archive.inbox == 11 and counts.archive.trash == 17
            assert counts.archive.justifications == 16
            assert [p for p, _, _ in fixture.modern_calls if "unread" in p] == [
                "/api/inbox/unreadMessagesCount"
            ]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change,kind",
    [
        (lambda d: d.pop("notes"), ErrorKind.PARSE),
        (lambda d: d.pop("archiveTrash"), ErrorKind.PARSE),
        (lambda d: d.update(inbox=-1), ErrorKind.PARSE),
        (lambda d: d.update(inbox=True), ErrorKind.PARSE),
        (lambda d: d.update(inbox="1"), ErrorKind.PARSE),
        (lambda d: d.update(trash=1000001), ErrorKind.LIMIT),
    ],
)
def test_unread_counts_never_guess_a_missing_or_invalid_counter(
    change: Any, kind: ErrorKind
) -> None:
    data = dict(UNREAD)
    change(data)
    with pytest.raises(LibrusError) as error:
        parse_unread_counts(json.dumps({"data": data}).encode())
    assert error.value.kind is kind


@pytest.mark.parametrize("drift", ["total", "subject", "repeated", "late_failure"])
def test_modern_continuation_refuses_drift_and_never_returns_partial_cache(
    drift: str,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            first = await client.modern_messages(page_size=10, limit=7)
            assert first.next_cursor is not None
            if drift == "total":
                fixture.message_count += 1
            elif drift == "subject":
                fixture.subject = "Changed fixture"
            elif drift == "late_failure":
                fixture.malformed_page = 2
            else:
                first = replace(
                    first,
                    next_cursor=replace(
                        first.next_cursor,
                        page=2,
                        offset=0,
                        seen_ids=tuple(str(19001 + i) for i in range(20)),
                    ),
                )
            with pytest.raises(LibrusError) as error:
                await client.modern_messages(
                    cursor=first.next_cursor, page_size=10, max_age_seconds=60
                )
            assert error.value.kind in {ErrorKind.STALE_CURSOR, ErrorKind.PARSE}
            calls = len(fixture.modern_calls)
            with pytest.raises(LibrusError):
                await client.modern_messages(
                    cursor=first.next_cursor, page_size=10, max_age_seconds=60
                )
            assert len(fixture.modern_calls) > calls
            assert not fixture.sends and service.snapshot().active == 0

    asyncio.run(scenario())


def test_modern_received_open_requires_consent_and_clears_summary_cache() -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            reference = ModernMessageReference(
                MessageFolder.RECEIVED, "19001", "student"
            )
            with pytest.raises(LibrusError) as error:
                await client.modern_message_content(reference)
            assert error.value.kind is ErrorKind.INVALID_INPUT and fixture.calls == []
            page = await client.modern_messages_page(max_age_seconds=60)
            content = await client.modern_message_content(
                reference, allow_mark_read=True
            )
            assert content.text == "Fixture & body\nSecond line"
            assert content.attachments[0].reference.message == reference
            modern_attachment: Any = content.attachments[0].reference
            with pytest.raises(LibrusError) as error:
                client.stream_attachment(modern_attachment)
            assert error.value.kind is ErrorKind.INVALID_INPUT
            assert (
                content.attachments[0].filename == "Fixture.txt"
                and content.may_mark_read
            )
            assert await client.modern_messages_page(max_age_seconds=60) is not page
            assert (
                sum(
                    path == "/api/inbox/messages/19001"
                    for path, _, _ in fixture.modern_calls
                )
                == 1
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "reference",
    [
        MessageReference(MessageFolder.SENT, "19001", "student"),
        ModernMessageReference(MessageFolder.SENT, "19001", "parent"),
        ModernMessageReference(MessageFolder.SENT, "../19001", "student"),
    ],
)
def test_modern_content_rejects_cross_backend_or_account_before_io(
    reference: Any,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            with pytest.raises(LibrusError) as error:
                await service.account("student").modern_message_content(reference)
            assert error.value.kind is ErrorKind.INVALID_INPUT and fixture.calls == []

    asyncio.run(scenario())


def test_modern_sent_content_is_inert_and_unqualified_body_fails_without_retry() -> (
    None
):
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            reference = ModernMessageReference(MessageFolder.SENT, "19001", "student")
            content = await client.modern_message_content(reference)
            assert not content.may_mark_read and content.summary.read_at is None
            fixture.responses["/api/outbox/messages/19001"] = (
                200,
                json.dumps(
                    {
                        "data": fixture.message(19001)
                        | {
                            "Message": base64.b64encode(
                                b"<script>never execute</script>"
                            ).decode(),
                            "attachments": [],
                            "isAnyFileAttached": False,
                        }
                    }
                ).encode(),
                "application/json",
                {},
            )
            with pytest.raises(LibrusError) as error:
                await client.modern_message_content(reference)
            assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
            assert (
                sum(
                    path == "/api/outbox/messages/19001"
                    for path, _, _ in fixture.modern_calls
                )
                == 2
            )
            assert not fixture.sends

    asyncio.run(scenario())


@pytest.mark.parametrize("identifier", ["teachers", "tutors", "sadmin", "classParents"])
def test_employee_and_class_parent_directory_keeps_account_ids_and_no_fake_class(
    identifier: str,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            result = await client.modern_recipients(
                ModernRecipientTypeReference(identifier, "student")
            )
            leaf = result.items[0]
            assert json.loads(leaf.availability_status_json or "null") == {
                "fixture": True
            }
            assert leaf.label == "Fixture employee"
            assert (
                leaf.reference.account_id == "19001"
                and leaf.reference.user_id == "19002"
            )
            assert (
                leaf.reference.class_label == ""
                and leaf.reference.recipient_type == identifier
            )
            assert fixture.modern_calls[-1][2] == {"receiverType": identifier}
            attempt = client.prepare_modern_send(
                recipients=(leaf.reference,), subject="Fixture", body="Fixture"
            )
            assert (
                attempt.submission.recipients == (leaf.reference,) and not fixture.sends
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("envelope", ["classes", "data"])
def test_virtual_selection_has_exact_wire_and_separate_reference_cache(
    envelope: str,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.directory_data = {envelope: directory()["classes"]}
        async with fixture.running() as service:
            client = service.account("student")
            ordinary = ModernRecipientTypeReference("students", "student")
            virtual = ModernRecipientTypeReference(
                "students", "student", include_virtual=True
            )
            first = await client.modern_recipients(ordinary, max_age_seconds=60)
            second = await client.modern_recipients(virtual, max_age_seconds=60)
            assert first is not second
            assert not first.items[0].reference.include_virtual
            assert second.items[0].reference.include_virtual
            assert fixture.modern_calls[-1][2] == {
                "receiverType": "students,virtualStudents"
            }
            assert await client.modern_recipients(ordinary, max_age_seconds=60) is first
            assert await client.modern_recipients(virtual, max_age_seconds=60) is second
            assert not fixture.sends

    asyncio.run(scenario())


def test_discovered_combined_parent_type_can_be_looked_up_without_rewriting() -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        fixture.types_data = {
            "data": {
                "defaultGroup": "parents,guardians",
                "list": [{"id": "parents,guardians", "name": "Fixture guardians"}],
            }
        }
        async with fixture.running() as service:
            client = service.account("student")
            types = await client.modern_recipient_types()
            assert len(types.items) == 1 and types.items[0].lookup_supported
            recipients = await client.modern_recipients(types.items[0].reference)
            assert recipients.items[0].reference.recipient_type == "parents,guardians"
            assert fixture.modern_calls[-1][2] == {"receiverType": "parents,guardians"}
            assert not fixture.sends

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", ["numeric_id", "duplicate", "unknown", "nonfinite"])
def test_employee_directory_refuses_ambiguous_ids_or_unqualified_metadata(
    invalid: str,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        leaf: dict[str, Any] = {
            "accountId": "19001",
            "userId": "19002",
            "label": "Fixture",
        }
        entries = [leaf]
        if invalid == "numeric_id":
            leaf["accountId"] = 19001
        elif invalid == "duplicate":
            entries.append(dict(leaf))
        elif invalid == "unknown":
            leaf["unknownRoutingField"] = "fixture"
        else:
            leaf["availabilityStatus"] = float("nan")
        fixture.responses["/api/receivers/groups/school-employees"] = (
            200,
            json.dumps({"receivers": entries}).encode(),
            "application/json",
            {},
        )
        async with fixture.running() as service:
            with pytest.raises(LibrusError) as error:
                await service.account("student").modern_recipients(
                    ModernRecipientTypeReference("teachers", "student")
                )
            assert error.value.kind in {
                ErrorKind.PARSE,
                ErrorKind.UNSUPPORTED_CAPABILITY,
            }
            assert (
                sum(
                    path == "/api/receivers/groups/school-employees"
                    for path, _, _ in fixture.modern_calls
                )
                == 1
            )
            assert not fixture.sends

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid", ["missing_read", "attachment_flag", "date", "duplicate"]
)
def test_inbox_page_rejects_incomplete_or_ambiguous_summaries(invalid: str) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        row = fixture.message(19001)
        entries = [row]
        if invalid == "missing_read":
            del row["readDate"]
        elif invalid == "attachment_flag":
            row["isAnyFileAttached"] = "false"
        elif invalid == "date":
            row["sendDate"] = "2026-02-31T10:00:00"
        else:
            entries.append(dict(row))
        fixture.responses["/api/inbox/messages"] = (
            200,
            json.dumps({"data": entries, "total": len(entries)}).encode(),
            "application/json",
            {},
        )
        async with fixture.running() as service:
            with pytest.raises(LibrusError) as error:
                await service.account("student").modern_messages_page()
            assert error.value.kind is ErrorKind.PARSE
            assert (
                sum(
                    path == "/api/inbox/messages" for path, _, _ in fixture.modern_calls
                )
                == 1
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("operation", "query", "reference", "path"),
    [
        (
            "modern_school_recipients",
            {"receiverType": "teachers"},
            None,
            "/api/receivers/groups/school-employees",
        ),
        (
            "modern_class_parents",
            {"receiverType": "classParents"},
            None,
            "/api/receivers/groups/class-parents",
        ),
        (
            "modern_messages_received",
            {"page": "1", "limit": "10"},
            None,
            "/api/inbox/messages",
        ),
        (
            "modern_messages_sent",
            {"page": "2", "limit": "50"},
            None,
            "/api/outbox/messages",
        ),
        ("modern_content_received", None, "19001", "/api/inbox/messages/19001"),
        ("modern_content_sent", None, "19001", "/api/outbox/messages/19001"),
    ],
)
def test_fixed_modern_routes_keep_get_selection_and_isolated_cookies(
    operation: str, query: dict[str, str] | None, reference: str | None, path: str
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            budget = RequestBudget(max_requests=9)
            await client.modern_identity(budget=budget)
            result = await client._transport.request(
                operation,
                budget,
                query=query,
                reference_id=reference,
            )
            assert result.status == 200
            assert fixture.modern_calls[-1] == (path, "student", query or {})
            assert budget.requests_dispatched == 9 and not fixture.sends
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("operation", "query", "reference"),
    [
        ("modern_messages_received", None, None),
        ("modern_messages_received", {"page": "0", "limit": "10"}, None),
        ("modern_messages_received", {"page": "1", "limit": "51"}, None),
        ("modern_messages_sent", {"page": "1001", "limit": "10"}, None),
        ("modern_messages_sent", {"page": "1", "limit": "10", "unreadOnly": "1"}, None),
        ("modern_school_recipients", {"receiverType": "parentsCouncil"}, None),
        ("modern_school_recipients", {"receiverType": "../messages"}, None),
        ("modern_class_parents", {"receiverType": "teachers"}, None),
        ("modern_content_sent", None, "19001/withdrawal"),
        ("modern_content_received", {"page": "1", "limit": "10"}, "19001"),
        ("identity", {"page": "1", "limit": "10"}, None),
    ],
)
def test_invalid_modern_query_and_reference_never_dispatch(
    operation: str, query: Any, reference: str | None
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        async with fixture.running() as service:
            client = service.account("student")
            with pytest.raises(LibrusError) as error:
                await client._transport.request(
                    operation,
                    RequestBudget(),
                    query=query,
                    reference_id=reference,
                )
            assert error.value.kind is ErrorKind.INVALID_INPUT
            assert fixture.calls == [] and fixture.modern_calls == []

    asyncio.run(scenario())
