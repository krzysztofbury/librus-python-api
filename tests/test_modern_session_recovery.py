"""Native/modern expiry isolation and side-effect-free send preflight on wire."""

import asyncio
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import RequestBudget, SendStatus, TransportLimits
from librus_python_api.exceptions import ErrorKind, LibrusError
from tests.http_support import LOGGED_OUT_PAGE
from tests.modern_support import ModernFixture
from tests.test_modern_messages import prepare


@pytest.mark.parametrize("absolute", [False, True])
def test_modern_launch_to_native_login_reports_expiry_not_denial(
    absolute: bool,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            fixture.launch_location = (fixture.origin if absolute else "") + "/loguj"
            attempt = prepare(service.account("student"))
            with pytest.raises(LibrusError) as error:
                await attempt.execute()
            assert error.value.kind is ErrorKind.SESSION_EXPIRED
            assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
            assert fixture.sends == [] and fixture.modern_calls == []
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [401, 403])
def test_warm_modern_send_revalidates_and_clears_only_modern_on_error(
    status: int,
) -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            initial = await client.modern_identity()
            fixture.responses["identity"] = (status, b"", "application/json", {})
            attempt = prepare(client)
            budget = RequestBudget(max_requests=1)
            with pytest.raises(LibrusError) as error:
                await attempt.execute(budget=budget)
            assert error.value.kind is (
                ErrorKind.SESSION_EXPIRED if status == 401 else ErrorKind.ACCESS_DENIED
            )
            assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
            assert fixture.sends == [] and budget.requests_dispatched == 1
            # A messages-origin denial/expiry must not replay legacy credentials.
            profile = await client.student_information(
                budget=RequestBudget(max_requests=1)
            )
            assert (
                profile.observation.session_generation
                == initial.observation.session_generation
            )
            assert fixture.logins == {"student": 1}
            del fixture.responses["identity"]
            ready = await client.modern_identity(budget=RequestBudget(max_requests=3))
            assert ready.account == initial.account
            assert [stage for stage, _, _ in fixture.modern_calls].count("handoff") == 2
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_successful_warm_preflight_is_exactly_one_get_before_one_post() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            await client.modern_identity()
            before = len(fixture.modern_calls)
            budget = RequestBudget(max_requests=2)
            result = await prepare(client).execute(budget=budget)
            assert result.status is SendStatus.UNKNOWN
            assert [stage for stage, _, _ in fixture.modern_calls[before:]] == [
                "identity",
                "send",
            ]
            assert budget.requests_dispatched == 2 and len(fixture.sends) == 1

    asyncio.run(scenario())


def test_modern_send_parse_failure_clears_only_modern_state() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            initial = await client.modern_identity()
            fixture.responses["send"] = (200, b"malformed", "application/json", {})
            result = await prepare(client).execute()
            assert (
                result.status is SendStatus.UNKNOWN and result.reason is ErrorKind.PARSE
            )
            profile = await client.student_information(
                budget=RequestBudget(max_requests=1)
            )
            assert (
                profile.observation.session_generation
                == initial.observation.session_generation
            )
            await client.modern_identity(budget=RequestBudget(max_requests=3))
            assert [stage for stage, _, _ in fixture.modern_calls].count("handoff") == 2
            assert fixture.logins == {"student": 1} and len(fixture.sends) == 1

    asyncio.run(scenario())


class ExpireOnceFixture(ModernFixture):
    expire_stage: str | None = None

    def response(self, stage: str, default: dict[str, Any]) -> web.Response:
        if stage == self.expire_stage:
            self.expire_stage = None
            return web.Response(status=401)
        return super().response(stage, default)


def test_explicit_modern_read_retry_recovers_without_discarding_legacy_session() -> (
    None
):
    async def scenario() -> None:
        fixture = ExpireOnceFixture()
        async with fixture.running(
            transport_limits=TransportLimits(cooldown_seconds=0.001)
        ) as service:
            client = service.account("student")
            initial = await client.modern_recipient_types(max_age_seconds=60)
            fixture.expire_stage = "types"
            budget = RequestBudget(max_requests=5)
            with pytest.raises(LibrusError) as error:
                await client.modern_recipient_types(budget=budget)
            assert error.value.kind is ErrorKind.SESSION_EXPIRED
            assert budget.requests_dispatched == 1
            await asyncio.sleep(0.005)
            recovered = await client.modern_recipient_types(budget=budget)
            assert recovered.items == initial.items
            assert (
                recovered.observation.session_generation
                == initial.observation.session_generation
            )
            assert budget.requests_dispatched == 5
            assert fixture.logins == {"student": 1}
            assert [stage for stage, _, _ in fixture.modern_calls].count("handoff") == 2

    asyncio.run(scenario())


