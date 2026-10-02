import asyncio
from collections.abc import Callable

import pytest

from librus_python_api import Availability, RequestBudget
from librus_python_api.config import GRADE_MAX_SUBJECTS
from librus_python_api.exceptions import (
    AccessDeniedError,
    LimitError,
    ParseError,
)
from librus_python_api.grade_parsers import parse_final_grades
from tests.grade_support import GradeFixture, summary_html
from tests.http_support import serve


@pytest.mark.parametrize("optional", ["midterm", "predicted"])
def test_summary_semantics_and_optional_column_presence(optional: str) -> None:
    (item,) = parse_final_grades(summary_html().encode())
    assert item.subject == "Fixture Language"
    assert item.annual.raw == "4+"
    assert item.midterm.raw == "progressing"
    assert item.predicted_annual.raw == "-"
    assert item.predicted_annual.availability == Availability.AVAILABLE
    (absent,) = parse_final_grades(
        summary_html(
            include_midterm=optional != "midterm",
            include_predicted=optional != "predicted",
        ).encode()
    )
    value = absent.midterm if optional == "midterm" else absent.predicted_annual
    assert value.raw is None
    assert value.availability == Availability.UNAVAILABLE
    assert "Fixture" not in repr(item)
    assert "progressing" not in repr(item)


def test_unassigned_summaries_do_not_mean_empty_or_unavailable_success() -> None:
    (item,) = parse_final_grades(
        summary_html(annual="-", midterm="", predicted="-").encode()
    )
    assert item.annual.raw == "-"
    assert item.annual.availability == Availability.AVAILABLE
    assert item.midterm.raw == ""
    assert item.midterm.availability == Availability.AVAILABLE


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("very<br/>good", "very good"),
        ("<p>making</p><p>progress</p>", "making progress"),
        ("5<span>+</span>", "5+"),
    ],
)
def test_rendered_summary_boundaries_preserve_words_and_grade_symbols(
    markup: str,
    expected: str,
) -> None:
    body = summary_html().replace("<td>4+</td>", f"<td>{markup}</td>")
    (item,) = parse_final_grades(body.encode())
    assert item.annual.raw == expected


def test_browser_html_end_tag_repair_keeps_summary_semantics() -> None:
    # Independently authored mismatched tags, not a live response excerpt.
    body = summary_html().replace("<body>", "<body><div>Display noise</em></div>")
    (item,) = parse_final_grades(body.encode())
    assert item.subject == "Fixture Language"
    assert item.annual.raw == "4+"


def test_html_repair_does_not_ignore_duplicate_ids() -> None:
    body = summary_html().replace(
        "<body>", '<body><span id="duplicate">a</span><span id="duplicate">b</span>'
    )
    with pytest.raises(ParseError):
        parse_final_grades(body.encode())


@pytest.mark.parametrize(
    "spacer",
    [
        '<tr><td colspan="7"></td></tr>',
        '<tr><td colspan="7">Unexpected content</td></tr>',
    ],
)
def test_only_empty_full_width_spacer_is_not_a_subject(spacer: str) -> None:
    body = summary_html().replace("</tbody>", spacer + "</tbody>")
    if "Unexpected" in spacer:
        with pytest.raises(ParseError):
            parse_final_grades(body.encode())
    else:
        (item,) = parse_final_grades(body.encode())
        assert item.annual.raw == "4+"


@pytest.mark.parametrize("portal_without_redirect", [False, True])
def test_login_grant_chain_and_form_reuse_are_bounded_wire_behaviour(
    portal_without_redirect: bool,
) -> None:
    async def scenario() -> None:
        fixture = GradeFixture()
        fixture.grant_chain = True
        fixture.identity_mode = "account_reference"
        fixture.portal_without_redirect = portal_without_redirect
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                result = await service.account("student").final_grades()
                assert result.identity.owner.id == "student"
                assert result.identity.student.id == "student-shared"
                assert result.items[0].annual.raw == "4+"
                assert fixture.logins == {"student": 1}
                assert [path for path, _ in fixture.calls] == [
                    "/loguj/portalRodzina",
                    "/OAuth/Authorization",
                    "/OAuth/Authorization",  # The only POST, not another GET.
                    "/OAuth/Authorization/2FA",
                    "/OAuth/Authorization/PerformLogin",
                    "/OAuth/Authorization/Grant",
                    "/loguj",
                    "/gateway/api/2.0/Me",
                    "/przegladaj_oceny/uczen",
                ]

    asyncio.run(scenario())


def test_reordered_header_and_body_columns_stay_aligned() -> None:
    markup = (
        summary_html()
        .replace("<thead>", '<thead><tr><th colspan="7">Group heading</th></tr>')
        .replace('<th title="Ocena roczna&lt;br /&gt;fixture year">Annual</th>', "")
        .replace("</tr></thead>", '<th title="Ocena roczna">Annual</th></tr></thead>')
        .replace("<td>4+</td>", "")
        .replace("</tr></tbody>", "<td>4+</td></tr></tbody>")
    )
    (item,) = parse_final_grades(markup.encode())
    assert (item.midterm.raw, item.predicted_annual.raw, item.annual.raw) == (
        "progressing",
        "-",
        "4+",
    )


def test_behaviour_can_span_unused_columns_without_losing_values() -> None:
    markup = summary_html(subject="Zachowanie", annual="very good").replace(
        "<td></td><td></td><td>progressing</td>",
        '<td colspan="3">good</td>',
    )
    (item,) = parse_final_grades(markup.encode())
    assert item.midterm.raw == "good"
    assert item.annual.raw == "very good"
    assert item.predicted_annual.raw == "-"


