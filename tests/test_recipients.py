"""Recipient identity/labels, group capability boundaries and parser limits."""

import asyncio
from typing import Any

import pytest

from librus_python_api import RecipientGroupReference, RequestBudget
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.recipients import (
    parse_recipient_group_choices,
    parse_recipient_groups,
    parse_recipients,
)
from tests.http_support import serve
from tests.reads_support import ReadsFixture
from tests.recipients_support import choice_html, groups_html, recipient_html


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


def test_anonymous_hidden_recipient_is_not_fabricated_as_empty_or_named() -> None:
    items = parse_recipients(
        b'<input type="HIDDEN" name="DoKogo" value="301">'
        b'<input type="hidden" name="DoKogo_hid[]" value="301">',
        RecipientGroupReference("sadmin", "student"),
    )
    assert len(items) == 1 and items[0].reference.identifier == "301"
    assert items[0].label is None
    body = (
        b'<input type="HIDDEN" name="DoKogo" value="301">'
        b'<input type="hidden" name="DoKogo_hid[]" value="301">'
        b"<script>refresh_tooltips();</script>"
    )
    assert parse_recipients(body, RecipientGroupReference("sadmin", "student")) == items


def test_group_choices_preserve_selection_scope_labels_and_availability() -> None:
    group = RecipientGroupReference("grupa", "student")
    assert parse_recipient_group_choices(choice_html().encode(), group) == ()
    choices = parse_recipient_group_choices(
        choice_html(
            (("301", "Same Fixture Group", False), ("302", "Same Fixture Group", True))
        ).encode(),
        group,
    )
    assert [c.reference.selection_id for c in choices] == ["301", "302"]
    assert all(
        c.reference.identifier == "grupa"
        and c.reference.account == "student"
        and c.label == "Same Fixture Group"
        for c in choices
    )
    assert choices[0].available and not choices[1].available
    assert "Fixture" not in repr(choices[0]) and "301" not in repr(choices[0].reference)


@pytest.mark.parametrize(
    "extra",
    [
        '<p class="msgEmptyTable">Unknown empty marker</p>',
        '<div class="warning-content">Unknown warning</div>',
    ],
)
def test_recipient_lists_do_not_silently_ignore_unknown_notices(extra: str) -> None:
    with pytest.raises(ParseError):
        parse_recipients(
            recipient_html().replace("</html>", extra + "</html>").encode(),
            RecipientGroupReference("nauczyciel", "student"),
        )


@pytest.mark.parametrize(
    "body",
    [
        '<input type="hidden" name="DoKogo" value="301">'
        '<input type="hidden" name="DoKogo_hid[]" value="302">',
        '<input type="hidden" name="DoKogo" value="301">'
        '<input type="checkbox" name="DoKogo_hid[]" value="301">',
        '<input type="hidden" name="DoKogo" value="301">'
        '<input type="hidden" name="DoKogo_hid[]" value="301">Visible unexpected data',
    ],
)
def test_anonymous_target_pair_cannot_hide_conflicting_id_type_or_display_data(
    body: str,
) -> None:
    with pytest.raises(ParseError):
        parse_recipients(body.encode(), RecipientGroupReference("sadmin", "student"))


