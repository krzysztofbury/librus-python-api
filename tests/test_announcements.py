"""Announcement data integrity and login-owned service/wire behavior."""

import asyncio
import re
from datetime import date

import pytest

from librus_python_api import RequestBudget
from librus_python_api.announcements import parse_announcements
from librus_python_api.exceptions import (
    AccessDeniedError,
    InvalidInputError,
    LimitError,
    MaintenanceError,
    ParseError,
    SessionExpiredError,
    ThrottledError,
    UnsupportedCapabilityError,
)
from tests.announcements_support import (
    AnnouncementsFixture,
    announcement_table,
    empty_page,
    page,
)
from tests.http_support import serve


def test_full_content_line_boundaries_inline_text_and_typed_date() -> None:
    content = (
        "<p>Fixture <span>Bio</span><em>logy</em>&nbsp;note.</p>"
        "<ul><li>First</li><li>Second<br>line</li></ul><p>" + "x" * 2048 + "</p>"
    )
    items = parse_announcements(
        page(announcement_table(content=content)).encode(), "fixture"
    )
    assert len(items) == 1
    item = items[0]
    assert item.title == "Fixture notice"
    assert item.author == "Fixture Editor"
    assert item.published_on == date(2026, 10, 1)
    assert item.date_text == "2026-10-01"
    assert item.content == "Fixture Biology note.\nFirst\nSecond\nline\n" + "x" * 2048
    assert re.fullmatch(r"content-sha256:[0-9a-f]{64}", item.reference)
    assert "Fixture" not in repr(item) and "sha256" not in repr(item)


def test_content_references_survive_reordering_but_change_with_scope_or_fields() -> (
    None
):
    first, second = announcement_table(), announcement_table(title="Fixture second")
    original = parse_announcements(page(first, second).encode(), "fixture")
    reordered = parse_announcements(page(second, first).encode(), "fixture")
    assert original == tuple(reversed(reordered))
    repeated = parse_announcements(page(first, first).encode(), "fixture")
    assert len(repeated) == 2 and repeated[0].reference == repeated[1].reference
    for kwargs in (
        {"title": "Fixture edited"},
        {"author": "Fixture other"},
        {"day": "2026-10-02"},
        {"content": "Fixture changed text"},
    ):
        assert (
            parse_announcements(page(announcement_table(**kwargs)).encode(), "fixture")[
                0
            ].reference
            != original[0].reference
        )
    assert (
        parse_announcements(page(first).encode(), "other-login")[0].reference
        != original[0].reference
    )


def test_semantic_field_order_and_source_whitespace_do_not_change_references() -> None:
    table = announcement_table()
    start = table.index('<tr class="line0">')
    end = table.index('<tr><td colspan="2">', start)
    rows = re.findall(r"<tr.*?</tr>", table[start:end])
    reordered = table[:start] + "".join(reversed(rows)) + table[end:]
    normalized = table.replace("Fixture Editor", "  Fixture\n Editor  ")
    expected = parse_announcements(page(table).encode(), "fixture")
    assert parse_announcements(page(reordered).encode(), "fixture") == expected
    assert parse_announcements(page(normalized).encode(), "fixture") == expected
    aliases = table.replace("Dodał:", "Autor:").replace("Data publikacji:", "Data:")
    assert parse_announcements(page(aliases).encode(), "fixture") == expected


def test_empty_collection_and_empty_content_are_distinct_from_missing_markup() -> None:
    assert parse_announcements(empty_page().encode(), "fixture") == ()
    assert (
        parse_announcements(page(announcement_table(content="")).encode(), "fixture")[
            0
        ].content
        == ""
    )
    for body in (
        page(),
        page("<p>Brak ogłoszeń.</p>"),
        empty_page().replace("Brak ogłoszeń.", "Fixture unrelated warning"),
        empty_page().replace("border-red", "unknown"),
    ):
        with pytest.raises(ParseError):
            parse_announcements(body.encode(), "fixture")
    contradictory = empty_page().replace("</body>", announcement_table() + "</body>")
    with pytest.raises(ParseError):
        parse_announcements(contradictory.encode(), "fixture")


@pytest.mark.parametrize(
    "before,after,expected",
    [
        ("Fixture Editor", "", ParseError),
        ("Fixture notice", "", ParseError),
        ("2026-10-01", "2026-02-30", ParseError),
        ("2026-10-01", "01.10.2026", UnsupportedCapabilityError),
        ("Dodał:", "Fixture Unknown:", UnsupportedCapabilityError),
        ("Data publikacji:", "Dodał:", ParseError),
        ("<th>Treść:</th>", '<th colspan="2">Treść:</th>', ParseError),
        ("<td>Fixture Editor</td>", '<td rowspan="2">Fixture Editor</td>', ParseError),
        ("printable big", "big", UnsupportedCapabilityError),
        (
            '<tr><td colspan="2"></td></tr>',
            '<tr><td colspan="2">Fixture unparsed</td></tr>',
            UnsupportedCapabilityError,
        ),
        ("Fixture notice", "x" * 1025, LimitError),
    ],
)
def test_malformed_or_unsupported_items_fail_whole_collection(
    before: str,
    after: str,
    expected: type[Exception],
) -> None:
    body = page(announcement_table(), announcement_table().replace(before, after))
    with pytest.raises(expected):
        parse_announcements(body.encode(), "fixture")


