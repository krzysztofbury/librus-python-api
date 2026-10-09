"""Owning mailbox semantics and bounded deduplicated continuation contracts."""

import asyncio
from dataclasses import replace
from datetime import datetime

import pytest

from librus_python_api import (
    MessageFolder,
    MessagesCursor,
    MessageSummary,
    RequestBudget,
)
from librus_python_api.exceptions import (
    ErrorKind,
    InvalidInputError,
    LibrusError,
    LimitError,
    ParseError,
    SessionExpiredError,
    UnsupportedCapabilityError,
)
from librus_python_api.messages import parse_messages
from tests.http_support import serve
from tests.messages_support import message_row, messages_html
from tests.reads_support import ReadsFixture


def parse(
    body: str, folder: MessageFolder = MessageFolder.RECEIVED, page: int = 0
) -> tuple[tuple[MessageSummary, ...], int, str]:
    return parse_messages(body.encode(), folder, page, "fixture-login")


def test_received_reference_visible_fields_wall_time_and_flags() -> None:
    items, count, fingerprint = parse(messages_html(rows=message_row(attachment=True)))
    item = items[0]
    assert count == 1 and len(fingerprint) == 64
    assert (
        item.reference.account == "fixture-login" and item.reference.identifier == "101"
    )
    assert item.reference.folder is MessageFolder.RECEIVED
    assert item.correspondent == "Fixture Sender" and item.subject == "Fixture subject"
    assert item.timestamp.local == datetime(2026, 10, 2, 8, 15, 30)
    assert (
        item.timestamp.timezone == "Europe/Warsaw"
        and item.timestamp.local.tzinfo is None
    )
    assert item.timestamp.raw == "2026-10-02 08:15:30"
    assert item.unread is True and item.has_attachment is True
    assert item.recipient_read_status is None
    assert "Fixture" not in repr(item) and "101" not in repr(item.reference)
    assert "2026" not in repr(item.timestamp)


@pytest.mark.parametrize("folder", list(MessageFolder))
@pytest.mark.parametrize("empty", [True, False])
def test_legacy_information_banner_and_blank_footer_are_not_data_or_errors(
    folder: MessageFolder,
    empty: bool,
) -> None:
    items, count, _ = parse(
        messages_html(
            folder,
            rows="" if empty else message_row(folder=folder),
            footer=True,
            legacy_notice=True,
            pagination=False,
        ),
        folder,
    )
    assert len(items) == (0 if empty else 1) and count == 1


def test_sent_correspondent_and_recipient_status_are_not_fabricated_unread() -> None:
    item = parse(
        messages_html(MessageFolder.SENT, rows=message_row(folder=MessageFolder.SENT)),
        MessageFolder.SENT,
    )[0][0]
    assert item.unread is None and item.recipient_read_status == "NIE"
    assert item.reference.folder is MessageFolder.SENT


@pytest.mark.parametrize("folder", list(MessageFolder))
def test_explicit_empty_folder_is_one_empty_page(folder: MessageFolder) -> None:
    items, count, _ = parse(messages_html(folder, rows="", pagination=False), folder)
    assert items == () and count == 1


def test_multiline_text_class_order_and_numeric_bold_preserve_rendered_semantics() -> (
    None
):
    body = messages_html(
        rows=message_row(
            subject="Fixture<br>subject", correspondent="Fixture&nbsp;Sender"
        )
    )
    body = body.replace("decorated stretch", "stretch decorated extra").replace(
        "font-weight: bold;", "font-weight:700 !important;"
    )
    item = parse(body)[0][0]
    assert (
        item.subject == "Fixture\nsubject"
        and item.correspondent == "Fixture Sender"
        and item.unread is True
    )
    assert (
        parse(body.replace("font-weight:700 !important;", "font-weight: normal;"))[0][
            0
        ].unread
        is False
    )
    # A DST fold is wall time on the page, never an invented UTC instant.
    fold = parse(body.replace("2026-10-02 08:15:30", "2026-10-25 02:30:00"))[0][
        0
    ].timestamp
    assert fold.local == datetime(2026, 10, 25, 2, 30) and fold.local.tzinfo is None


