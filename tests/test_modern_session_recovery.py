"""Native/modern expiry isolation and side-effect-free send preflight on wire."""

import asyncio
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import RequestBudget, SendStatus, TransportLimits
from librus_python_api.exceptions import ErrorKind, LibrusError
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
