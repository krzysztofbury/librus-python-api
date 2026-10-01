"""Original wire fixtures for the fixed grade-view POST, not upstream captures."""

import asyncio

import pytest

from librus_python_api import RequestBudget
from librus_python_api.exceptions import InvalidInputError
from librus_python_api.models import LoginSubmission
from tests.http_support import SchoolFixture, serve


def test_login_credentials_cannot_be_submitted_to_grade_view_route() -> None:
    async def scenario() -> None:
        fixture = SchoolFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                before = service.snapshot().requests_dispatched
                with pytest.raises(InvalidInputError):
                    await client._transport.request(
                        "grades",
                        RequestBudget(),
                        form=LoginSubmission(
                            client._credentials.login, client._credentials.password
                        ),
                    )
                assert service.snapshot().requests_dispatched == before

    asyncio.run(scenario())