@pytest.mark.parametrize(
    "before,after",
    [
        ("Nadawca", "Adresat"),
        ("Temat", "Fixture unknown header"),
        ("2026-10-02 08:15:30", "2026-02-30 08:15:30"),
        ("2026-10-02 08:15:30", "02.10.2026 08:15"),
        ("/wiadomosci/1/5/101/f0", "https://example.invalid/101"),
        ("/wiadomosci/1/5/101/f0", "/wiadomosci/1/6/101/f0"),
        ("/wiadomosci/1/5/101/f0", "/wiadomosci/1/5/101/f0?extra=1"),
        ("Fixture subject", "<script>Fixture unsafe()</script>"),
        ('class="medium center"', 'class="medium center" rowspan="2"'),
        ("font-weight: bold;", "font-weight:bolder;"),
        ("Strona 1 z&nbsp;1", "Strona 2 z&nbsp;2"),
        ("Strona 1 z&nbsp;1", "Strona 1 z&nbsp;0"),
    ],
)
def test_wrong_rows_routes_dates_and_metadata_fail_without_partial_output(
    before: str, after: str
) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse(messages_html().replace(before, after))


def test_link_disagreement_duplicates_and_missing_empty_marker_fail() -> None:
    with pytest.raises(ParseError):
        parse(
            messages_html(rows="").replace(
                "<body>",
                '<body><div class="warning-content">Fixture unknown notice</div>',
            )
        )
    with pytest.raises(ParseError):
        parse(messages_html(rows=message_row() + message_row()))
    with pytest.raises(ParseError):
        parse(messages_html().replace("/101/f0", "/102/f0", 1))
    with pytest.raises(ParseError):
        parse("<html></html>")
    with pytest.raises(ParseError):
        parse(
            messages_html(rows="").replace("Brak wiadomości", "Fixture unknown empty")
        )
    with pytest.raises(ParseError):
        parse(
            messages_html(
                rows=message_row() + '<tr><td colspan="6">Brak wiadomości</td></tr>'
            )
        )


