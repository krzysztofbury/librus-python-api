"""e-Justifications semantics and the denied-page outcome.

Shared read guarantees (coalescing, budgets, expiry by status, notices) are
owned by tests/test_account_reads.py; this module owns what is specific here.
"""

import asyncio
from datetime import date, datetime
from typing import Any

import pytest
from aiohttp import web

from librus_python_api import JustificationStatus
from librus_python_api.exceptions import (
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.justifications import parse_justifications
from tests.http_support import LOGGED_OUT_PAGE, SchoolFixture, serve
from tests.justifications_support import (
    EMPTY_ROW,
    HEADERS,
    entry,
    justifications_html,
)

LIST = "/eusprawiedliwienia"
PROBE = "/informacja"


def parse(html: str) -> Any:
    result = parse_justifications(html.encode())
    assert result is not None
    return result


def test_default_window_entries_are_typed() -> None:
    start, end, (ranged, one_day) = parse(justifications_html())
    assert (start, end) == (date(2026, 10, 13), date(2026, 11, 13))
    assert (ranged.start, ranged.end, ranged.lessons) == (
        date(2026, 10, 1),
        date(2026, 10, 3),
        (),
    )
    assert ranged.absence_count == 4
    assert ranged.status is JustificationStatus.JUSTIFIED
    assert ranged.decided_by == "A. Fixture"
    assert ranged.sent_at == datetime(2026, 10, 4, 8, 15, 30)
    assert ranged.teachers == (
        "Fixture Teacher One",
        "Fixture Teacher Two",
        "Fixture Teacher Three",
    )
    assert ranged.content == "Fixture reason for the absence."
    assert ranged.has_attachment is False
    assert (one_day.start, one_day.end, one_day.lessons) == (
        date(2026, 10, 7),
        date(2026, 10, 7),
        (2, 3),
    )
    assert one_day.status is JustificationStatus.SENT and one_day.decided_by is None
    # Text, names, dates and counts stay out of repr; only the outcome shows.
    assert repr(ranged) == (
        "Justification(status=<JustificationStatus.JUSTIFIED: 'justified'>, "
        "has_attachment=False)"
    )


@pytest.mark.parametrize(
    "word,status",
    [
        ("wysłane", JustificationStatus.SENT),
        ("usprawiedliwione", JustificationStatus.JUSTIFIED),
        ("odrzucone (B. Fixture)", JustificationStatus.REJECTED),
    ],
)
def test_every_status_option_maps_to_a_member(
    word: str, status: JustificationStatus
) -> None:
    (item,) = parse(justifications_html(entry(status=word)))[2]
    assert item.status is status


@pytest.mark.parametrize(
    "period,lessons",
    [("2026-10-07, lekcja: 4", (4,)), ("2026-10-07, lekcje: 0, 1, 2", (0, 1, 2))],
)
def test_one_day_lesson_lists(period: str, lessons: tuple[int, ...]) -> None:
    (item,) = parse(justifications_html(entry(period=period)))[2]
    assert item.lessons == lessons and item.start == item.end


def test_explicit_empty_row_and_no_rows_are_empty_results() -> None:
    assert parse(justifications_html(EMPTY_ROW))[2] == ()
    assert parse(justifications_html(""))[2] == ()


def test_filled_attachment_cell_is_only_flagged() -> None:
    (item,) = parse(justifications_html(entry(attachment='<a href="#">x</a>')))[2]
    assert item.has_attachment is True


@pytest.mark.parametrize(
    "html",
    [
        justifications_html(entry(status="zaakceptowane")),
        justifications_html(entry(status="usprawiedliwione ()")),
        justifications_html(headers=(*HEADERS[:-1], "Stan")),
        justifications_html(headers=HEADERS[:-1]),
        justifications_html(entry().replace("<td></td>", "", 1)),
        justifications_html(entry(period="2026-10-07")),
        justifications_html(entry(period="od 2026-10-03 do 2026-10-01")),
        justifications_html(entry(period="od 2026-02-30 do 2026-03-01")),
        justifications_html(entry(period="2026-10-07, lekcje: 2, 2")),
        justifications_html(entry(count="cztery")),
        justifications_html(entry(sent="2026-10-04")),
        justifications_html(start="2026-11-14"),
        justifications_html(start=""),
        '<html><body><div id="graphic-menu"></div></body></html>',
    ],
)
def test_unknown_layouts_fail_as_parse(html: str) -> None:
    with pytest.raises(ParseError):
        parse_justifications(html.encode())


def test_a_list_narrowed_to_one_status_is_refused() -> None:
    with pytest.raises(UnsupportedCapabilityError):
        parse_justifications(justifications_html(status_option="2").encode())


def test_entries_and_text_are_bounded() -> None:
    with pytest.raises(LimitError):
        parse_justifications(
            justifications_html(*(entry() for _ in range(513))).encode()
        )
    with pytest.raises(LimitError):
        parse_justifications(justifications_html(entry(content="x" * 8193)).encode())


def test_the_denied_page_is_returned_as_none() -> None:
    assert parse_justifications(LOGGED_OUT_PAGE.encode()) is None


class JustificationsFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        # Logins answered with the "Brak dostępu" page on every list request.
        self.denied: set[str] = set()

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get(LIST, self.justifications)
        return app

    async def justifications(self, request: web.Request) -> web.Response:
        login = self.record(request)
        if login in self.denied or self.logged_out_page(login):
            return web.Response(text=LOGGED_OUT_PAGE, content_type="text/html")
        return web.Response(text=justifications_html(), content_type="text/html")

    def count(self, path: str) -> int:
        return sum(called == path for called, _ in self.calls)


def run(scenario: Any) -> None:
    async def main() -> None:
        fixture = JustificationsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                await asyncio.wait_for(scenario(fixture, service), timeout=10)

    asyncio.run(main())


@pytest.mark.parametrize("signed_in_first", [True, False])
def test_a_denied_login_keeps_its_session_and_is_not_asked_again(
    signed_in_first: bool,
) -> None:
    async def scenario(fixture: JustificationsFixture, service: Any) -> None:
        client = service.account("student")
        fixture.denied.add("student")
        if signed_in_first:
            await client.identity()
        with pytest.raises(UnsupportedCapabilityError):
            await client.justifications()
        assert (fixture.count(LIST), fixture.count(PROBE)) == (1, 1)
        # Later calls in the same session make no request at all.
        before = len(fixture.calls)
        with pytest.raises(UnsupportedCapabilityError):
            await client.justifications()
        assert len(fixture.calls) == before
        # The session was never cleared: other reads still use it.
        await client.student_information()
        assert fixture.logins == {"student": 1}

    run(scenario)


def test_a_dead_session_signs_in_again_and_reads_the_list() -> None:
    async def scenario(fixture: JustificationsFixture, service: Any) -> None:
        client = service.account("student")
        await client.identity()
        # The list and the probe both get the logged-out page once.
        fixture.logged_out["student"] = 2
        result = await client.justifications()
        assert len(result.items) == 2
        assert fixture.logins == {"student": 2}
        assert (fixture.count(LIST), fixture.count(PROBE)) == (2, 1)

    run(scenario)
