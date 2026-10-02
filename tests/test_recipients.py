"""Recipient identity/labels, group capability boundaries and parser limits."""

import asyncio

import pytest

from librus_python_api import RecipientGroupReference, RequestBudget
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.recipients import parse_recipient_groups, parse_recipients
from tests.http_support import serve
from tests.reads_support import ReadsFixture
from tests.recipients_support import groups_html, recipient_html


def test_group_header_is_not_a_selector_and_named_tokens_are_preserved() -> None:
    groups = parse_recipient_groups(groups_html().encode(), "student")
    assert [g.reference.identifier for g in groups] == [
        "nauczyciel",
        "wychowawca",
        "grupa",
    ]
    assert all(g.reference.account == "student" for g in groups)
    assert groups[0].label == "Fixture nauczyciel group"
    assert groups[0].available and groups[0].lookup_supported
    assert not groups[2].lookup_supported
    assert "Fixture" not in repr(groups[0]) and "student" not in repr(
        groups[0].reference
    )


def test_group_count_accepts_thirty_two_and_refuses_thirty_three() -> None:
    assert (
        len(
            parse_recipient_groups(
                groups_html(tuple(f"fixture{i}" for i in range(32))).encode(), "student"
            )
        )
        == 32
    )
    with pytest.raises(LimitError):
        parse_recipient_groups(
            groups_html(tuple(f"fixture{i}" for i in range(33))).encode(), "student"
        )


def test_recipient_same_name_distinct_ids_do_not_overwrite_and_keep_scope() -> None:
    reference = RecipientGroupReference("nauczyciel", "student")
    items = parse_recipients(
        recipient_html(
            (("101", "Same Fixture Name"), ("102", "Same Fixture Name"))
        ).encode(),
        reference,
    )
    assert len(items) == 2 and [i.reference.identifier for i in items] == ["101", "102"]
    assert all(
        i.label == "Same Fixture Name"
        and i.reference.account == "student"
        and i.reference.group_type == "nauczyciel"
        for i in items
    )
    assert "Fixture" not in repr(items[0]) and "101" not in repr(items[0].reference)


@pytest.mark.parametrize(
    "before,after",
    [
        ('value="nauczyciel"', 'value="../bad"'),
        ('for="radio_nauczyciel"', 'for="radio_other"'),
        ('type="radio"', 'type="checkbox"'),
        ("Fixture nauczyciel group", "<script>fixture()</script>"),
    ],
)
def test_invalid_group_structure_never_silently_skips(before: str, after: str) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_recipient_groups(groups_html().replace(before, after).encode(), "student")


@pytest.mark.parametrize(
    "before,after",
    [
        ('for="adresat_101"', 'for="adresat_999"'),
        ('value="101"', 'value="102"'),
        ('type="checkbox"', 'type="radio"'),
        ("adresat_101", "adresat_../101"),
    ],
)
def test_invalid_recipient_reference_or_control_fails(before: str, after: str) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_recipients(
            recipient_html().replace(before, after).encode(),
            RecipientGroupReference("nauczyciel", "student"),
        )


def test_missing_empty_layout_duplicates_and_disabled_group_are_explicit() -> None:
    assert not parse_recipient_groups(
        groups_html()
        .replace('value="nauczyciel"', 'disabled value="nauczyciel"')
        .encode(),
        "student",
    )[0].available
    with pytest.raises(ParseError):
        parse_recipient_groups(
            groups_html(("nauczyciel", "nauczyciel")).encode(), "student"
        )
    with pytest.raises(ParseError):
        parse_recipients(
            b"<html></html>", RecipientGroupReference("nauczyciel", "student")
        )
    with pytest.raises(ParseError):
        parse_recipients(
            recipient_html(
                (("101", "Fixture Person"), ("101", "Fixture Person"))
            ).encode(),
            RecipientGroupReference("nauczyciel", "student"),
        )


@pytest.mark.parametrize(
    "bound",
    [
        "RECIPIENT_MAX_ITEMS",
        "RECIPIENT_MAX_LABEL_LENGTH",
        "RECIPIENT_MAX_TOTAL_TEXT_LENGTH",
    ],
)
def test_recipient_limits_are_errors_not_truncation(
    bound: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.recipients." + bound, 1)
    with pytest.raises(LimitError):
        parse_recipients(
            recipient_html().encode(), RecipientGroupReference("nauczyciel", "student")
        )


def test_numeric_checkbox_without_label_cannot_silently_disappear() -> None:
    body = recipient_html().replace(
        "</div>", '<input type="checkbox" id="check_103" value="103"></div>'
    )
    with pytest.raises(ParseError):
        parse_recipients(
            body.encode(), RecipientGroupReference("nauczyciel", "student")
        )


def test_invalid_scope_and_subgroup_fail_before_login() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            client = service.account("student")
            for reference in (
                RecipientGroupReference("nauczyciel", "parent"),
                RecipientGroupReference("../1", "student"),
            ):
                with pytest.raises(InvalidInputError):
                    await client.recipients(reference)
            with pytest.raises(UnsupportedCapabilityError):
                await client.recipients(RecipientGroupReference("grupa", "student"))
            assert fixture.calls == []

    asyncio.run(scenario())


def test_distinct_groups_have_distinct_cache_keys_and_share_a_budget() -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                budget = RequestBudget(max_requests=8)
                groups = await client.recipient_groups(
                    budget=budget, max_age_seconds=60
                )
                first = await client.recipients(
                    groups.groups[0].reference, budget=budget, max_age_seconds=60
                )
                other = await client.recipients(
                    groups.groups[1].reference, budget=budget, max_age_seconds=60
                )
                assert (
                    first.group != other.group
                    and first.items[0].reference.group_type
                    != other.items[0].reference.group_type
                )
                assert budget.requests_dispatched == 8
                assert (
                    await client.recipients(
                        groups.groups[0].reference, budget=budget, max_age_seconds=60
                    )
                    is first
                )
                assert budget.requests_dispatched == 8

    asyncio.run(scenario())


def test_full_recipient_response_preserves_two_thousand_distinct_same_name_ids() -> (
    None
):
    async def scenario() -> None:
        fixture = ReadsFixture()
        body = recipient_html(tuple((str(i), "Fixture") for i in range(2000)))
        fixture.bodies["recipients"] = (body.encode(), "text/html")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                result = await service.account("student").recipients(
                    RecipientGroupReference("nauczyciel", "student")
                )
                assert (
                    len(result.items) == 2000
                    and len({r.reference.identifier for r in result.items}) == 2000
                )
                assert all(r.label == "Fixture" for r in result.items)

    asyncio.run(scenario())
