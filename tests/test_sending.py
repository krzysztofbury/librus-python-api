"""Owning attempt lifecycle, independent exact wire form and uncertainty proofs."""

import asyncio
from dataclasses import FrozenInstanceError
from typing import Any
from urllib.parse import parse_qsl

import pytest

from librus_python_api import (
    MessageFolder,
    RecipientReference,
    RequestBudget,
    SendStatus,
)
from librus_python_api.config import SchedulerLimits
from librus_python_api.exceptions import ErrorKind, InvalidInputError, LibrusError
from librus_python_api.sending import parse_send_acknowledgement
from tests.http_support import FIXTURE_SECRET, serve
from tests.sending_support import SendFixture, acknowledgement

REF = RecipientReference("101", "student", "nauczyciel")


def prepare(client: Any, **kwargs: Any) -> Any:
    return client.prepare_send(
        recipients=(REF,), subject="Fixture subject", body="Fixture body", **kwargs
    )


def test_local_frozen_attempt_preserves_exact_repeated_wire_fields() -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                attempt = client.prepare_send(
                    recipients=(
                        REF,
                        RecipientReference("102", "student", "grupa", "301"),
                    ),
                    subject="Fixture subject &+",
                    body="Fixture α body\r\nLine two\t&+",
                )
                assert (
                    not attempt.used
                    and attempt.outcome.status is SendStatus.NOT_DISPATCHED
                )
                assert fixture.calls == []
                assert "Fixture" not in repr(attempt) and "Fixture" not in repr(
                    attempt.submission
                )
                with pytest.raises(FrozenInstanceError):
                    attempt.submission.body = "changed"  # type: ignore[misc]
                budget = RequestBudget(max_requests=6)
                result = await attempt.execute(budget=budget)
                assert (
                    result is attempt.outcome and result.status is SendStatus.ACCEPTED
                )
                assert result.identity is not None and result.observation is not None
                assert (
                    result.identity.owner.id == "student"
                    and result.identity.student.id == "student-shared"
                )
                assert result.observation.source == "send_message"
                assert "student" not in repr(result)
                assert fixture.logins == {"student": 1}
                assert budget.requests_dispatched == 6
                assert len(fixture.send_calls) == 1
                login, form, raw = fixture.send_calls[0]
                expected = [
                    ("filtrUzytkownikow", "0"),
                    ("idPojemnika", ""),
                    ("DoKogo", "101"),
                    ("DoKogo", "102"),
                    ("Rodzaj", "0"),
                    ("temat", "Fixture subject &+"),
                    ("tresc", "Fixture α body\r\nLine two\t&+"),
                    ("poprzednia", "5"),
                    ("fileStorageIdentifier", ""),
                    ("wyslij", "Wyślij"),
                ]
                assert login == "student" and form == expected
                assert (
                    parse_qsl(raw.decode("ascii"), keep_blank_values=True) == expected
                )
                with pytest.raises(InvalidInputError):
                    await attempt.execute()
                assert attempt.outcome is result and len(fixture.send_calls) == 1
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changes",
    [
        {"recipients": ()},
        {"recipients": [REF]},
        {"recipients": (REF, REF)},
        {"recipients": (RecipientReference("101", "parent", "nauczyciel"),)},
        {"recipients": (RecipientReference("../101", "student", "nauczyciel"),)},
        {"recipients": (RecipientReference("101", "student", "nauczyciel", "301"),)},
        {"subject": ""},
        {"subject": "  "},
        {"subject": "x" * 201},
        {"body": ""},
        {"body": " \r\n "},
        {"body": "x" * 15001},
        {"subject": "Fixture\nsubject"},
        {"body": "Fixture\x00body"},
        {"body": "Fixture\ud800body"},
        {"body": "😀" * 15000},
        {
            "recipients": tuple(
                RecipientReference(str(i), "student", "nauczyciel") for i in range(51)
            )
        },
    ],
)
def test_invalid_payloads_fail_before_transport_or_authentication(
    changes: dict[str, Any],
) -> None:
    fixture = SendFixture()
    fixture.origin = "http://localhost:8080"
    service = fixture.service()
    with pytest.raises(InvalidInputError):
        service.account("student").prepare_send(
            **(
                {
                    "recipients": (REF,),
                    "subject": "Fixture subject",
                    "body": "Fixture body",
                }
                | changes
            )
        )
    assert fixture.calls == []