@pytest.mark.parametrize(
    "bound,value",
    [
        ("MESSAGE_MAX_PAGE_ITEMS", 0),
        ("MESSAGE_MAX_FIELD_LENGTH", 2),
        ("MESSAGE_MAX_TOTAL_TEXT_LENGTH", 2),
        ("MESSAGE_MAX_PAGE_COUNT", 0),
    ],
)
def test_parser_limits_reject_instead_of_truncating(
    bound: str, value: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.messages." + bound, value)
    with pytest.raises(LimitError):
        parse(messages_html())


def test_page_and_row_actual_maximum_boundaries() -> None:
    body = messages_html(
        page=999, count=1000, rows="".join(message_row(str(100 + i)) for i in range(50))
    )
    assert len(parse(body, page=999)[0]) == 50
    with pytest.raises(LimitError):
        parse(messages_html(rows="".join(message_row(str(100 + i)) for i in range(51))))
    with pytest.raises(LimitError):
        parse(messages_html(count=1001))
    with pytest.raises(ParseError):
        parse(messages_html(pagination=False), page=1)


@pytest.mark.parametrize("folder", list(MessageFolder))
def test_pagerless_full_mailbox_is_unsupported_not_silently_complete(
    folder: MessageFolder,
) -> None:
    body = messages_html(
        folder,
        pagination=False,
        rows="".join(message_row(str(100 + i), folder=folder) for i in range(50)),
    )
    with pytest.raises(UnsupportedCapabilityError):
        parse(body, folder)
    partial = messages_html(
        folder,
        pagination=False,
        rows="".join(message_row(str(100 + i), folder=folder) for i in range(49)),
    )
    assert len(parse(partial, folder)[0]) == 49


def test_midpage_resume_uses_one_budget_and_never_gets_separate_page_count() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                budget = RequestBudget(max_requests=8)
                first = await client.messages(max_pages=1, limit=1, budget=budget)
                assert first.pages_fetched == 1 and len(first.items) == 1
                assert first.truncation_reason == "item_limit"
                assert first.next_cursor is not None and first.next_cursor.offset == 1
                second = await client.messages(
                    cursor=first.next_cursor, max_pages=1, budget=budget
                )
                assert len(second.items) == 1 and second.next_cursor is not None
                assert second.next_cursor.page == 1 and second.next_cursor.offset == 0
                assert second.truncation_reason == "page_limit"
                third = await client.messages(
                    cursor=second.next_cursor, max_pages=1, budget=budget
                )
                assert third.items[0].reference.identifier == "103"
                assert (
                    budget.requests_dispatched == 8
                    and fixture.count("messages_received") == 3
                )

    asyncio.run(scenario())


def test_batch_overlap_deduplicates_across_resume_without_losing_new_rows() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        for number, ids in enumerate((("101", "102"), ("102", "103"), ("103", "104"))):
            fixture.page_bodies[("messages_received", number)] = (
                messages_html(
                    page=number, count=3, rows="".join(message_row(i) for i in ids)
                ).encode(),
                "text/html",
            )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.messages(max_pages=1, limit=2)
                assert first.next_cursor is not None
                rest = await client.messages(cursor=first.next_cursor)
                assert [r.reference.identifier for r in first.items + rest.items] == [
                    "101",
                    "102",
                    "103",
                    "104",
                ]
                assert (
                    rest.duplicates_skipped == 2
                    and rest.next_cursor is None
                    and rest.pages_fetched == 2
                )

    asyncio.run(scenario())


def test_mid_page_resume_survives_read_state_change() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.messages(max_pages=1, limit=1)
                assert first.next_cursor is not None
                assert first.next_cursor.offset == 1
                # Row 101 was opened (marked read) before the caller resumed.
                body = messages_html(
                    count=3, rows=message_row(unread=False) + message_row("102")
                )
                fixture.page_bodies[("messages_received", 0)] = (
                    body.encode(),
                    "text/html",
                )
                rest = await client.messages(cursor=first.next_cursor, limit=1)
                assert [r.reference.identifier for r in rest.items] == ["102"]
                assert rest.items[0].unread is True

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["row", "count", "clamped", "no_progress", "expiry"])
def test_resume_integrity_and_later_page_failures_never_return_partial_success(
    change: str,
) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.messages(
                    max_pages=1, limit=1 if change == "row" else 2
                )
                assert first.next_cursor is not None
                number = first.next_cursor.page
                body = messages_html(
                    page=number, count=3, rows=message_row("103") + message_row("104")
                )
                if change == "row":
                    body = messages_html(
                        count=3,
                        rows=message_row(subject="Fixture changed")
                        + message_row("102"),
                    )
                elif change == "count":
                    body = body.replace("z&nbsp;3", "z&nbsp;4")
                elif change == "clamped":
                    body = messages_html(count=3)
                elif change == "no_progress":
                    body = messages_html(
                        page=number,
                        count=3,
                        rows=message_row("101", subject="Fixture changed")
                        + message_row("102"),
                    )
                else:
                    fixture.failures["messages_received"] = [401]
                fixture.page_bodies[("messages_received", number)] = (
                    body.encode(),
                    "text/html",
                )
                with pytest.raises(
                    SessionExpiredError if change == "expiry" else LibrusError
                ) as error:
                    await client.messages(cursor=first.next_cursor)
                if change not in ("expiry", "clamped"):
                    assert error.value.kind.value == "stale_cursor"
                elif change == "clamped":
                    assert error.value.kind is ErrorKind.PARSE
                assert fixture.logins == {"student": 1}
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_foreign_folder_account_and_invalid_history_fail_before_any_login() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        cursor = MessagesCursor(
            "student", MessageFolder.RECEIVED, 0, 1, 3, "a" * 64, ("101",)
        )
        bad = [
            replace(cursor, account="parent"),
            replace(cursor, folder=MessageFolder.SENT),
            replace(cursor, page=True),
            replace(cursor, offset=50),
            replace(cursor, page_count=0),
            replace(cursor, fingerprint="private"),
            replace(cursor, seen_ids=("../1",)),
            replace(cursor, seen_ids=("101", "101")),
            replace(cursor, seen_ids=()),
            replace(cursor, seen_ids=tuple(str(i) for i in range(2001))),
        ]
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                for value in bad:
                    with pytest.raises(InvalidInputError):
                        await service.account("student").messages(cursor=value)
                assert fixture.calls == []

    asyncio.run(scenario())


