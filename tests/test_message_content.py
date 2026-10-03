"""Owning content semantics, read consent, summary invalidation and inert files."""

import asyncio
from dataclasses import replace
from datetime import datetime

import pytest

from librus_python_api import MessageFolder, MessageReference, RequestBudget
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.message_content import parse_message_content
from tests.http_support import serve
from tests.message_content_support import (
    attachment_html,
    content_html,
    sent_content_html,
)
from tests.reads_support import ReadsFixture

REFERENCE = MessageReference(MessageFolder.RECEIVED, "101", "student")


def test_sent_content_with_no_correspondent_preserves_ordered_individual_receipts() -> (
    None
):
    ref = replace(REFERENCE, folder=MessageFolder.SENT)
    data = parse_message_content(
        sent_content_html(
            (
                ("Fixture Office", "2026-10-03 09:00:00"),
                ("Same Fixture Name", "NIE"),
                ("Same Fixture Name", "NIE"),
            )
        ).encode(),
        ref,
    )
    assert data.correspondent is None and data.read_timestamp is None
    assert data.subject == "Fixture sent subject"
    assert data.timestamp.local == datetime(2026, 10, 3, 8)
    assert data.text == "Fixture sent body\nSecond line"
    assert [r.recipient for r in data.recipient_receipts] == [
        "Fixture Office",
        "Same Fixture Name",
        "Same Fixture Name",
    ]
    stamp = data.recipient_receipts[0].read_timestamp
    assert stamp is not None and stamp.local == datetime(2026, 10, 3, 9)
    assert (
        data.recipient_receipts[1].read_timestamp is None
        and data.recipient_receipts[1].raw_status == "NIE"
    )
    assert "Fixture" not in repr(data.recipient_receipts[0])


@pytest.mark.parametrize(
    "before,after",
    [
        ('colspan="3"', 'colspan="2"'),
        ("Fixture Office", ""),
        ("2026-10-03 09:00:00", "2026-02-30 09:00:00"),
        ("2026-10-03 09:00:00", "TAK"),
        ("Fixture Office", "<script>unsafe()</script>"),
        ("<td>Fixture Office</td>", '<td rowspan="2">Fixture Office</td>'),
    ],
)
def test_sent_receipt_unknown_or_ambiguous_rows_fail_whole_content(
    before: str, after: str
) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_message_content(
            sent_content_html().replace(before, after).encode(),
            replace(REFERENCE, folder=MessageFolder.SENT),
        )


def test_duplicate_individual_receipts_or_mixed_global_receipt_are_rejected() -> None:
    body = sent_content_html()
    individual = body[
        body.index('<table class="stretch"><tbody><tr><td colspan="3">') : body.index(
            "</body>"
        )
    ]
    for extra in (
        individual,
        '<table class="stretch"><tr><td>Przeczytano</td>'
        "<td>2026-10-03 09:00:00</td></tr></table>",
    ):
        with pytest.raises(ParseError):
            parse_message_content(
                body.replace("</body>", extra + "</body>").encode(),
                replace(REFERENCE, folder=MessageFolder.SENT),
            )
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_message_content(body.encode(), REFERENCE)


@pytest.mark.parametrize(
    "bound", ["MESSAGE_MAX_RECIPIENT_RECEIPTS", "MESSAGE_MAX_RECEIPT_TEXT_LENGTH"]
)
def test_sent_receipt_limits_are_errors_not_partial_results(
    bound: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.message_content." + bound, 1)
    with pytest.raises(LimitError):
        parse_message_content(
            sent_content_html(
                (("Fixture Office", "NIE"), ("Other fixture", "NIE"))
            ).encode(),
            replace(REFERENCE, folder=MessageFolder.SENT),
        )


def test_separate_read_receipt_table_is_not_ambiguous_message_metadata() -> None:
    data = parse_message_content(content_html(read_receipt=True).encode(), REFERENCE)
    assert data.subject == "Fixture subject"
    assert data.read_timestamp is not None
    assert data.read_timestamp.local == datetime(2026, 10, 2, 9)


def test_page_comments_are_not_download_markers_or_parser_exceptions() -> None:
    body = content_html().replace("<body>", "<body><!-- Fixture layout note -->")
    assert parse_message_content(body.encode(), REFERENCE).attachments == ()


@pytest.mark.parametrize("folder", list(MessageFolder))
def test_content_fields_plain_text_and_account_bound_attachment_metadata(
    folder: MessageFolder,
) -> None:
    ref = replace(REFERENCE, folder=folder)
    body = content_html(folder, attachments=attachment_html() + attachment_html("302"))
    data = parse_message_content(body.encode(), ref)
    assert data.reference == ref
    assert data.correspondent == "Fixture Person" and data.subject == "Fixture subject"
    assert data.timestamp.local == datetime(2026, 10, 2, 8, 15, 30)
    assert data.text == "First line\nSecond line"
    assert [a.reference.identifier for a in data.attachments] == ["301", "302"]
    assert all(a.reference.message == ref for a in data.attachments)
    assert [a.filename for a in data.attachments] == ["Fixture file.txt"] * 2
    assert all("Fixture" not in repr(a) for a in data.attachments)
    assert "Fixture" not in repr(data) and "101" not in repr(data.attachments[0])


def test_empty_body_and_no_files_are_explicit_and_escaped_handler_is_inert() -> None:
    data = parse_message_content(content_html(content="").encode(), REFERENCE)
    assert data.text == "" and data.attachments == ()
    body = content_html(attachments=attachment_html()).replace(
        "/wiadomosci/pobierz_zalacznik/101/301",
        r"\/wiadomosci\/pobierz_zalacznik\/101\/301",
    )
    assert (
        parse_message_content(body.encode(), REFERENCE)
        .attachments[0]
        .reference.identifier
        == "301"
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ("Nadawca:", "Unknown:"),
        ("2026-10-02 08:15:30", "2026-02-30 08:15:30"),
        ("container-message-content", "unknown-body"),
        ("First line", "<script>unsafe()</script>"),
        ('class="left"', 'class="left" rowspan="2"'),
        (
            'alt="download"',
            'alt="download" href="/wiadomosci/pobierz_zalacznik/101/301"',
        ),
        ("Fixture file.txt", ""),
        ("/101/301", "/102/301"),
        ("/101/301", "/101/301?extra=1"),
        ("'/wiadomosci", "'https://example.invalid/wiadomosci"),
    ],
)
def test_wrong_layout_or_attachment_scope_never_returns_partial_content(
    before: str,
    after: str,
) -> None:
    body = content_html(attachments=attachment_html()).replace(before, after)
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_message_content(body.encode(), REFERENCE)


