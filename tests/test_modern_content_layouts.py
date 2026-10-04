"""Original detail-layout and recipient-observation contracts over real HTTP."""

import asyncio
import base64
import json
from typing import Any

import pytest

from librus_python_api import MessageFolder, ModernMessageReference
from librus_python_api.exceptions import ErrorKind, LibrusError
from tests.test_modern_communication import CommunicationFixture


def detail(folder: MessageFolder) -> dict[str, Any]:
    return {
        "messageId": "19001",
        "senderName": "Fixture sender",
        "topic": "Fixture topic",
        "sendDate": "2026-01-15T10:20:30+01:00",
        "readDate": "2026-01-15T10:30:00+01:00"
        if folder is MessageFolder.RECEIVED
        else None,
        "Message": base64.b64encode(b"Fixture first\nFixture second").decode(),
        "attachments": [{"id": "401", "filename": "Fixture.txt"}],
        "archive": 0,
        "isMessageWithdrawn": 0,
        "originalMessage": "",
        "originalTopic": "",
    }


def recipient(identifier: str, readed: str | None) -> dict[str, Any]:
    return {
        "receiverId": identifier,
        "name": "Fixture recipient",
        "groupId": "5",
        "className": None,
        "pupilFirstName": None,
        "pupilLastName": None,
        "readed": readed,
        "isCc": "0",
        "isBcc": "0",
    }