@pytest.mark.parametrize(
    "bound",
    [
        "RECIPIENT_MAX_ITEMS",
        "RECIPIENT_MAX_LABEL_LENGTH",
        "RECIPIENT_MAX_TOTAL_TEXT_LENGTH",
    ],
)
def test_choice_limits_fail_without_partial_options(
    bound: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.recipients." + bound, 1)
    with pytest.raises(LimitError):
        parse_recipient_group_choices(
            choice_html(
                (("301", "Fixture", False), ("302", "Other fixture", False))
            ).encode(),
            RecipientGroupReference("grupa", "student"),
        )


@pytest.mark.parametrize(
    "before,after",
    [
        ('value="301"', 'value="../301"'),
        ('value="301"', 'value="0"'),
        ('id="idGrupy"', 'id="unknown"'),
        ('value="0"></option>', 'value="0">Fixture unknown placeholder</option>'),
        ("Wybierz grupę", "Unknown state"),
        ("Fixture Group", "<script>unsafe()</script>"),
    ],
)
def test_group_choices_reject_unknown_controls_or_ambiguous_selections(
    before: str, after: str
) -> None:
    with pytest.raises((ParseError, InvalidInputError, UnsupportedCapabilityError)):
        parse_recipient_group_choices(
            choice_html((("301", "Fixture Group", False),))
            .replace(before, after)
            .encode(),
            RecipientGroupReference("grupa", "student"),
        )


@pytest.mark.parametrize(
    "reference",
    [
        RecipientGroupReference("grupa", "parent"),
        RecipientGroupReference("nauczyciel", "student", "301"),
        RecipientGroupReference("grupa", "student", "../301"),
        RecipientGroupReference("grupa", "student", "0301"),
        RecipientGroupReference("grupa", "student", True),  # type: ignore[arg-type]
    ],
)
def test_foreign_or_invalid_group_selections_fail_before_auth(reference: Any) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            with pytest.raises(InvalidInputError):
                await service.account("student").recipients(reference)
            assert fixture.calls == []

    asyncio.run(scenario())


def test_group_selections_have_exact_forms_and_separate_cache_keys() -> None:
    from aiohttp import web

    class ChoiceFixture(ReadsFixture):
        def handler(self, operation: str) -> Any:
            if operation != "recipients":
                return super().handler(operation)

            async def select(request: web.Request) -> web.Response:
                login = self.record(request)
                self.reads.append((operation, login))
                data = {str(k): str(v) for k, v in (await request.post()).items()}
                assert set(data) == {
                    "typAdresata",
                    "poprzednia",
                    "tabZaznaczonych",
                    "czyWirtualneKlasy",
                    "idGrupy",
                }
                assert (
                    data["typAdresata"] == "grupa"
                    and data["poprzednia"] == "5"
                    and data["tabZaznaczonych"] == ""
                    and data["czyWirtualneKlasy"] == "false"
                )
                identifier = data["idGrupy"]
                body = (
                    choice_html(
                        (
                            ("301", "Fixture group", False),
                            ("302", "Other fixture group", False),
                        )
                    )
                    if identifier == "0"
                    else recipient_html(((identifier, "Fixture Person"),))
                )
                return web.Response(text=body, content_type="text/html")

            return select

    async def scenario() -> None:
        fixture = ChoiceFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                group = RecipientGroupReference("grupa", "student")
                budget = RequestBudget(max_requests=8)
                choices = await client.recipient_group_choices(
                    group, budget=budget, max_age_seconds=60
                )
                first = await client.recipients(
                    choices.items[0].reference, budget=budget, max_age_seconds=60
                )
                second = await client.recipients(
                    choices.items[1].reference, budget=budget, max_age_seconds=60
                )
                assert (
                    first.group.selection_id
                    == first.items[0].reference.selection_id
                    == "301"
                )
                assert (
                    second.group.selection_id
                    == second.items[0].reference.selection_id
                    == "302"
                )
                assert [
                    first.items[0].reference.identifier,
                    second.items[0].reference.identifier,
                ] == ["301", "302"]
                assert (
                    await client.recipient_group_choices(
                        group, budget=budget, max_age_seconds=60
                    )
                    is choices
                )
                assert (
                    await client.recipients(
                        choices.items[0].reference, budget=budget, max_age_seconds=60
                    )
                    is first
                )
                assert (
                    await client.recipients(
                        choices.items[1].reference, budget=budget, max_age_seconds=60
                    )
                    is second
                )
                assert (
                    budget.requests_dispatched == 8 and fixture.count("recipients") == 3
                )

    asyncio.run(scenario())


def test_class_unavailable_recipient_notice_is_not_empty_or_generic_failure() -> None:
    body = (
        '<div><p class="msgEmptyTable">Uczeń nie jest przydzielony do klasy. '
        "W celu wyjaśnienia sytuacji prosimy o kontakt ze szkołą</p></div>"
    )
    with pytest.raises(UnsupportedCapabilityError):
        parse_recipients(
            body.encode(), RecipientGroupReference("rada_rodzicow", "student")
        )


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
            with pytest.raises(InvalidInputError):
                await client.recipient_group_choices(
                    RecipientGroupReference("grupa", "parent")
                )
            for reference in (
                RecipientGroupReference("nauczyciel", "student"),
                RecipientGroupReference("grupa", "student", "301"),
            ):
                with pytest.raises(UnsupportedCapabilityError):
                    await client.recipient_group_choices(reference)
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