def test_post_dispatch_modern_expiry_is_uncertain_but_does_not_expire_legacy() -> None:
    async def scenario() -> None:
        fixture = ModernFixture()
        async with fixture.running() as service:
            client = service.account("student")
            initial = await client.modern_identity()
            fixture.responses["send"] = (401, b"", "application/json", {})
            result = await prepare(client).execute()
            assert (
                result.status is SendStatus.UNKNOWN
                and result.reason is ErrorKind.SESSION_EXPIRED
            )
            profile = await client.student_information(
                budget=RequestBudget(max_requests=1)
            )
            assert (
                profile.observation.session_generation
                == initial.observation.session_generation
            )
            assert fixture.logins == {"student": 1} and len(fixture.sends) == 1

    asyncio.run(scenario())


class LoggedOutLaunchFixture(ModernFixture):
    """The launch answers 200 with a page instead of redirecting."""

    launch_page: str | None = None
    # How many launches answer with `launch_page` before redirecting again.
    launch_pages = 1

    async def launch(self, request: web.Request) -> web.Response:
        if self.launch_page is None or not self.launch_pages:
            return await super().launch(request)
        self.record(request)
        self.launch_pages -= 1
        return web.Response(text=self.launch_page, content_type="text/html")


def test_a_logged_out_launch_page_signs_in_again_once() -> None:
    # librus-mcp#136, live 2026-11-23: after a GET of /eusprawiedliwienia ended
    # the session, the launch answered 200 with the logged-out page and every
    # modern read failed as UNSUPPORTED_CAPABILITY.
    async def scenario() -> None:
        fixture = LoggedOutLaunchFixture()
        async with fixture.running() as service:
            client = service.account("student")
            await client.identity()
            fixture.launch_page = LOGGED_OUT_PAGE
            result = await client.modern_recipient_types()
            assert len(result.items) == 2
            assert fixture.logins == {"student": 2}
            assert [stage for stage, _, _ in fixture.modern_calls].count("handoff") == 1

    asyncio.run(scenario())


def test_any_other_launch_page_is_still_unsupported() -> None:
    async def scenario() -> None:
        fixture = LoggedOutLaunchFixture()
        async with fixture.running() as service:
            client = service.account("student")
            await client.identity()
            fixture.launch_page = "<html><body><h2>Fixture page</h2></body></html>"
            with pytest.raises(LibrusError) as error:
                await client.modern_recipient_types()
            assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY
            assert fixture.logins == {"student": 1} and fixture.modern_calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("signed_in_first", [True, False])
def test_a_send_never_signs_in_again_after_a_logged_out_launch(
    signed_in_first: bool,
) -> None:
    async def scenario() -> None:
        fixture = LoggedOutLaunchFixture()
        async with fixture.running() as service:
            client = service.account("student")
            if signed_in_first:
                await client.identity()
            fixture.launch_page = LOGGED_OUT_PAGE
            attempt = prepare(client)
            with pytest.raises(LibrusError) as error:
                await attempt.execute()
            assert error.value.kind is ErrorKind.SESSION_EXPIRED
            assert attempt.outcome.status is SendStatus.NOT_DISPATCHED
            assert fixture.sends == [] and fixture.modern_calls == []
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_a_launch_that_stays_logged_out_signs_in_once_more_then_cools_down() -> None:
    # No loop: one more sign-in, then PARSE, then the cooldown answers.
    async def scenario() -> None:
        fixture = LoggedOutLaunchFixture()
        fixture.launch_page, fixture.launch_pages = LOGGED_OUT_PAGE, 10
        async with fixture.running() as service:
            client = service.account("student")
            await client.identity()
            with pytest.raises(LibrusError) as error:
                await client.modern_recipient_types()
            assert error.value.kind is ErrorKind.PARSE
            assert fixture.logins == {"student": 2} and fixture.launch_pages == 8
            with pytest.raises(LibrusError) as again:
                await client.modern_recipient_types()
            assert again.value.kind is ErrorKind.PARSE
            assert fixture.logins == {"student": 2} and fixture.launch_pages == 8

    asyncio.run(scenario())


def test_a_fresh_session_that_gets_a_logged_out_launch_fails_as_parse() -> None:
    async def scenario() -> None:
        fixture = LoggedOutLaunchFixture()
        fixture.launch_page = LOGGED_OUT_PAGE
        async with fixture.running() as service:
            with pytest.raises(LibrusError) as error:
                await service.account("student").modern_recipient_types()
            assert error.value.kind is ErrorKind.PARSE
            assert fixture.logins == {"student": 1} and fixture.modern_calls == []

    asyncio.run(scenario())