@pytest.mark.parametrize("folder", list(MessageFolder))
@pytest.mark.parametrize(
    "encoding", ["plain", "html", "xml", "xml_bom", "xml_preamble"]
)
def test_detail_without_list_flag_decodes_original_body_not_wrapper(
    folder: MessageFolder,
    encoding: str,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        data = detail(folder)
        raw = {
            "plain": b"Fixture first\nFixture second",
            "html": b"<p>Fixture first</p><p>Fixture second</p>",
            "xml": (
                b"<Message><Topic>Not the body</Topic><Content>"
                b"<![CDATA[Fixture first\nFixture second]]></Content></Message>"
            ),
            "xml_bom": (
                b"\xef\xbb\xbf<Message><Topic>Not the body</Topic><Content>"
                b"<![CDATA[Fixture first\nFixture second]]></Content></Message>"
            ),
            "xml_preamble": (
                b"<!-- Fixture preamble --><?fixture layout?>\n"
                b"<Message><Topic>Not the body</Topic><Content>"
                b"<![CDATA[Fixture first\nFixture second]]></Content></Message>"
            ),
        }[encoding]
        data["Message"] = base64.b64encode(raw).decode()
        mailbox = "inbox" if folder is MessageFolder.RECEIVED else "outbox"
        path = f"/api/{mailbox}/messages/19001"
        fixture.responses[path] = (
            200,
            json.dumps({"data": data}).encode(),
            "application/json",
            {},
        )
        async with fixture.running() as service:
            result = await service.account("student").modern_message_content(
                ModernMessageReference(folder, "19001", "student"),
                allow_mark_read=True,
            )
            assert result.text == "Fixture first\nFixture second"
            assert result.summary.has_attachment and len(result.attachments) == 1
            assert result.summary.reference.folder is folder
            assert "Not the body" not in result.text
            assert not fixture.sends

    asyncio.run(scenario())


def test_archived_withdrawn_detail_preserves_inert_original_and_attachment_scope() -> (
    None
):
    async def scenario() -> None:
        fixture = CommunicationFixture()
        data = detail(MessageFolder.RECEIVED) | {
            "archive": 1,
            "isMessageWithdrawn": 1,
            "originalTopic": "Fixture original",
            "originalMessage": base64.b64encode(
                b"<Message><Content><![CDATA[Original &amp; body]]></Content></Message>"
            ).decode(),
        }
        fixture.responses["/api/inbox/messages/19001"] = (
            200,
            json.dumps({"data": data}).encode(),
            "application/json",
            {},
        )
        async with fixture.running() as service:
            result = await service.account("student").modern_message_content(
                ModernMessageReference(MessageFolder.RECEIVED, "19001", "student"),
                allow_mark_read=True,
            )
            assert result.archived and result.withdrawn
            assert result.original_subject == "Fixture original"
            assert result.original_text == "Original & body"
            assert result.attachments[0].reference.archived
            assert not fixture.sends

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid",
    [
        "duplicate_recipient",
        "bad_date",
        "cc_bcc",
        "counts",
        "numeric_id",
        "individual_shape",
        "xml_duplicate",
        "xml_entity",
        "xml_nested",
        "xml_preamble_duplicate",
        "xml_encoding",
        "attachment_mismatch",
        "bad_flag",
    ],
)
def test_detail_rejects_ambiguous_receipts_or_active_wrapper_without_partial_output(
    invalid: str,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        data = detail(MessageFolder.SENT)
        row = recipient("701", None)
        data.update(receivers=[row], readedCount=0, receiversCount=1)
        if invalid == "duplicate_recipient":
            data["receivers"].append(dict(row))
        elif invalid == "bad_date":
            row["readed"] = "not-a-date"
        elif invalid == "cc_bcc":
            row.update(isCc="1", isBcc="1")
        elif invalid == "counts":
            data["readedCount"] = 2
        elif invalid == "numeric_id":
            row["receiverId"] = 701
        elif invalid == "individual_shape":
            data["individualRecipients"] = {}
        elif invalid.startswith("xml_"):
            raw = {
                "xml_duplicate": (
                    b"<Message><Content>A</Content><Content>B</Content></Message>"
                ),
                "xml_entity": b'<!DOCTYPE Message [<!ENTITY leak SYSTEM "file:///etc/passwd">]><Message><Content>&leak;</Content></Message>',
                "xml_nested": (
                    b"<Message><Content><script>fixture()</script></Content></Message>"
                ),
                "xml_preamble_duplicate": (
                    b"<!-- Fixture -->\n<Message><Content>A</Content>"
                    b"<Content>B</Content></Message>"
                ),
                "xml_encoding": (
                    b'<?xml version="1.0" encoding="ISO-8859-1"?>'
                    b"<Message><Content>Fixture \xc3\xa9</Content></Message>"
                ),
            }[invalid]
            data["Message"] = base64.b64encode(raw).decode()
        elif invalid == "attachment_mismatch":
            data["isAnyFileAttached"] = False
        else:
            data["archive"] = 2
        fixture.responses["/api/outbox/messages/19001"] = (
            200,
            json.dumps({"data": data}).encode(),
            "application/json",
            {},
        )
        async with fixture.running() as service:
            with pytest.raises(LibrusError) as error:
                await service.account("student").modern_message_content(
                    ModernMessageReference(MessageFolder.SENT, "19001", "student")
                )
            assert error.value.kind in {
                ErrorKind.PARSE,
                ErrorKind.UNSUPPORTED_CAPABILITY,
            }
            assert (
                sum(
                    path == "/api/outbox/messages/19001"
                    for path, _, _ in fixture.modern_calls
                )
                == 1
            )
            assert not fixture.sends

    asyncio.run(scenario())


@pytest.mark.parametrize("individual", [False, True])
def test_sent_receipts_preserve_read_observation_channel_and_unknown_delivery(
    individual: bool,
) -> None:
    async def scenario() -> None:
        fixture = CommunicationFixture()
        data = detail(MessageFolder.SENT)
        read = recipient("701", "2026-01-15T11:00:00+01:00")
        unread = recipient("702", None) | {"isCc": "1"}
        unknown = recipient("703", None) | {"isBcc": "1"}
        del unknown["readed"]
        data.update(receivers=[read, unread, unknown], readedCount=1, receiversCount=3)
        if individual:
            data["individualRecipients"] = data["receivers"]
            data["receivers"] = [recipient("800", None)]
        fixture.responses["/api/outbox/messages/19001"] = (
            200,
            json.dumps({"data": data}).encode(),
            "application/json",
            {},
        )
        async with fixture.running() as service:
            result = await service.account("student").modern_message_content(
                ModernMessageReference(MessageFolder.SENT, "19001", "student"),
            )
            assert [r.recipient_id for r in result.recipient_receipts] == [
                "701",
                "702",
                "703",
            ]
            assert [r.read for r in result.recipient_receipts] == [True, False, None]
            assert [r.channel for r in result.recipient_receipts] == ["to", "cc", "bcc"]
            assert all(r.delivered is None for r in result.recipient_receipts)
            assert result.recipient_receipts[0].read_at is not None
            assert result.read_count == 1 and result.recipient_count == 3
            assert result.receipt_source == (
                "individualRecipients" if individual else "receivers"
            )
            assert "Fixture recipient" not in repr(result.recipient_receipts)

    asyncio.run(scenario())