@pytest.mark.parametrize(
    "content",
    [
        "<table><tr><td>Fixture nested</td></tr></table>",
        "<script>Fixture unsupported()</script>",
        '<iframe src="https://example.invalid/"></iframe>',
        "<form>Fixture form</form>",
    ],
)
def test_active_or_nested_content_is_not_silently_dropped(content: str) -> None:
    with pytest.raises(UnsupportedCapabilityError):
        parse_announcements(
            page(announcement_table(content=content)).encode(), "fixture"
        )


@pytest.mark.parametrize(
    "bound,value,body",
    [
        (
            "ANNOUNCEMENT_MAX_ITEMS",
            1,
            page(announcement_table(), announcement_table(title="Second")),
        ),
        ("ANNOUNCEMENT_MAX_CONTENT_LENGTH", 10, page(announcement_table())),
        (
            "ANNOUNCEMENT_MAX_TOTAL_TEXT_LENGTH",
            130,
            page(announcement_table(), announcement_table(title="Second")),
        ),
    ],
)
def test_limits_reject_instead_of_truncating(
    bound: str,
    value: int,
    body: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("librus_python_api.announcements." + bound, value)
    with pytest.raises(LimitError):
        parse_announcements(body.encode(), "fixture")


def test_four_login_isolation_coalescing_cache_and_freshness() -> None:
    async def scenario() -> None:
        fixture = AnnouncementsFixture()
        aliases = ("student-a", "parent-a", "student-b", "parent-b")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(aliases) as service:
                results = await asyncio.gather(
                    *(
                        service.account(a).announcements()
                        for a in aliases
                        for _ in range(2)
                    )
                )
                assert len(fixture.announcement_gets) == 4
                refs = set()
                for index, alias in enumerate(aliases):
                    result = results[index * 2]
                    assert result is results[index * 2 + 1]
                    assert result.items[0].author == "Fixture " + alias
                    assert result.observation.source == "announcements"
                    assert result.identity.student.id == "student-shared"
                    refs.add(result.items[0].reference)
                    assert (
                        await service.account(alias).announcements(max_age_seconds=60)
                        is result
                    )
                assert len(refs) == 4
                assert len(fixture.announcement_gets) == 4
                fixture.announcement_body = empty_page()
                assert (await service.account(aliases[0]).announcements()).items == ()
                assert len(fixture.announcement_gets) == 5
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_proven_expiry_recovers_once_and_invalidates_prior_cache() -> None:
    async def scenario() -> None:
        fixture = AnnouncementsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.announcements()
                fixture.announcement_expiry = 1
                fixture.announcement_body = page(
                    announcement_table(title="Fixture refreshed")
                )
                refreshed = await client.announcements()
                assert refreshed.items[0].title == "Fixture refreshed"
                assert (
                    refreshed.observation.session_generation
                    > first.observation.session_generation
                )
                assert fixture.logins == {"student": 2}
                assert len(fixture.announcement_gets) == 3
                assert await client.announcements(max_age_seconds=60) is refreshed

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,expected",
    [
        (403, AccessDeniedError),
        (429, ThrottledError),
        (503, MaintenanceError),
        (401, SessionExpiredError),
    ],
)
def test_failures_do_not_loop_or_cache_partial_results(
    status: int, expected: type[Exception]
) -> None:
    async def scenario() -> None:
        fixture = AnnouncementsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                await service.account("student").identity()
                fixture.announcement_status = status
                with pytest.raises(expected):
                    await service.account("student").announcements()
                assert len(fixture.announcement_gets) == (2 if status == 401 else 1)
                assert fixture.logins == {"student": 2 if status == 401 else 1}

    asyncio.run(scenario())


def test_original_budget_and_form_guards_own_all_announcement_dispatches() -> None:
    from librus_python_api.models import LoginSubmission

    async def scenario() -> None:
        fixture = AnnouncementsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                before = service.snapshot().requests_dispatched
                with pytest.raises(InvalidInputError):
                    await client._transport.request(
                        "announcements",
                        RequestBudget(),
                        form=LoginSubmission(
                            client._credentials.login, client._credentials.password
                        ),
                    )
                assert service.snapshot().requests_dispatched == before
            async with fixture.service() as service:
                budget = RequestBudget(max_requests=5, timeout_seconds=3)
                with pytest.raises(LimitError):
                    await service.account("student").announcements(budget=budget)
                assert budget.requests_dispatched == 5
                assert not fixture.announcement_gets

    asyncio.run(scenario())


def test_malformed_read_is_not_cached_or_returned_as_empty() -> None:
    async def scenario() -> None:
        fixture = AnnouncementsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                fixture.announcement_body = page()
                with pytest.raises(ParseError):
                    await client.announcements()
                fixture.announcement_body = page(announcement_table())
                result = await client.announcements(max_age_seconds=60)
                assert result.items[0].title == "Fixture notice"
                assert len(fixture.announcement_gets) == 2
                assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_cancellation_releases_joined_read_and_does_not_poison_next_call() -> None:
    async def scenario() -> None:
        fixture = AnnouncementsFixture()
        fixture.wait_announcements = asyncio.Event()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                task = asyncio.create_task(service.account("student").announcements())
                try:
                    await asyncio.wait_for(
                        fixture.announcements_started.wait(), timeout=2
                    )
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert service.snapshot().active == service.snapshot().queued == 0
                finally:
                    fixture.wait_announcements.set()
                assert (await service.account("student").announcements()).items

    asyncio.run(scenario())