def test_other_tables_and_detail_rows_are_not_summary_subjects() -> None:
    markup = (
        summary_html()
        .replace("<body>", "<body><table><tr><td>Not a subject</td></tr></table>")
        .replace(
            "</tbody>",
            '<tr><td colspan="7"><table><tr><td>Nested detail</td></tr>'
            "</table></td></tr>"
            "<tr><td></td><td>Ocena</td><td>Inline detail</td></tr></tbody>",
        )
    )
    items = parse_final_grades(markup.encode())
    assert [item.subject for item in items] == ["Fixture Language"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda text: "<html><form>login or wrong page</form></html>",
        lambda text: text.replace("Ocena roczna", "Unknown summary"),
        lambda text: text.replace("<td>4+</td>", ""),
        lambda text: text.replace("<td>4+</td>", "<td>4+</td><td>extra</td>"),
        lambda text: text.replace("<td>4+</td>", '<td rowspan="2">4+</td>'),
        lambda text: text.replace("<td>4+</td>", '<td colspan="2">4+</td>'),
        lambda text: text.replace("<td>Fixture Language</td>", "<td></td>"),
        lambda text: text.replace('<th colspan="2">', '<th colspan="0">'),
        lambda text: text.replace('<th colspan="2">', '<th colspan="bad">'),
        lambda text: text.replace("<tbody>", "<tbody><tr><td>short</td></tr>"),
        lambda text: text.replace("<tbody>", "<tbody><tr></tr>"),
        lambda text: text.replace(
            "</tbody>",
            "<tr><td></td><td>another subject<table><tr><td>detail</td></tr>"
            "</table></td></tr></tbody>",
        ),
        lambda text: text.replace(
            '<th title="Przewidywana ocena roczna">', '<th title="Ocena roczna">'
        ),
        lambda text: text.replace(
            "<tbody>",
            "<tbody><tr><td></td><td>Fixture Language</td><td>1</td><td></td>"
            "<td></td><td>2</td><td>3</td></tr>",
        ),
        lambda text: text.replace(
            "<tr><td></td><td>Fixture Language</td><td>4+</td><td></td><td></td>"
            "<td>progressing</td><td>-</td></tr>",
            "",
        ),
        lambda text: text.replace(
            "</body>", text.split("<body>")[1].split("</body>")[0] + "</body>"
        ),
    ],
    ids=[
        "wrong-page",
        "missing-annual",
        "short",
        "long",
        "rowspan",
        "ordinary-colspan",
        "no-subject",
        "zero-span",
        "bad-span",
        "short-row",
        "empty-row",
        "nested-subject",
        "duplicate-header",
        "duplicate-subject",
        "no-rows",
        "ambiguous-tables",
    ],
)
def test_malformed_summaries_fail_instead_of_returning_partial_rows(
    mutate: Callable[[str], str],
) -> None:
    with pytest.raises(ParseError) as caught:
        parse_final_grades(mutate(summary_html()).encode())
    assert caught.value.__context__ is None
    assert "Fixture" not in str(caught.value)


def test_merged_cell_cannot_fabricate_distinct_summary_values() -> None:
    markup = summary_html(subject="Zachowanie").replace(
        "<td>progressing</td><td>-</td>", '<td colspan="2">good</td>'
    )
    with pytest.raises(ParseError):
        parse_final_grades(markup.encode())


@pytest.mark.parametrize("count", [GRADE_MAX_SUBJECTS, GRADE_MAX_SUBJECTS + 1])
def test_summary_subject_bound(count: int) -> None:
    markup = summary_html()
    row = (
        "<tr><td></td><td>Topic {index}</td><td>3</td><td></td><td></td>"
        "<td>-</td><td></td></tr>"
    )
    start = markup.index("<tbody>") + len("<tbody>")
    end = markup.index("</tbody>")
    markup = (
        markup[:start]
        + "".join(row.format(index=index) for index in range(count))
        + markup[end:]
    )
    if count == GRADE_MAX_SUBJECTS:
        assert len(parse_final_grades(markup.encode())) == count
    else:
        with pytest.raises(LimitError):
            parse_final_grades(markup.encode())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda text: text.replace('<th colspan="2">', '<th colspan="65">'),
        lambda text: text.replace("<td>4+</td>", "<td>" + "x" * 1025 + "</td>"),
    ],
)
def test_summary_column_and_value_bounds(mutate: Callable[[str], str]) -> None:
    with pytest.raises(LimitError):
        parse_final_grades(mutate(summary_html()).encode())


def test_summary_session_recovery_invalidates_other_cached_account_results() -> None:
    async def scenario() -> None:
        fixture = GradeFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                previous = await client.final_grades()
                profile = await client.student_information()
                fixture.expire_grades["student"] = 1
                budget = RequestBudget(max_requests=7)
                recovered = await client.final_grades(budget=budget)
                assert (
                    recovered.observation.session_generation
                    == previous.observation.session_generation + 1
                )
                assert budget.requests_dispatched == 7
                assert fixture.logins == {"student": 2}
                assert await client.final_grades(max_age_seconds=60) is recovered
                assert (
                    await client.student_information(max_age_seconds=60) is not profile
                )
                assert len(fixture.calls) == 15

    asyncio.run(scenario())


def test_summary_denial_cooldown_does_not_block_profile_or_another_login() -> None:
    async def scenario() -> None:
        fixture = GradeFixture()
        fixture.grade_status["parent"] = 403
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student", "parent")) as service:
                await service.account("student").final_grades()
                with pytest.raises(AccessDeniedError):
                    await service.account("parent").final_grades()
                before = len(fixture.calls)
                with pytest.raises(AccessDeniedError):
                    await service.account("parent").final_grades()
                assert len(fixture.calls) == before
                assert (
                    await service.account("parent").student_information()
                ).identity.owner.id == "parent"
                assert fixture.logins == {"student": 1, "parent": 1}

    asyncio.run(scenario())