@pytest.mark.parametrize(
    "message,status",
    [
        ("Wiadomość została wysłana.", SendStatus.ACCEPTED),
        ("Wiadomość nie została wysłana.", SendStatus.REJECTED),
    ],
)
def test_exact_designated_acknowledgement_is_not_substring_interpretation(
    message: str, status: SendStatus
) -> None:
    assert parse_send_acknowledgement(acknowledgement(message).encode()) is status


@pytest.mark.parametrize(
    "body",
    [
        acknowledgement("Unknown state"),
        acknowledgement("Wiadomość nie została wysłana. Wiadomość została wysłana."),
        acknowledgement().replace("<p>", "<p>quoted: "),
        "<html><p>Wiadomość została wysłana.</p></html>",
        '<div class="container-message-content">Wiadomość została wysłana.</div>',
        '<html><body><div class="container-message-content">'
        '<div class="container-background"><p>Wiadomość została wysłana.</p>'
        "</div></div></body></html>",
        acknowledgement().replace(
            "</div>", "<p>Wiadomość nie została wysłana.</p></div>"
        ),
        acknowledgement().replace(
            "</body>", '<div class="warning-content">Unknown warning</div></body>'
        ),
        acknowledgement().replace(
            "Wiadomość została wysłana.", "<script>unsafe()</script>"
        ),
    ],
)
def test_unknown_misleading_or_contradictory_acknowledgement_never_accepts(
    body: str,
) -> None:
    with pytest.raises(LibrusError):
        parse_send_acknowledgement(body.encode())


