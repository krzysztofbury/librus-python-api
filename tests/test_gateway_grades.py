"""New-schema descriptive grades read from the gateway behind the grades page."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import date
from typing import Any

import pytest

from librus_python_api import GradeKind, GradeView, RequestBudget
from librus_python_api.config import GRADE_MAX_METADATA_LENGTH, GRADE_MAX_RECORDS
from librus_python_api.exceptions import (
    ConnectionError,
    LibrusError,
    LimitError,
    ParseError,
    SessionExpiredError,
    UnsupportedCapabilityError,
)
from librus_python_api.gateway_grades import (
    parse_gateway_subjects,
    parse_gateway_users,
    parse_grade_page,
    parse_partial_grades,
    parse_token_info,
    parse_user_info,
)
from librus_python_api.grade_records import parse_grade_records
from librus_python_api.models import Grades
from librus_python_api.service import LibrusService
from tests.gateway_grades_support import (
    PARENT,
    STUDENT,
    GatewayGradesFixture,
    descriptive_page,
    descriptive_row,
    descriptive_table,
    encoded,
    gateway_subjects,
    gateway_users,
    observed_descriptive_page,
    partial_grade,
    partial_grades,
)
from tests.grade_records_support import grade_box, grades_html
from tests.http_support import serve

LOGIN_REQUESTS = 5  # portal, form, submission, callback, identity


def run(
    fixture: GatewayGradesFixture,
    scenario: Callable[[LibrusService], Coroutine[Any, Any, None]],
) -> None:
    async def main() -> None:
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                await asyncio.wait_for(scenario(service), 30)

    asyncio.run(main())


def read_grades(
    fixture: GatewayGradesFixture, view: GradeView = GradeView.ALL
) -> Grades:
    result: list[Grades] = []

    async def scenario(service: LibrusService) -> None:
        result.append(await service.account("student").grades(view=view))

    run(fixture, scenario)
    return result[0]


def failure(fixture: GatewayGradesFixture) -> LibrusError:
    async def scenario(service: LibrusService) -> None:
        await service.account("student").grades()

    with pytest.raises(LibrusError) as caught:
        run(fixture, scenario)
    return caught.value


# The page table.


@pytest.mark.parametrize(
    "page",
    [descriptive_page(), grades_html(extra=descriptive_table())],
    ids=["alone", "beside-the-ordinary-table"],
)
def test_new_schema_rows_stay_empty_descriptive_subjects_on_the_page(
    page: str,
) -> None:
    # The page alone shows no grades; its subjects keep their unavailable
    # averages as before this read existed.
    records, table = parse_grade_page(page.encode())
    assert records == parse_grade_records(page.encode())
    assert records.descriptive == ()
    assert records.descriptive_summaries == ()
    assert {a.subject for a in records.averages} >= {"Fixture Nature", "Fixture Music"}
    assert table is not None
    assert dict(table.subjects) == {301: "Fixture Nature", 302: "Fixture Music"}
    assert "Fixture" not in repr(table)


def test_a_page_without_the_new_schema_table_has_no_table() -> None:
    assert parse_grade_page(grades_html().encode())[1] is None


def test_the_observed_live_layout_reads_the_populated_table_only() -> None:
    # An owner's live page failed the first implementation, which counted the
    # unclosed row-less table as a second table.
    page = observed_descriptive_page().encode()
    records, table = parse_grade_page(page)
    assert records == parse_grade_records(page)
    assert table is not None
    assert dict(table.subjects) == {301: "Fixture Nature", 302: "Fixture Music"}
    shell_only = observed_descriptive_page().replace("studentRow", "otherRow")
    assert parse_grade_page(shell_only.encode())[1] is None


@pytest.mark.parametrize(
    "table,expected",
    [
        (descriptive_table() * 2, ParseError),
        (descriptive_table(descriptive_row() + descriptive_row()), ParseError),
        (descriptive_table(descriptive_row("A1")), ParseError),
        (descriptive_table(descriptive_row(subject="")), ParseError),
        (
            descriptive_table(descriptive_row() + descriptive_row("302", user="78")),
            ParseError,
        ),
        (descriptive_table(descriptive_row(first="B")), UnsupportedCapabilityError),
        (
            descriptive_table(descriptive_row(second=grade_box(descriptive=True))),
            UnsupportedCapabilityError,
        ),
        (
            descriptive_table(descriptive_row().replace('data-semester="2"', "")),
            UnsupportedCapabilityError,
        ),
        (
            descriptive_table(
                descriptive_row().replace("</tr>", "<td></td><td>-</td></tr>")
            ),
            UnsupportedCapabilityError,
        ),
    ],
    ids=[
        "two-tables",
        "duplicate-subject",
        "non-numeric-subject",
        "blank-subject",
        "two-students",
        "rendered-text",
        "rendered-grade",
        "unknown-cell",
        "extra-cell",
    ],
)
def test_unknown_new_schema_table_layouts_fail_closed(
    table: str, expected: type[Exception]
) -> None:
    with pytest.raises(expected):
        parse_grade_page(descriptive_page(table).encode())


# The JSON parsers.


@pytest.mark.parametrize(
    "parse,body",
    [
        (parse_token_info, {"UserIdentifier": "FIX/1"}),
        (parse_token_info, {"UserIdentifier": 41}),
        (parse_token_info, {"UserType": 2}),
        (parse_user_info, {"IdentifierOfStudentAssignedWithUser": "FIX 1"}),
        (parse_user_info, ["FIX-1"]),
        (parse_partial_grades, partial_grades(partial_grade(semester=3))),
        (parse_partial_grades, partial_grades(partial_grade(semester=True))),
        (parse_partial_grades, partial_grades(partial_grade(semester="1"))),
        (parse_partial_grades, partial_grades(partial_grade(date="2026-02-30"))),
        (parse_partial_grades, partial_grades(partial_grade(date="05.10.2026"))),
        (parse_partial_grades, partial_grades(partial_grade(date="2026-10-05T25:00"))),
        (parse_partial_grades, partial_grades(partial_grade(subjectId=301))),
        (parse_partial_grades, partial_grades(partial_grade(content=["text"]))),
        (parse_partial_grades, {"data": {"0": partial_grade()}}),
        (parse_partial_grades, {"items": []}),
        (parse_gateway_subjects, gateway_subjects({"identifier": "S", "name": 1})),
        (
            parse_gateway_subjects,
            gateway_subjects(
                {"identifier": "S", "numericIdentifier": 1},
                {"identifier": "S", "numericIdentifier": 2},
            ),
        ),
        (
            parse_gateway_subjects,
            gateway_subjects(
                {"identifier": "S", "numericIdentifier": 1},
                {"identifier": "T", "numericIdentifier": 1},
            ),
        ),
        (
            parse_gateway_users,
            gateway_users(
                {"AccountId": "T-1", "LastName": "One"},
                {"AccountId": "T-1", "LastName": "Other"},
            ),
        ),
        (parse_gateway_users, {"Users": [{"LastName": "Fixture"}]}),
    ],
)
def test_malformed_gateway_json_fails_as_a_parse_error(
    parse: Callable[[bytes], object], body: object
) -> None:
    with pytest.raises(ParseError):
        parse(encoded(body))
    with pytest.raises(ParseError):
        parse(b"<html>not json</html>")


@pytest.mark.parametrize(
    "parse,body",
    [
        (parse_partial_grades, {"data": [partial_grade()] * (GRADE_MAX_RECORDS + 1)}),
        (
            parse_partial_grades,
            partial_grades(
                partial_grade(content="x" * (GRADE_MAX_METADATA_LENGTH + 1))
            ),
        ),
        (
            parse_gateway_subjects,
            {"data": [{"identifier": f"S{n}"} for n in range(1025)]},
        ),
        (parse_gateway_users, {"Users": [{"AccountId": "T"}] * 8193}),
    ],
)
def test_oversized_gateway_json_fails_as_a_limit(
    parse: Callable[[bytes], object], body: object
) -> None:
    with pytest.raises(LimitError):
        parse(encoded(body))


def test_an_empty_or_identical_repetition_is_valid() -> None:
    assert parse_partial_grades(encoded({"data": [], "pagination": {}})) == ()
    assert parse_user_info(encoded({})) is None
    assert parse_user_info(encoded({"IdentifierOfStudentAssignedWithUser": ""})) is None
    same = {"AccountId": "T-1", "FirstName": "Ada", "LastName": "Fixture"}
    assert dict(parse_gateway_users(encoded(gateway_users(same, same)))) == {
        "T-1": "Fixture Ada"
    }


@pytest.mark.parametrize(
    "envelope",
    [
        {"pagination": {"total": 9}},
        {"meta": {"pagination": {"totalCount": "9"}}},
        {"pagination": {"page": 1, "pages": 2}},
        {"pagination": {"lastPage": 4}},
        {"links": {"next": "/fixture?page=2"}},
        {"pagination": {"nextPage": 2}},
        {"pagination": {"has_more": True}},
        {"pagination": {"perPage": 2}},
    ],
)
def test_a_pagination_member_showing_more_items_is_unsupported(
    envelope: dict[str, Any],
) -> None:
    # No paginated response was observed; a first page alone is never returned.
    with pytest.raises(UnsupportedCapabilityError):
        parse_partial_grades(encoded(partial_grades(**envelope)))
    with pytest.raises(UnsupportedCapabilityError):
        parse_gateway_subjects(encoded(gateway_subjects(**envelope)))


@pytest.mark.parametrize(
    "envelope",
    [
        {"pagination": {"page": 1, "pages": 1, "total": 2, "perPage": 50}},
        {"pagination": {"total": 2, "perPage": 2, "next": None, "hasMore": False}},
        {"pagination": {"page": 1}},
    ],
)
def test_a_pagination_member_of_a_complete_collection_is_accepted(
    envelope: dict[str, Any],
) -> None:
    assert len(parse_partial_grades(encoded(partial_grades(**envelope)))) == 2


# The service read.


def test_parent_read_adds_gateway_grades_to_the_all_view() -> None:
    fixture = GatewayGradesFixture()
    fixture.grade_body = grades_html(extra=descriptive_table())
    result = read_grades(fixture)
    assert fixture.operations() == [
        "descriptive_token_info",
        "descriptive_user_info",
        "descriptive_partial_grades",
        "descriptive_subjects",
        "descriptive_users",
    ]
    token, user, grades, subjects, users = fixture.gateway
    assert [call["method"] for call in fixture.gateway] == [
        "GET",
        "GET",
        "POST",
        "GET",
        "GET",
    ]
    assert user["reference"] == PARENT
    # A parent login reads the grades of its assigned student.
    assert grades["reference"] == STUDENT
    assert grades["body"] == b"{}"
    assert grades["content_type"] == "application/json"
    assert all(call["query"] == "" for call in fixture.gateway)
    assert all(
        call["body"] == b"" and call["content_type"] is None
        for call in (token, user, subjects, users)
    )
    assert {call["login"] for call in fixture.gateway} == {"student"}
    assert len(fixture.calls) == LOGIN_REQUESTS + 1 + 5
    page = parse_grade_records(fixture.grade_body.encode())
    records = result.records
    assert records.numeric == page.numeric
    assert records.averages == page.averages
    first, second = records.descriptive
    # The page's name for the subject's numeric ID wins over the gateway name.
    assert (first.subject, first.raw, first.day, first.semester) == (
        "Fixture Nature",
        "B",
        date(2026, 10, 5),
        1,
    )
    assert (first.teacher, first.comment, first.kind, first.href) == (
        "Fixture Ada",
        "Fixture remark",
        GradeKind.CURRENT,
        None,
    )
    assert first.metadata == (
        ("Obszar", "Fixture listening"),
        ("Treść", "Fixture follows spoken steps"),
        ("Dodał", "Author"),
        ("Komentarz", "Fixture remark"),
        ("Skala", "B"),
    )
    # Without a scale value the content is the grade; a subject the page does
    # not list keeps the gateway name; an unlisted teacher stays unknown.
    assert (second.subject, second.raw, second.day, second.semester) == (
        "Fixture Choir",
        "Fixture sings in tune",
        date(2027, 2, 10),
        2,
    )
    assert (second.teacher, second.comment) == (None, None)
    assert second.metadata == (("Treść", "Fixture sings in tune"),)
    for item in (records, first, second):
        assert "Fixture" not in repr(item)


def test_student_read_uses_its_own_identifier_and_empty_data_is_empty() -> None:
    # Observed live: an empty data collection with a pagination member.
    fixture = GatewayGradesFixture()
    fixture.bodies["descriptive_token_info"] = {"UserIdentifier": STUDENT}
    fixture.bodies["descriptive_user_info"] = {
        "IdentifierOfStudentAssignedWithUser": None
    }
    fixture.bodies["descriptive_partial_grades"] = {
        "data": [],
        "pagination": {"page": 1},
    }
    result = read_grades(fixture)
    assert fixture.operations() == [
        "descriptive_token_info",
        "descriptive_user_info",
        "descriptive_partial_grades",
    ]
    assert fixture.gateway[2]["reference"] == STUDENT
    assert result.records == parse_grade_records(descriptive_page().encode())
    assert len(fixture.calls) == LOGIN_REQUESTS + 1 + 3


def test_pages_without_the_table_and_other_views_make_no_gateway_request() -> None:
    fixture = GatewayGradesFixture()
    fixture.grade_body = grades_html(first=grade_box(day="2026-10-01"))
    result = read_grades(fixture)
    assert fixture.gateway == []
    assert result.records == parse_grade_records(fixture.grade_body.encode())
    for view in (GradeView.WEEK, GradeView.LAST_LOGIN):
        # The page script narrows these views by an unknown field.
        fixture = GatewayGradesFixture()
        result = read_grades(fixture, view)
        assert fixture.gateway == []
        assert result.records.descriptive == ()
        assert len(fixture.view_posts) == 1


def test_grade_windows_filter_gateway_grades_from_the_same_collection() -> None:
    fixture = GatewayGradesFixture()

    async def scenario(service: LibrusService) -> None:
        client = service.account("student")
        result = await client.grades()
        window = await client.grades_window(
            date(2027, 1, 1), date(2027, 12, 31), max_age_seconds=60
        )
        assert [g.raw for g in window.descriptive] == ["Fixture sings in tune"]
        assert window.observation is result.observation
        assert len(fixture.view_posts) == 1
        assert fixture.operations().count("descriptive_partial_grades") == 1

    run(fixture, scenario)


@pytest.mark.parametrize(
    "operation,body",
    [
        (
            "descriptive_partial_grades",
            partial_grades(partial_grade(subjectId="SUBJ-UNKNOWN")),
        ),
        (
            "descriptive_partial_grades",
            partial_grades(partial_grade(subjectId="SUBJ-C")),
        ),
        (
            "descriptive_partial_grades",
            partial_grades(partial_grade(scaleValue={"value": " "}, content=None)),
        ),
        ("descriptive_partial_grades", partial_grades(partial_grade(semester=0))),
        ("descriptive_partial_grades", partial_grades(partial_grade(date=""))),
        ("descriptive_subjects", {"data": "SUBJ-A"}),
        ("descriptive_users", {"Users": None}),
        ("descriptive_user_info", {"IdentifierOfStudentAssignedWithUser": "../x"}),
        ("descriptive_token_info", {}),
    ],
    ids=[
        "unknown-subject",
        "unnamed-subject",
        "no-grade-value",
        "semester",
        "date",
        "subjects",
        "users",
        "student-identifier",
        "token",
    ],
)
def test_malformed_gateway_responses_fail_the_whole_grade_read(
    operation: str, body: object
) -> None:
    fixture = GatewayGradesFixture()
    fixture.bodies[operation] = body
    assert isinstance(failure(fixture), ParseError)


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, ConnectionError),
        (404, ConnectionError),
        (500, ConnectionError),
        (403, UnsupportedCapabilityError),
        (401, SessionExpiredError),
    ],
)
@pytest.mark.parametrize(
    "operation", ["descriptive_token_info", "descriptive_partial_grades"]
)
def test_gateway_errors_propagate_without_a_partial_result_or_replay(
    operation: str, status: int, expected: type[Exception]
) -> None:
    fixture = GatewayGradesFixture()
    fixture.raw[operation] = (status, b"", "application/json")
    assert isinstance(failure(fixture), expected)
    # Neither the gateway read nor the credentials are submitted again.
    assert fixture.operations().count(operation) == 1
    assert fixture.logins == {"student": 1}
    assert len(fixture.view_posts) == 1


def test_a_refused_gateway_leaves_the_other_grade_views_readable() -> None:
    # The page-level access-denied cooldown covers every grade view, so a
    # gateway refusal must not raise it; notifications read LAST_LOGIN.
    fixture = GatewayGradesFixture()
    fixture.raw["descriptive_users"] = (403, b"", "application/json")

    async def scenario(service: LibrusService) -> None:
        client = service.account("student")
        with pytest.raises(UnsupportedCapabilityError):
            await client.grades()
        last = await client.grades(view=GradeView.LAST_LOGIN)
        assert last.view is GradeView.LAST_LOGIN

    run(fixture, scenario)


@pytest.mark.parametrize(
    "raw",
    [
        (200, b"not json", "application/json"),
        (200, encoded(partial_grades()), "text/html"),
        (204, b"", "application/json"),
    ],
)
def test_a_non_json_gateway_response_is_a_parse_error(
    raw: tuple[int, bytes, str],
) -> None:
    fixture = GatewayGradesFixture()
    fixture.raw["descriptive_partial_grades"] = raw
    assert isinstance(failure(fixture), ParseError)


def test_pagination_showing_more_fails_the_grade_read() -> None:
    fixture = GatewayGradesFixture()
    fixture.bodies["descriptive_partial_grades"] = partial_grades(
        pagination={"page": 1, "pages": 2}
    )
    assert isinstance(failure(fixture), UnsupportedCapabilityError)
    assert "descriptive_subjects" not in fixture.operations()


def test_gateway_reads_share_the_grade_read_budget() -> None:
    fixture = GatewayGradesFixture()
    budget = RequestBudget(max_requests=LOGIN_REQUESTS + 1 + 2)

    async def scenario(service: LibrusService) -> None:
        with pytest.raises(LimitError):
            await service.account("student").grades(budget=budget)
        assert budget.requests_dispatched == LOGIN_REQUESTS + 1 + 2
        assert service.snapshot().requests_dispatched == budget.requests_dispatched

    run(fixture, scenario)
    assert fixture.operations() == ["descriptive_token_info", "descriptive_user_info"]


def test_page_and_gateway_records_share_the_grade_record_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The page holds one record and the gateway adds two.
    monkeypatch.setattr("librus_python_api.service.GRADE_MAX_RECORDS", 3)
    fixture = GatewayGradesFixture()
    fixture.grade_body = grades_html(extra=descriptive_table())
    assert len(read_grades(fixture).records.descriptive) == 2
    monkeypatch.setattr("librus_python_api.service.GRADE_MAX_RECORDS", 2)
    fixture = GatewayGradesFixture()
    fixture.grade_body = grades_html(extra=descriptive_table())
    assert isinstance(failure(fixture), LimitError)
