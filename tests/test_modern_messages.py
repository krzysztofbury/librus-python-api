"""Public two-origin discovery/write boundaries, not copied app fixtures."""

import asyncio
import base64
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from librus_python_api import (
    MessageFolder,
    MessagingBackend,
    ModernRecipientReference,
    ModernRecipientTypeReference,
    RecipientReference,
    RequestBudget,
    SendStatus,
)
from librus_python_api.config import SchedulerLimits
from librus_python_api.exceptions import ErrorKind, InvalidInputError, LibrusError
from librus_python_api.modern_messages import (
    parse_modern_recipients,
    parse_modern_send_response,
    parse_modern_types,
)
from tests.modern_support import ModernFixture, directory

REF = ModernRecipientReference(
    "701", "901", "student", "parentsCouncil", "Fixture class"
)
TYPE = ModernRecipientTypeReference("parentsCouncil", "student")


def prepare(client: Any, **changes: Any) -> Any:
    return client.prepare_modern_send(
        **(
            {
                "recipients": (REF,),
                "subject": "Fixture α subject",
                "body": "Fixture body\r\n<plain> &+",
            }
            | changes
        )
    )


@pytest.mark.parametrize("integer_account_id", [False, True])
def test_modern_discovery_binds_class_and_account_and_reuses_account_session(
    integer_account_id: bool,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        if integer_account_id:
            fixture.identity_override = {"accountId": 301}
        async with fixture.running() as service:
            client = service.account("student")
            budget = RequestBudget(max_requests=10)
            types = await client.modern_recipient_types(
                budget=budget, max_age_seconds=60
            )
            assert [
                (t.reference.identifier, t.lookup_supported) for t in types.items
            ] == [("parentsCouncil", True), ("teachers", True)]
            recipients = await client.modern_recipients(
                types.items[0].reference, budget=budget, max_age_seconds=60
            )
            assert len(recipients.items) == 2
            assert recipients.items[0].reference == REF
            assert recipients.items[0].label == "Fixture recipient 0"
            assert recipients.identity.owner.id == "301"
            assert budget.requests_dispatched == 10
            assert fixture.logins == {"student": 1}
            assert await client.modern_recipient_types(max_age_seconds=60) is types
            assert (
                await client.modern_recipients(TYPE, max_age_seconds=60) is recipients
            )
            assert budget.requests_dispatched == 10 and len(fixture.modern_calls) == 4
            before = len(fixture.calls) + len(fixture.modern_calls)
            identity = await client.modern_identity()
            assert identity.account.account_id == "301"
            assert len(fixture.calls) + len(fixture.modern_calls) == before + 1
            assert [s for s, _, _ in fixture.modern_calls].count("handoff") == 1
            assert "Fixture" not in repr(recipients) and "701" not in repr(REF)
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_exact_json_uses_account_id_and_single_attempt_remains_unknown_on_2xx() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            attempt = prepare(service.account("student"))
            assert attempt.outcome.backend is MessagingBackend.MODERN
            assert (
                attempt.outcome.status is SendStatus.NOT_DISPATCHED
                and fixture.calls == []
            )
            with pytest.raises(FrozenInstanceError):
                attempt.submission.subject = "changed"
            budget = RequestBudget(max_requests=9)
            result = await attempt.execute(budget=budget)
            assert (
                result.status is SendStatus.UNKNOWN
                and result.reason is ErrorKind.UNKNOWN_DELIVERY
            )
            assert result.backend is MessagingBackend.MODERN
            assert result.identity is not None and result.identity.owner.id == "301"
            assert (
                result.observation is not None
                and result.observation.source == "modern_send_message"
            )
            login, raw, kind = fixture.sends[0]
            data = json.loads(raw)
            assert login == "student" and kind == "application/json"
            assert data == {
                "receivers": {"schoolReceivers": [{"accountId": "701"}]},
                "topic": "Rml4dHVyZSDOsSBzdWJqZWN0",
                "content": "Rml4dHVyZSBib2R5DQombHQ7cGxhaW4mZ3Q7ICZhbXA7Kw==",
                "storageId": None,
                "category": "normal",
            }
            assert base64.b64decode(data["content"]).decode() == (
                "Fixture body\r\n&lt;plain&gt; &amp;+"
            )
            assert budget.requests_dispatched == 9 and fixture.logins == {"student": 1}
            with pytest.raises(InvalidInputError):
                await attempt.execute()
            assert attempt.outcome is result and len(fixture.sends) == 1
            assert "Fixture" not in repr(result)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changes",
    [
        {"recipients": ()},
        {"recipients": [REF]},
        {"recipients": (REF, REF)},
        {
            "recipients": (
                ModernRecipientReference(
                    "701",
                    "901",
                    "student",
                    [],  # type: ignore[arg-type]
                    "Fixture class",
                ),
            )
        },
        {"recipients": (RecipientReference("701", "student", "rada_rodzicow"),)},
        {
            "recipients": (
                ModernRecipientReference(
                    "701", "901", "parent", "parentsCouncil", "Fixture class"
                ),
            )
        },
        {
            "recipients": (
                ModernRecipientReference(
                    "../701", "901", "student", "parentsCouncil", "Fixture class"
                ),
            )
        },
        {
            "recipients": (
                ModernRecipientReference(
                    "701", "bad", "student", "parentsCouncil", "Fixture class"
                ),
            )
        },
        {
            "recipients": (
                ModernRecipientReference(
                    "701", "901", "student", "teachers", "Fixture class"
                ),
            )
        },
        {
            "recipients": (
                ModernRecipientReference("701", "901", "student", "parentsCouncil", ""),
            )
        },
        {"subject": ""},
        {"subject": "x" * 201},
        {"subject": "x\n"},
        {"body": " \n "},
        {"body": "x\x00y"},
        {"body": "\ud800"},
        {"body": "😀" * 15000},
        {"body": "x" * 15001},
    ],
)
def test_modern_preparation_rejects_invalid_and_cross_backend_references_without_io(
    changes: dict[str, Any],
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            with pytest.raises(InvalidInputError):
                prepare(client, **changes)
            with pytest.raises(InvalidInputError):
                client.prepare_send(
                    recipients=(REF,),  # type: ignore[arg-type]
                    subject="Fixture",
                    body="Fixture",
                )
            assert fixture.calls == [] and fixture.modern_calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change",
    [
        "foreign",
        "wrong_login",
        "query",
        "fragment",
        "percent",
        "send_target",
        "wrong_target",
        "invalid_token",
        "overlong_token",
        "userinfo",
        "backslash",
        "wrong_source",
        "terminal_send",
    ],
)
@pytest.mark.parametrize("namespace", ["pobierz12", "pobierz28", "pobierz31"])
def test_modern_auth_redirects_cannot_leave_exact_account_handoff_or_dispatch_send(
    change: str,
    namespace: str,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            base = (
                f"{fixture.modern_origin}/{namespace}/MultiDomainLogon/token/{'Z' * 32}"
                "/login/c3R1ZGVudA/target/L25vd3k/from/c3luZXJnaWE"
            )
            fixture.launch_location = {
                "foreign": "https://example.invalid/steal",
                "wrong_login": base.replace("c3R1ZGVudA", "cGFyZW50"),
                "query": base + "?x=1",
                "fragment": base + "#x",
                "percent": base.replace("token/", "token/%"),
                "send_target": fixture.modern_origin + "/api/messages",
                "wrong_target": base.replace("L25vd3k", "L2FwaS9tZXNzYWdlcw"),
                "invalid_token": base.replace("Z" * 32, "short"),
                "overlong_token": base.replace("Z" * 32, "Z" * 257),
                "userinfo": base.replace("://", "://fixture-user:fixture-secret@"),
                "backslash": base.replace("/MultiDomainLogon", "\\MultiDomainLogon"),
                "wrong_source": base.replace("c3luZXJnaWE", "b3RoZXI"),
            }.get(change, base)
            if change == "terminal_send":
                fixture.handoff_location = "/api/messages"
            attempt = prepare(service.account("student"))
            with pytest.raises(LibrusError) as caught:
                await attempt.execute()
            assert caught.value.kind is ErrorKind.ACCESS_DENIED
            assert (
                attempt.outcome.status is SendStatus.NOT_DISPATCHED
                and fixture.sends == []
            )
            assert fixture.logins == {"student": 1}
            assert all(stage == "handoff" for stage, _, _ in fixture.modern_calls)
            assert len(fixture.handoff_paths) == (1 if change == "terminal_send" else 0)
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "namespace",
    ["pobierz12", "pobierz28", "pobierz31", "pobierz7", "pobierz987", "pobierz000"],
)
def test_bounded_handoff_namespace_is_followed_once_without_fallback(
    namespace: str,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        fixture.handoff_namespace = namespace
        fixture.handoff_token = "A1zQ" * 32
        async with fixture.running() as service:
            client = service.account("student")
            budget = RequestBudget(max_requests=10)
            types = await client.modern_recipient_types(budget=budget)
            directory = await client.modern_recipients(TYPE, budget=budget)
            assert len(types.items) == len(directory.items) == 2
            assert fixture.handoff_paths == [
                f"/{namespace}/MultiDomainLogon/token/{'A1zQ' * 32}"
                "/login/c3R1ZGVudA/target/L25vd3k/from/c3luZXJnaWE"
            ]
            assert budget.requests_dispatched == 10
            assert fixture.logins == {"student": 1} and fixture.sends == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "namespace",
    [
        "pobierz",
        "pobierz1234",
        "pobierz12x",
        "Pobierz12",
        "pobierz-12",
        "pobierz１２",
        "other12",
    ],
)
def test_invalid_namespace_never_falls_back_to_a_valid_handoff(
    namespace: str,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        fixture.handoff_namespace = namespace
        async with fixture.running() as service:
            with pytest.raises(LibrusError) as error:
                await service.account("student").modern_identity()
            assert error.value.kind is ErrorKind.ACCESS_DENIED
            assert fixture.handoff_paths == []
            assert fixture.modern_calls == []
            assert fixture.sends == []
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "override",
    [
        {"accountId": "999"},
        {"accountId": 999},
        {"accountId": True},
        {"accountId": -301},
        {"accountId": 301.0},
        {"accountId": 10**64},
        {"firstName": "Other"},
        {"lastName": "Other"},
        {"groupId": "50"},
        {"originSystem": "other"},
        {"groupId": []},
    ],
)
def test_modern_identity_mismatch_or_unsupported_role_stops_before_send(
    override: dict[str, Any],
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        fixture.identity_override = override
        async with fixture.running() as service:
            attempt = prepare(service.account("student"))
            with pytest.raises(LibrusError):
                await attempt.execute()
            assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
            assert fixture.sends == [] and [s for s, _, _ in fixture.modern_calls] == [
                "handoff",
                "identity",
            ]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    [
        "disconnect",
        "partial",
        401,
        403,
        429,
        503,
        302,
        500,
        "unknown",
        "positive_hint",
        "rejected",
        "mixed_denial",
        "html",
        "oversize",
    ],
)
def test_modern_send_never_replays_or_infers_acceptance_from_unqualified_marker(
    mode: str | int,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        if mode == "disconnect":
            fixture.disconnect = True
        if mode == "partial":
            fixture.partial = True
        status = mode if type(mode) is int else 200
        body = {
            "unknown": "{}",
            "positive_hint": '{"success":true,"messageId":"123"}',
            "rejected": '{"errors":[{"code":"DUPLICATED_RECEIVERS"}]}',
            "mixed_denial": (
                '{"errors":[{"code":"DUPLICATED_RECEIVERS"},{"code":"OTHER"}]}'
            ),
        }.get(str(mode), "{}")
        if mode in ("rejected", "mixed_denial"):
            status = 422
        if mode == "oversize":
            body = "x" * (4 * 1024 * 1024 + 1)
        fixture.responses["send"] = (
            status,
            body.encode(),
            "text/html" if mode == "html" else "application/json",
            {"Location": "/nowy"} if mode == 302 else {},
        )
        async with fixture.running() as service:
            attempt = prepare(service.account("student"))
            result = await attempt.execute()
            assert result.status is (
                SendStatus.REJECTED if mode == "rejected" else SendStatus.UNKNOWN
            )
            assert len(fixture.sends) == 1 and fixture.logins == {"student": 1}
            assert [s for s, _, _ in fixture.modern_calls] == [
                "handoff",
                "identity",
                "send",
            ]
            with pytest.raises(InvalidInputError):
                await attempt.execute()
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "status_200",
        "status_202",
        "queued",
        "string_id",
        "bool_id",
        "zero_id",
        "negative_id",
        "float_id",
        "oversized_id",
        "missing_id",
        "extra_outer",
        "extra_inner",
        "html",
        "malformed",
        "duplicate_key",
    ],
)
def test_exact_created_sent_receipt_accepts_only_qualified_shape_and_never_replays(
    change: str,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        data: dict[str, Any] = {"data": {"messageId": 19001, "status": "sent"}}
        status = {"status_200": 200, "status_202": 202}.get(change, 201)
        replacements: dict[str, Any] = {
            "string_id": "19001",
            "bool_id": True,
            "zero_id": 0,
            "negative_id": -19001,
            "float_id": 19001.0,
            "oversized_id": 10**64,
        }
        if change in replacements:
            data["data"]["messageId"] = replacements[change]
        if change == "missing_id":
            del data["data"]["messageId"]
        if change == "queued":
            data["data"]["status"] = "queued"
        if change == "extra_outer":
            data["errors"] = []
        if change == "extra_inner":
            data["data"]["other"] = True
        body = json.dumps(data).encode()
        if change == "malformed":
            body = b"not-json"
        if change == "duplicate_key":
            body = b'{"data":{"messageId":19001,"status":"queued","status":"sent"}}'
        fixture.responses["send"] = (
            status,
            body,
            "text/html" if change == "html" else "application/json",
            {},
        )
        async with fixture.running() as service:
            client = service.account("student")
            await client.modern_identity()
            before = len(fixture.modern_calls)
            attempt = prepare(client)
            budget = RequestBudget(max_requests=2)
            result = await attempt.execute(budget=budget)
            assert result.status is (
                SendStatus.ACCEPTED if change == "none" else SendStatus.UNKNOWN
            )
            assert [stage for stage, _, _ in fixture.modern_calls[before:]] == [
                "identity",
                "send",
            ]
            assert len(fixture.sends) == 1 and budget.requests_dispatched == 2
            with pytest.raises(InvalidInputError):
                await attempt.execute()
            assert len(fixture.sends) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["launch", "handoff", "identity", "send"])