@pytest.mark.parametrize(
    "mode",
    [
        "accepted",
        "rejected",
        "unknown",
        "disconnect",
        "partial_response",
        401,
        403,
        429,
        500,
        503,
        302,
        "wrong_type",
        "oversize",
        "parse_limit",
    ],
)
def test_dispatched_failure_or_response_has_one_attempt_and_explicit_outcome(
    mode: str | int,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        if mode == "rejected":
            fixture.send_body = acknowledgement("Wiadomość nie została wysłana.")
        if mode == "unknown":
            fixture.send_body = acknowledgement("Unknown acknowledgement")
        if mode == "disconnect":
            fixture.disconnect = True
        if mode == "partial_response":
            fixture.partial_response = True
        if isinstance(mode, int):
            fixture.send_status = mode
        if mode == 302:
            fixture.send_headers = {"Location": "/loguj"}
        if mode == "wrong_type":
            fixture.send_content_type = "application/json"
        if mode == "oversize":
            fixture.send_body = "x" * (4 * 1024 * 1024 + 1)
        if mode == "parse_limit":
            fixture.send_body = "x" * 1048577
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                attempt = prepare(client)
                result = await attempt.execute()
                expected = (
                    SendStatus.ACCEPTED
                    if mode == "accepted"
                    else SendStatus.REJECTED
                    if mode == "rejected"
                    else SendStatus.UNKNOWN
                )
                assert result.status is expected and result is attempt.outcome
                assert len(fixture.send_calls) == 1 and fixture.logins == {"student": 1}
                assert len(fixture.calls) == 6
                with pytest.raises(InvalidInputError):
                    await attempt.execute()
                assert len(fixture.send_calls) == 1
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_two_distinct_attempts_are_not_cached_or_coalesced() -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first, second = prepare(client), prepare(client)
                results = await asyncio.gather(first.execute(), second.execute())
                assert all(r.status is SendStatus.ACCEPTED for r in results)
                assert len(fixture.send_calls) == 2 and fixture.logins == {"student": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize("interruption", ["cancel", "timeout", "shutdown"])
def test_post_dispatch_interruption_joins_and_preserves_inspectable_unknown(
    interruption: str,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.send_hold = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                attempt = prepare(client)
                task = asyncio.create_task(
                    attempt.execute(
                        budget=RequestBudget(
                            timeout_seconds=0.1 if interruption == "timeout" else 10
                        )
                    )
                )
                await fixture.send_started.wait()
                assert attempt.outcome.status is SendStatus.UNKNOWN
                with pytest.raises(InvalidInputError):
                    await attempt.execute()
                if interruption == "cancel":
                    task.cancel()
                if interruption == "shutdown":
                    await service.aclose()
                if interruption == "timeout":
                    result = await task
                    assert (
                        result.status is SendStatus.UNKNOWN
                        and result.reason is ErrorKind.TIMEOUT
                    )
                else:
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert attempt.outcome.status is SendStatus.UNKNOWN
                assert len(fixture.send_calls) == 1 and fixture.logins == {"student": 1}
                assert service.snapshot().active == service.snapshot().queued == 0
                fixture.send_hold.set()

    asyncio.run(scenario())


@pytest.mark.parametrize("limit", [1, 4, 5])
def test_pre_dispatch_auth_or_budget_failure_is_not_dispatched_and_consumes_attempt(
    limit: int,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                attempt = prepare(service.account("student"))
                with pytest.raises(LibrusError):
                    await attempt.execute(budget=RequestBudget(max_requests=limit))
                assert (
                    attempt.outcome.status is SendStatus.NOT_DISPATCHED and attempt.used
                )
                assert fixture.send_calls == []
                with pytest.raises(InvalidInputError):
                    await attempt.execute()
                assert fixture.send_calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("accepted", [True, False])
def test_dispatch_invalidates_sent_page_and_batch_even_when_response_is_unknown(
    accepted: bool,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        if not accepted:
            fixture.send_body = acknowledgement("Unknown acknowledgement")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                received = await client.messages_page(
                    MessageFolder.RECEIVED, max_age_seconds=60
                )
                await client.messages_page(MessageFolder.SENT, max_age_seconds=60)
                await client.messages(
                    MessageFolder.SENT, max_pages=1, max_age_seconds=60
                )
                await prepare(client).execute()
                before = fixture.count("messages_sent")
                await client.messages_page(MessageFolder.SENT, max_age_seconds=60)
                await client.messages(
                    MessageFolder.SENT, max_pages=1, max_age_seconds=60
                )
                assert fixture.count("messages_sent") == before + 2
                assert (
                    await client.messages_page(
                        MessageFolder.RECEIVED, max_age_seconds=60
                    )
                    is received
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["authentication", "lock", "scheduler"])
@pytest.mark.parametrize("interruption", ["cancel", "timeout", "shutdown"])
def test_pre_dispatch_interruption_never_crosses_http_boundary(
    stage: str, interruption: str
) -> None:
    class AuthFixture(SendFixture):
        async def submit(self, request: Any) -> Any:
            response = await super().submit(request)
            self.held.set()
            assert self.hold is not None
            await self.hold.wait()
            return response

    async def scenario() -> None:
        fixture = AuthFixture() if stage == "authentication" else SendFixture()
        blocker: asyncio.Task[Any] | None = None
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            aliases = ("student", "parent") if stage == "scheduler" else ("student",)
            async with fixture.service(
                aliases,
                scheduler_limits=SchedulerLimits(
                    active_requests=1, requests_per_second=1000, burst=16
                ),
            ) as service:
                if stage != "authentication":
                    for alias in aliases:
                        await service.account(alias).identity()
                    fixture.hold = asyncio.Event()
                    blocker = asyncio.create_task(
                        service.account("student").messages_page()
                    )
                    await fixture.held.wait()
                else:
                    fixture.hold = asyncio.Event()
                alias = "parent" if stage == "scheduler" else "student"
                attempt = service.account(alias).prepare_send(
                    recipients=(RecipientReference("101", alias, "nauczyciel"),),
                    subject="Fixture subject",
                    body="Fixture body",
                )
                task = asyncio.create_task(
                    attempt.execute(
                        budget=RequestBudget(
                            timeout_seconds=0.1 if interruption == "timeout" else 10
                        )
                    )
                )
                if stage == "authentication":
                    await fixture.held.wait()
                else:
                    for _ in range(1000):
                        if attempt.used and (
                            stage != "scheduler" or service.snapshot().queued == 1
                        ):
                            break
                        await asyncio.sleep(0)
                    assert attempt.used
                    if stage == "scheduler":
                        assert service.snapshot().queued == 1
                assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
                if interruption == "cancel":
                    task.cancel()
                if interruption == "shutdown":
                    await service.aclose()
                if interruption == "timeout":
                    with pytest.raises(LibrusError) as caught:
                        await task
                    assert caught.value.kind is ErrorKind.TIMEOUT
                else:
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
                assert fixture.send_calls == []
                with pytest.raises(InvalidInputError):
                    await attempt.execute()
                assert fixture.hold is not None
                fixture.hold.set()
                if blocker is not None:
                    await asyncio.gather(blocker, return_exceptions=True)
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_rejected_credentials_fail_before_dispatch_without_reauthentication() -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("rejected",)) as service:
                attempt = service.account("rejected").prepare_send(
                    recipients=(RecipientReference("101", "rejected", "nauczyciel"),),
                    subject="Fixture",
                    body="Fixture",
                )
                with pytest.raises(LibrusError) as caught:
                    await attempt.execute()
                assert caught.value.kind is ErrorKind.CREDENTIALS_REJECTED
                assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
                assert fixture.send_calls == [] and fixture.logins == {"rejected": 1}

    asyncio.run(scenario())


def test_four_accounts_share_exact_budget_for_full_bounded_payloads() -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        aliases = ("student", "parent", "other-student", "other-parent")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(aliases) as service:
                attempts = [
                    service.account(alias).prepare_send(
                        recipients=tuple(
                            RecipientReference(str(100 + i), alias, "nauczyciel")
                            for i in range(50)
                        ),
                        subject="x" * 200,
                        body="x" * 15000,
                    )
                    for alias in aliases
                ]
                budget = RequestBudget(max_requests=24)
                results = await asyncio.gather(
                    *(a.execute(budget=budget) for a in attempts)
                )
                assert all(
                    r.status is SendStatus.ACCEPTED
                    and r.identity is not None
                    and r.identity.student.id == "student-shared"
                    for r in results
                )
                assert {
                    r.identity.owner.id for r in results if r.identity is not None
                } == set(aliases)
                assert budget.requests_dispatched == 24
                assert len(fixture.send_calls) == 4 and {
                    c[0] for c in fixture.send_calls
                } == set(aliases)
                assert fixture.logins == {alias: 1 for alias in aliases}
                assert all(
                    len([v for k, v in c[1] if k == "DoKogo"]) == 50
                    for c in fixture.send_calls
                )
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "message,status",
    [
        ("Wiadomość została wysłana.", SendStatus.ACCEPTED),
        ("Wiadomość nie została wysłana.", SendStatus.REJECTED),
    ],
)
def test_acknowledged_outcome_survives_cancellation_at_owned_worker_completion(
    message: str, status: SendStatus
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        fixture.send_body = acknowledgement(message)
        caller: asyncio.Task[Any] | None = None

        def diagnostic(event: Any) -> None:
            if event.operation == "send_message":
                assert caller is not None
                caller.cancel()

        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(diagnostic_sink=diagnostic) as service:
                attempt = prepare(service.account("student"))
                caller = asyncio.create_task(attempt.execute())
                with pytest.raises(asyncio.CancelledError):
                    await caller
                assert (
                    attempt.outcome.status is status and attempt.outcome.reason is None
                )
                assert len(fixture.send_calls) == 1
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_request_byte_bound_applies_to_encoded_form_not_only_unicode_characters() -> (
    None
):
    from librus_python_api import SendSubmission
    from librus_python_api.config import SEND_MAX_REQUEST_BYTES, encode_send_form

    initial = SendSubmission((REF,), "Fixture", "")
    overhead = (
        len(encode_send_form(SendSubmission((REF,), "Fixture", "x"), "student")) - 1
    )
    # Each Unicode symbol takes nine percent-encoded bytes, unlike one char.
    count = (SEND_MAX_REQUEST_BYTES - overhead) // 9
    payload = encode_send_form(
        SendSubmission(initial.recipients, initial.subject, "€" * count), "student"
    )
    assert len(payload) <= SEND_MAX_REQUEST_BYTES
    assert len(payload) > SEND_MAX_REQUEST_BYTES - 9
    with pytest.raises(InvalidInputError):
        encode_send_form(
            SendSubmission(initial.recipients, initial.subject, "€" * (count + 1)),
            "student",
        )


def test_generic_request_cannot_enter_write_or_modern_handoff_with_any_form() -> None:
    from librus_python_api import LibrusService
    from librus_python_api.config import AccountCredentials, ConnectionSettings

    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with LibrusService(
                {
                    "student": AccountCredentials(
                        login="student", password=FIXTURE_SECRET
                    )
                },
                connection=ConnectionSettings(
                    synergia_origin=origin, api_origin=origin, messages_origin=origin
                ),
            ) as service:
                client = service.account("student")
                for form in (
                    None,
                    {"wyslij": "Wyślij"},
                    {"numer_strony105": "0", "porcjowanie_pojemnik105": "105"},
                ):
                    for endpoint in (
                        "send_message",
                        "modern_send_message",
                        "modern_launch",
                        "modern_handoff",
                    ):
                        budget = RequestBudget()
                        with pytest.raises(InvalidInputError):
                            await client._transport.request(endpoint, budget, form=form)
                        assert budget.requests_dispatched == 0
                assert fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("limit", ["operations", "queue"])
def test_saturated_admission_rejects_write_without_marking_dispatch(limit: str) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        limits = SchedulerLimits(
            active_requests=1,
            requests_per_second=1000,
            burst=16,
            operations=1 if limit == "operations" else 32,
            operations_per_account=1,
            queued_requests=0 if limit == "queue" else 8,
            queued_requests_per_account=0 if limit == "queue" else 8,
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(
                ("student", "parent"), scheduler_limits=limits
            ) as service:
                await service.account("student").identity()
                await service.account("parent").identity()
                fixture.hold = asyncio.Event()
                blocker = asyncio.create_task(
                    service.account("student").messages_page()
                )
                await fixture.held.wait()
                attempt = service.account("parent").prepare_send(
                    recipients=(RecipientReference("101", "parent", "nauczyciel"),),
                    subject="Fixture",
                    body="Fixture",
                )
                with pytest.raises(LibrusError) as caught:
                    await attempt.execute()
                assert caught.value.kind is ErrorKind.LIMIT
                assert (
                    attempt.used and attempt.outcome.status is SendStatus.NOT_DISPATCHED
                )
                assert fixture.send_calls == []
                fixture.hold.set()
                await blocker
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["invalid_budget", "closed", "response_budget"])
def test_explicit_budget_and_closed_service_have_correct_attempt_boundary(
    failure: str,
) -> None:
    async def scenario() -> None:
        fixture = SendFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                attempt = prepare(client)
                if failure == "closed":
                    await service.aclose()
                if failure == "response_budget":
                    result = await attempt.execute(
                        budget=RequestBudget(max_response_bytes=16)
                    )
                    assert (
                        result.status is SendStatus.UNKNOWN
                        and result.reason is ErrorKind.LIMIT
                    )
                    assert len(fixture.send_calls) == 1
                else:
                    with pytest.raises(LibrusError) as caught:
                        await attempt.execute(
                            budget=object() if failure == "invalid_budget" else None
                        )
                    assert caught.value.kind is (
                        ErrorKind.INVALID_INPUT
                        if failure == "invalid_budget"
                        else ErrorKind.CLOSED
                    )
                    assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
                    assert fixture.send_calls == []
                assert attempt.used

    asyncio.run(scenario())


@pytest.mark.parametrize("after_boundary", [False, True])
def test_custom_transport_private_failure_is_redacted_and_keeps_dispatch_state(
    after_boundary: bool,
) -> None:
    from collections.abc import Callable

    from librus_python_api import (
        AccountCredentials,
        ConnectionSettings,
        LibrusService,
        SendSubmission,
    )
    from librus_python_api.models import TransportResponse
    from librus_python_api.transport import AiohttpTransport

    class BrokenTransport(AiohttpTransport):
        async def send_message(
            self,
            submission: SendSubmission,
            budget: RequestBudget,
            dispatched: Callable[[], None],
        ) -> TransportResponse:
            if after_boundary:
                dispatched()
            raise RuntimeError("Fixture private target and payload")

    async def scenario() -> None:
        fixture = SendFixture()
        events: list[Any] = []
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with LibrusService(
                {
                    "student": AccountCredentials(
                        login="student", password=FIXTURE_SECRET
                    )
                },
                connection=ConnectionSettings(
                    synergia_origin=origin, api_origin=origin
                ),
                transport_factory=BrokenTransport,
                diagnostic_sink=events.append,
            ) as service:
                attempt = prepare(service.account("student"))
                if after_boundary:
                    result = await attempt.execute()
                    assert (
                        result.status is SendStatus.UNKNOWN
                        and result.reason is ErrorKind.CONNECTION
                    )
                    assert "Fixture" not in repr(result)
                else:
                    with pytest.raises(LibrusError) as caught:
                        await attempt.execute()
                    assert caught.value.kind is ErrorKind.CONNECTION
                    assert caught.value.__cause__ is caught.value.__context__ is None
                    assert "Fixture" not in str(caught.value)
                    assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
                assert fixture.send_calls == [] and len(fixture.calls) == 5
                assert "Fixture" not in repr(events)
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())