def test_duplicate_file_reference_and_duplicate_body_are_rejected() -> None:
    with pytest.raises(ParseError):
        parse_message_content(
            content_html(attachments=attachment_html() * 2).encode(), REFERENCE
        )
    body = content_html() + '<div class="container-message-content">Extra</div>'
    with pytest.raises(ParseError):
        parse_message_content(body.encode(), REFERENCE)


def test_real_content_and_file_limits_reject_without_truncation() -> None:
    body = content_html(
        content="x" * 65536,
        attachments="".join(attachment_html(str(300 + i)) for i in range(20)),
    )
    data = parse_message_content(body.encode(), REFERENCE)
    assert len(data.text) == 65536 and len(data.attachments) == 20
    for oversized in (
        body.replace("x" * 65536, "x" * 65537),
        content_html(
            attachments="".join(attachment_html(str(300 + i)) for i in range(21))
        ),
    ):
        with pytest.raises(LimitError):
            parse_message_content(oversized.encode(), REFERENCE)


def test_received_opt_in_and_foreign_or_injected_references_fail_before_login() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            client = service.account("student")
            with pytest.raises(InvalidInputError):
                await client.message_content(REFERENCE)
            for ref in (
                replace(REFERENCE, account="parent"),
                replace(REFERENCE, identifier="../101"),
                replace(REFERENCE, identifier=True),  # type: ignore[arg-type]
                replace(REFERENCE, folder="received"),  # type: ignore[arg-type]
                "101",
            ):
                with pytest.raises(InvalidInputError):
                    await client.message_content(ref, allow_mark_read=True)  # type: ignore[arg-type]
            with pytest.raises(InvalidInputError):
                await client.message_content(REFERENCE, allow_mark_read=1)  # type: ignore[arg-type]
            assert fixture.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("folder", list(MessageFolder))
def test_four_independent_maximum_content_reads_share_one_bounded_budget(
    folder: MessageFolder,
) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        body = content_html(
            content="x" * 65536,
            attachments="".join(attachment_html(str(300 + i)) for i in range(20)),
        )
        if folder is MessageFolder.SENT:
            body = (
                sent_content_html(tuple((f"Fixture {i}", "NIE") for i in range(256)))
                .replace("Fixture sent body<br>Second line", "x" * 65536)
                .replace(
                    "</body>",
                    "".join(attachment_html(str(300 + i)) for i in range(20))
                    + "</body>",
                )
            )
        fixture.bodies["message_content_" + folder.value] = (
            body.encode(),
            "text/html",
        )
        accounts = ("student", "parent", "other-student", "other-parent")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(accounts) as service:
                budget = RequestBudget(max_requests=24)
                results = await asyncio.gather(
                    *(
                        service.account(alias).message_content(
                            replace(REFERENCE, account=alias, folder=folder),
                            allow_mark_read=True,
                            budget=budget,
                        )
                        for alias in accounts
                    )
                )
                assert budget.requests_dispatched == 24
                assert fixture.count("message_content_" + folder.value) == 4
                for alias, result in zip(accounts, results, strict=True):
                    assert result.identity.owner.id == alias
                    assert result.content.reference.account == alias
                    assert len(result.content.text) == 65536
                    assert len(result.content.attachments) == 20
                    assert result.may_mark_read is (folder is MessageFolder.RECEIVED)
                    if folder is MessageFolder.SENT:
                        assert len(result.content.recipient_receipts) == 256
                    assert all(
                        a.reference.message.account == alias
                        for a in result.content.attachments
                    )
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [False, True])
def test_received_open_invalidates_page_and_batch_even_if_parser_fails(
    failure: bool,
) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.messages_page(max_age_seconds=60)
                await client.messages(max_pages=1, max_age_seconds=60)
                if failure:
                    fixture.bodies["message_content_received"] = (
                        b"<html></html>",
                        "text/html",
                    )
                    with pytest.raises(ParseError):
                        await client.message_content(REFERENCE, allow_mark_read=True)
                else:
                    result = await client.message_content(
                        REFERENCE, allow_mark_read=True, max_age_seconds=60
                    )
                    assert result.may_mark_read is True
                    assert result.content.reference == REFERENCE
                    assert "Fixture" not in repr(result)
                    # Consent is required even for a warm cache; no accidental
                    # side-effect waiver based on a summary's stale unread flag.
                    with pytest.raises(InvalidInputError):
                        await client.message_content(REFERENCE, max_age_seconds=60)
                await client.messages_page(max_age_seconds=60)
                await client.messages(max_pages=1, max_age_seconds=60)
                assert fixture.count("messages_received") == 4
                assert fixture.count("message_content_received") == 1

    asyncio.run(scenario())