@pytest.mark.parametrize("interrupt", ["cancel", "timeout", "shutdown"])
def test_modern_interruptions_join_and_preserve_attempt_boundary(
    stage: str, interrupt: str
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        fixture.block_stage = stage
        async with fixture.running() as service:
            client = service.account("student")
            await client.identity()
            attempt = prepare(client)
            task = asyncio.create_task(
                attempt.execute(
                    budget=RequestBudget(
                        timeout_seconds=0.1 if interrupt == "timeout" else 10
                    )
                )
            )
            await fixture.started.wait()
            if interrupt == "cancel":
                task.cancel()
            if interrupt == "shutdown":
                await service.aclose()
            if interrupt == "timeout":
                if stage == "send":
                    assert (await task).status is SendStatus.UNKNOWN
                else:
                    with pytest.raises(LibrusError):
                        await task
            else:
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert attempt.outcome.status is (
                SendStatus.UNKNOWN if stage == "send" else SendStatus.NOT_DISPATCHED
            )
            assert len(fixture.sends) == (1 if stage == "send" else 0)
            assert service.snapshot().active == service.snapshot().queued == 0
            fixture.release.set()

    asyncio.run(scenario())


@pytest.mark.parametrize("limit", [5, 6, 7, 8])
def test_modern_budget_exhaustion_never_dispatches_a_send_or_reuses_consumed_attempt(
    limit: int,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            attempt = prepare(service.account("student"))
            budget = RequestBudget(max_requests=limit)
            with pytest.raises(LibrusError):
                await attempt.execute(budget=budget)
            assert budget.requests_dispatched == limit and attempt.used
            assert (
                attempt.outcome.status is SendStatus.NOT_DISPATCHED
                and fixture.sends == []
            )
            with pytest.raises(InvalidInputError):
                await attempt.execute()

    asyncio.run(scenario())


@pytest.mark.parametrize("qualified_receipt", [False, True])
def test_four_accounts_share_full_payload_budget_without_coalescing_sends(
    qualified_receipt: bool,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        if qualified_receipt:
            fixture.responses["send"] = (
                201,
                b'{"data":{"messageId":19001,"status":"sent"}}',
                "application/json",
                {},
            )
        aliases = ("student", "parent", "other-student", "other-parent")
        async with fixture.running(aliases) as service:
            attempts = [
                service.account(alias).prepare_modern_send(
                    recipients=tuple(
                        ModernRecipientReference(
                            str(700 + i),
                            str(900 + i),
                            alias,
                            "parentsCouncil",
                            "Fixture class",
                        )
                        for i in range(50)
                    ),
                    subject="x" * 200,
                    body="x" * 15000,
                )
                for alias in aliases
            ]
            budget = RequestBudget(max_requests=36)
            results = await asyncio.gather(
                *(a.execute(budget=budget) for a in attempts)
            )
            expected = SendStatus.ACCEPTED if qualified_receipt else SendStatus.UNKNOWN
            assert all(r.status is expected for r in results)
            assert budget.requests_dispatched == 36 and len(fixture.sends) == 4
            assert {login for login, _, _ in fixture.sends} == set(aliases)
            assert fixture.logins == {alias: 1 for alias in aliases}
            assert {r.identity.owner.id for r in results if r.identity} == {
                "301",
                "302",
                "303",
                "304",
            }
            assert {r.identity.student.id for r in results if r.identity} == {
                "student-shared"
            }
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change",
    [
        "missing_classes",
        "wrong_receivers",
        "multiple_groups",
        "duplicate_class",
        "duplicate_id",
        "wrong_user_id",
        "extra_leaf",
        "unknown_notice",
    ],
)
def test_directory_rejects_ambiguous_or_unsupported_shapes_instead_of_partial_output(
    change: str,
) -> None:
    value = deepcopy(directory())
    if change == "missing_classes":
        value = {}
    elif change == "wrong_receivers":
        value["classes"][0]["receivers"] = {}
    elif change == "multiple_groups":
        value["classes"][0]["receivers"].append([])
    elif change == "duplicate_class":
        value["classes"].append(deepcopy(value["classes"][0]))
    elif change == "duplicate_id":
        value["classes"][0]["receivers"][0][1]["accountId"] = "701"
    elif change == "wrong_user_id":
        value["classes"][0]["receivers"][0][0]["userId"] = 901
    elif change == "extra_leaf":
        value["classes"][0]["receivers"][0][0]["disabled"] = True
    elif change == "unknown_notice":
        value["notice"] = "Unknown unavailable state"
    with pytest.raises(LibrusError):
        parse_modern_recipients(json.dumps(value).encode(), TYPE)


def test_explicit_empty_directory_is_distinct_from_malformed_or_unknown_state() -> None:
    assert parse_modern_recipients(b'{"classes":[]}', TYPE) == ()
    assert (
        parse_modern_recipients(
            b'{"classes":[{"label":"Fixture class","receivers":[[]]}]}', TYPE
        )
        == ()
    )
    with pytest.raises(LibrusError):
        parse_modern_types(
            b'{"data":{"list":[{"id":"parentsCouncil","name":"Fixture"},{"id":"parentsCouncil","name":"Other"}]}}',
            "student",
        )
    with pytest.raises(LibrusError):
        parse_modern_send_response(
            b'{"errors":[{"code":"DUPLICATED_RECEIVERS"}],"data":{"messageId":"1"}}',
            422,
        )


def test_same_account_concurrent_attempts_share_only_authentication_not_sends() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            attempts = [prepare(client), prepare(client)]
            budget = RequestBudget(max_requests=11)
            results = await asyncio.gather(
                *(a.execute(budget=budget) for a in attempts)
            )
            assert all(r.status is SendStatus.UNKNOWN for r in results)
            assert len(fixture.sends) == 2
            assert [stage for stage, _, _ in fixture.modern_calls].count("handoff") == 1
            assert budget.requests_dispatched == 11

    asyncio.run(scenario())


def test_modern_shared_queue_saturation_is_not_dispatched() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running(
            ("student", "parent"),
            scheduler_limits=SchedulerLimits(
                requests_per_second=1000,
                burst=32,
                active_requests=1,
                active_requests_per_account=1,
                queued_requests=0,
                queued_requests_per_account=0,
            ),
        ) as service:
            student, parent = service.account("student"), service.account("parent")
            await student.modern_identity()
            await parent.modern_identity()
            fixture.block_stage = "send"
            first = prepare(student)
            task = asyncio.create_task(first.execute())
            await fixture.started.wait()
            second = parent.prepare_modern_send(
                recipients=(
                    ModernRecipientReference(
                        "701", "901", "parent", "parentsCouncil", "Fixture class"
                    ),
                ),
                subject="Fixture",
                body="Fixture",
            )
            budget = RequestBudget(max_requests=1)
            try:
                with pytest.raises(LibrusError) as caught:
                    await second.execute(budget=budget)
                assert caught.value.kind is ErrorKind.LIMIT
                assert second.outcome.status is SendStatus.NOT_DISPATCHED
                assert budget.requests_dispatched == 0 and len(fixture.sends) == 1
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                fixture.release.set()
            assert first.outcome.status is SendStatus.UNKNOWN
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_modern_unsupported_and_cross_account_lookup_reject_before_io() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            for reference, expected in (
                (
                    ModernRecipientTypeReference("customGroups", "student"),
                    ErrorKind.UNSUPPORTED_CAPABILITY,
                ),
                (
                    ModernRecipientTypeReference("parentsCouncil", "parent"),
                    ErrorKind.INVALID_INPUT,
                ),
            ):
                with pytest.raises(LibrusError) as caught:
                    await client.modern_recipients(reference)
                assert caught.value.kind is expected
            assert fixture.calls == [] and fixture.modern_calls == []

    asyncio.run(scenario())


def test_maximum_directory_load_and_one_over_limit() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        fixture.directory_data = directory(2048)
        async with fixture.running() as service:
            recipients = await service.account("student").modern_recipients(TYPE)
            assert len(recipients.items) == 2048
            assert recipients.items[-1].reference.account_id == "2748"
            assert recipients.items[-1].reference.user_id == "2948"
            assert [s for s, _, _ in fixture.modern_calls] == [
                "handoff",
                "identity",
                "directory",
            ]

    asyncio.run(scenario())
    with pytest.raises(LibrusError) as caught:
        parse_modern_recipients(json.dumps(directory(2049)).encode(), TYPE)
    assert caught.value.kind is ErrorKind.LIMIT


def test_modern_dispatch_invalidates_sent_cache_not_received_summaries() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            received = await client.messages_page(
                MessageFolder.RECEIVED, max_age_seconds=60
            )
            await client.messages_page(MessageFolder.SENT, max_age_seconds=60)
            await client.messages(MessageFolder.SENT, max_pages=1, max_age_seconds=60)
            await prepare(client).execute()
            before = fixture.count("messages_sent")
            await client.messages_page(MessageFolder.SENT, max_age_seconds=60)
            await client.messages(MessageFolder.SENT, max_pages=1, max_age_seconds=60)
            assert fixture.count("messages_sent") == before + 2
            assert (
                await client.messages_page(MessageFolder.RECEIVED, max_age_seconds=60)
                is received
            )

    asyncio.run(scenario())
