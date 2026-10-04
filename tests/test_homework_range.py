"""Public multi-selection homework contract over real isolated loopback sessions."""

import asyncio
from datetime import date
from typing import Any, cast

import pytest
from aiohttp import web

from librus_python_api import HomeworkRangeRequest, RequestBudget
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    ParseError,
    SessionExpiredError,
)
from tests.http_support import serve
from tests.school_reads_support import SchoolReadsFixture, homework_html, homework_row


class RangeFixture(SchoolReadsFixture):
    def __init__(self) -> None:
        super().__init__()
        self.conflict = False
        self.fail_second = False

    async def homework(self, request: web.Request) -> web.Response:
        login, form = await self.selected(request, "homework")
        assert set(form) == {"dataOd", "dataDo", "przedmiot", "status"}
        assert form["przedmiot"] == form["status"] == "-1"
        second = form["dataOd"] == "2026-03-01"
        if second and self.fail_second:
            return web.Response(status=401)
        shared = homework_row(
            "100", topic=login + (" changed" if second and self.conflict else "")
        )
        distinct = homework_row("102" if second else "101", topic=login)
        return web.Response(
            text=homework_html(rows=shared + distinct), content_type="text/html"
        )


SELECTION = HomeworkRangeRequest(date(2026, 1, 31), date(2026, 3, 5))


def test_range_windows_share_budget_and_keep_account_bound_references() -> None:
    async def scenario() -> None:
        fixture = RangeFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("parent", "student")) as service:
                budgets = [RequestBudget(max_requests=7) for _ in range(2)]
                results = await asyncio.gather(
                    *(
                        service.account(alias).homework_range(SELECTION, budget=budget)
                        for alias, budget in zip(
                            ("parent", "student"), budgets, strict=True
                        )
                    )
                )
                for alias, result in zip(("parent", "student"), results, strict=True):
                    assert result.identity.owner.id == alias
                    assert (
                        result.start == SELECTION.start and result.end == SELECTION.end
                    )
                    assert [
                        i.reference.identifier for i in result.items if i.reference
                    ] == ["100", "101", "102"]
                    assert {
                        i.reference.account for i in result.items if i.reference
                    } == {alias}
                    assert {i.topic for i in result.items} == {alias}
                    assert [
                        (f["dataOd"], f["dataDo"])
                        for _, who, f in fixture.forms
                        if who == alias
                    ] == [("2026-01-31", "2026-02-28"), ("2026-03-01", "2026-03-05")]
                    cached = await service.account(alias).homework_range(
                        SELECTION, max_age_seconds=60
                    )
                    assert cached == result
                assert len(fixture.forms) == 4
                assert [b.requests_dispatched for b in budgets] == [7, 7]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode,error",
    [
        ("conflict", ParseError),
        ("expiry", SessionExpiredError),
        ("budget", LimitError),
        ("items", LimitError),
    ],
)
def test_partial_range_is_neither_returned_nor_cached(
    mode: str, error: type[Exception]
) -> None:
    async def scenario() -> None:
        fixture = RangeFixture()
        fixture.conflict = mode == "conflict"
        fixture.fail_second = mode == "expiry"
        selection = HomeworkRangeRequest(
            SELECTION.start, SELECTION.end, max_items=2 if mode == "items" else 4096
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student",)) as service:
                client = service.account("student")
                with pytest.raises(error):
                    await client.homework_range(
                        selection,
                        budget=RequestBudget(max_requests=6 if mode == "budget" else 7),
                    )
                assert fixture.logins == {"student": 1}
                assert len(fixture.forms) == (1 if mode == "budget" else 2)
                fixture.conflict = fixture.fail_second = False
                if mode == "expiry":
                    # Existing expiry cooldown must prevent a replay and must
                    # not be bypassed by a partially cached range.
                    with pytest.raises(SessionExpiredError):
                        await client.homework_range(selection, max_age_seconds=60)
                    assert len(fixture.forms) == 2
                    return
                if mode == "items":
                    # Same key must still fail: a partial cache would return success.
                    with pytest.raises(LimitError):
                        await client.homework_range(selection, max_age_seconds=60)
                else:
                    result = await client.homework_range(selection, max_age_seconds=60)
                    assert len(result.items) == 3
                assert len(fixture.forms) == (3 if mode == "budget" else 4)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "selection,error",
    [
        (None, InvalidInputError),
        (
            HomeworkRangeRequest(cast(date, "2026-01-01"), date(2026, 2, 1)),
            InvalidInputError,
        ),
        (HomeworkRangeRequest(date(2026, 1, 1), date(2027, 1, 7)), InvalidInputError),
        (HomeworkRangeRequest(date(2026, 2, 1), date(2026, 1, 1)), InvalidInputError),
        (
            HomeworkRangeRequest(SELECTION.start, SELECTION.end, max_windows=True),
            InvalidInputError,
        ),
        (
            HomeworkRangeRequest(SELECTION.start, SELECTION.end, max_windows=1),
            LimitError,
        ),
        (
            HomeworkRangeRequest(SELECTION.start, SELECTION.end, max_items=0),
            InvalidInputError,
        ),
    ],
)
def test_invalid_selection_dispatches_nothing(
    selection: Any, error: type[Exception]
) -> None:
    async def scenario() -> None:
        fixture = RangeFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student",)) as service:
                with pytest.raises(error):
                    await service.account("student").homework_range(selection)
                assert fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "selection,expected",
    [
        (
            HomeworkRangeRequest(date(2028, 1, 31), date(2028, 3, 1)),
            [("2028-01-31", "2028-02-29"), ("2028-03-01", "2028-03-01")],
        ),
        (
            HomeworkRangeRequest(date(2026, 12, 31), date(2027, 2, 2)),
            [("2026-12-31", "2027-01-31"), ("2027-02-01", "2027-02-02")],
        ),
    ],
)
def test_range_calendar_boundaries_on_wire(
    selection: HomeworkRangeRequest, expected: list[tuple[str, str]]
) -> None:
    async def scenario() -> None:
        fixture = RangeFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student",)) as service:
                result = await service.account("student").homework_range(selection)
                assert len(result.items) == 2
                assert [
                    (f["dataOd"], f["dataDo"]) for _, _, f in fixture.forms
                ] == expected

    asyncio.run(scenario())