def test_page_and_batch_caches_are_distinct_and_empty_batch_is_explicit() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        fixture.bodies["messages_sent"] = (
            messages_html(MessageFolder.SENT, rows="", pagination=False).encode(),
            "text/html",
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                page = await client.messages_page(
                    MessageFolder.SENT, max_age_seconds=60
                )
                batch = await client.messages(MessageFolder.SENT, max_age_seconds=60)
                assert (
                    batch.items == page.items == ()
                    and batch.next_cursor is None
                    and batch.pages_fetched == 1
                )
                assert fixture.count("messages_sent") == 2
                assert (
                    await client.messages_page(MessageFolder.SENT, max_age_seconds=60)
                    is page
                )
                assert (
                    await client.messages(MessageFolder.SENT, max_age_seconds=60)
                    is batch
                )

    asyncio.run(scenario())


def test_later_page_budget_exhaustion_discards_partial_results_and_releases_work() -> (
    None
):
    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                budget = RequestBudget(max_requests=1)
                with pytest.raises(LimitError):
                    await client.messages(budget=budget, max_age_seconds=60)
                assert (
                    fixture.count("messages_received")
                    == budget.requests_dispatched
                    == 1
                )
                assert service.snapshot().active == service.snapshot().queued == 0
                result = await client.messages(max_age_seconds=60)
                assert len(result.items) == 6 and result.next_cursor is None
                assert fixture.count("messages_received") == 4

    asyncio.run(scenario())


def test_four_independent_full_mailboxes_share_budget_without_cross_account_dedup() -> (
    None
):
    async def scenario() -> None:
        fixture = ReadsFixture()
        for number in range(5):
            body = messages_html(
                page=number,
                count=5,
                footer=True,
                rows="".join(
                    message_row(str(100 + number * 50 + i), attachment=i % 2 == 0)
                    for i in range(50)
                ),
            )
            fixture.page_bodies[("messages_received", number)] = (
                body.encode(),
                "text/html",
            )
        accounts = ("student", "parent", "other-student", "other-parent")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(accounts) as service:
                budget = RequestBudget(max_requests=40)
                results = await asyncio.gather(
                    *(
                        service.account(a).messages(
                            max_pages=8, limit=256, budget=budget, max_age_seconds=60
                        )
                        for a in accounts
                    )
                )
                assert budget.requests_dispatched == 40
                assert fixture.count("messages_received") == 20
                for account, result in zip(accounts, results, strict=True):
                    assert len(result.items) == 250 and result.pages_fetched == 5
                    assert result.duplicates_skipped == 0 and result.next_cursor is None
                    assert result.truncation_reason is None
                    assert result.observation.account == account
                    assert all(r.reference.account == account for r in result.items)
                    assert (
                        await service.account(account).messages(
                            max_pages=8,
                            limit=256,
                            budget=RequestBudget(),
                            max_age_seconds=60,
                        )
                        is result
                    )
                assert fixture.count("messages_received") == 20

    asyncio.run(scenario())
