"""Original contracts for attendance detail, gateway metadata and ratio policies."""

import asyncio
import json
from datetime import date

import pytest
from aiohttp import web

from librus_python_api import RequestBudget
from librus_python_api.attendance import parse_attendance_detail
from librus_python_api.attendance_frequency import (
    parse_gateway_attendance,
    summarize_frequency,
)
from librus_python_api.config import ACCOUNT_RESULT_CACHE_SIZE, ATTENDANCE_MAX_RECORDS
from librus_python_api.exceptions import (
    ConnectionError,
    InvalidInputError,
    LimitError,
    MaintenanceError,
    ParseError,
    SessionExpiredError,
    ThrottledError,
)
from tests.attendance_support import DETAIL, AttendanceFixture, gateway_rows
from tests.http_support import serve


class FrequencyFixture(AttendanceFixture):
    def __init__(self) -> None:
        super().__init__()
        self.gateway_body = gateway_rows()
        self.detail_body = DETAIL
        self.metadata_requests: list[tuple[str, str]] = []
        self.gateway_expiry = 0
        # Collection rows: lesson ID -> subject ID, and subject IDs listed by name.
        # None makes the collection route unavailable.
        self.collection_lessons: dict[int, int | None] | None = {41: 51}
        self.collection_subjects: tuple[int, ...] | None = (51,)
        # Collection name -> how many next reads answer with a non-JSON body.
        self.malformed_collections: dict[str, int] = {}
        # The school's attendance type list; None makes the route unavailable.
        self.types: list[dict[str, object]] | None = []
        # Per-reference routes answer these IDs with this HTTP status.
        self.missing_lessons: dict[str, int] = {}
        self.missing_subjects: dict[str, int] = {}

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get("/przegladaj_nb/szczegoly/{id}", self.detail)
        app.router.add_get("/gateway/api/2.0/Attendances", self.gateway)
        app.router.add_get("/gateway/api/2.0/Attendances/Types", self.attendance_types)
        app.router.add_get("/gateway/api/2.0/Lessons", self.lessons)
        app.router.add_get("/gateway/api/2.0/Subjects", self.subjects)
        app.router.add_get("/gateway/api/2.0/Lessons/{id}", self.lesson)
        app.router.add_get("/gateway/api/2.0/Subjects/{id}", self.subject)
        return app

    async def lessons(self, request: web.Request) -> web.Response:
        self.record(request)
        self.metadata_requests.append(("lessons", "*"))
        if self.malformed_collections.get("lessons"):
            self.malformed_collections["lessons"] -= 1
            return web.Response(text="<html>", content_type="application/json")
        if self.collection_lessons is None:
            return web.Response(status=404)
        return web.json_response(
            {
                "Lessons": [
                    {"Id": lesson, "Teacher": {"Id": 7}}
                    | ({} if subject is None else {"Subject": {"Id": subject}})
                    for lesson, subject in self.collection_lessons.items()
                ],
                "Url": "fixture",
            }
        )

    async def attendance_types(self, request: web.Request) -> web.Response:
        self.record(request)
        self.metadata_requests.append(("types", "*"))
        if self.types is None:
            return web.Response(status=404)
        return web.json_response({"Types": self.types, "Url": "fixture"})

    async def subjects(self, request: web.Request) -> web.Response:
        login = self.record(request)
        self.metadata_requests.append(("subjects", "*"))
        if self.malformed_collections.get("subjects"):
            self.malformed_collections["subjects"] -= 1
            return web.Response(text="<html>", content_type="application/json")
        if self.collection_subjects is None:
            return web.Response(status=404)
        return web.json_response(
            {
                "Subjects": [
                    {"Id": subject, "Name": "Fixture " + login, "No": 1, "Short": "F"}
                    for subject in self.collection_subjects
                ]
            }
        )

    async def gateway(self, request: web.Request) -> web.Response:
        self.record(request)
        if self.gateway_expiry:
            self.gateway_expiry -= 1
            return web.Response(status=401)
        return web.Response(body=self.gateway_body, content_type="application/json")

    async def detail(self, request: web.Request) -> web.Response:
        self.record(request)
        self.metadata_requests.append(("detail", request.match_info["id"]))
        return web.Response(text=self.detail_body, content_type="text/html")

    async def lesson(self, request: web.Request) -> web.Response:
        self.record(request)
        self.metadata_requests.append(("lesson", request.match_info["id"]))
        if request.match_info["id"] in self.missing_lessons:
            return web.Response(status=self.missing_lessons[request.match_info["id"]])
        return web.json_response(
            {"Lesson": {"Id": int(request.match_info["id"]), "Subject": {"Id": 51}}}
        )

    async def subject(self, request: web.Request) -> web.Response:
        login = self.record(request)
        self.metadata_requests.append(("subject", request.match_info["id"]))
        if request.match_info["id"] in self.missing_subjects:
            return web.Response(status=self.missing_subjects[request.match_info["id"]])
        return web.json_response(
            {
                "Subject": {
                    "Id": int(request.match_info["id"]),
                    "Name": "Fixture " + login,
                }
            }
        )


def test_detail_preserves_labels_and_block_boundaries() -> None:
    content = parse_attendance_detail(DETAIL.encode())
    assert content.notes == ()
    assert content.fields == (
        ("Data", "2026-10-01"),
        ("Temat zajęć", "Fixture topic"),
    )


def test_detail_control_footer_is_not_a_malformed_data_row() -> None:
    footer = (
        '<tr class="line0"><td colspan="2" class="center">'
        '<button type="button" onclick="window.close()">Zamknij</button>'
        "</td></tr>"
    )
    body = DETAIL.replace("</table>", footer + "</table>")
    content = parse_attendance_detail(body.encode())
    assert content.notes == ("Zamknij",)
    assert content.fields == (
        ("Data", "2026-10-01"),
        ("Temat zajęć", "Fixture topic"),
    )
    ancillary = body.replace("Zamknij", "Fixture additional detail information")
    assert parse_attendance_detail(ancillary.encode()).notes == (
        "Fixture additional detail information",
    )
    invalid = body.replace('colspan="2"', 'colspan="1"')
    with pytest.raises(ParseError):
        parse_attendance_detail(invalid.encode())


@pytest.mark.parametrize(
    "body",
    [
        b"<html></html>",
        b'<div class="container-background"></div>',
        (DETAIL + DETAIL).encode(),
        DETAIL.replace("Temat zajęć:", "Data:").encode(),
        DETAIL.replace("<th>Data:</th>", "").encode(),
    ],
)
def test_detail_rejects_missing_ambiguous_or_partial_fields(body: bytes) -> None:
    with pytest.raises(ParseError):
        parse_attendance_detail(body)


def test_overall_and_subject_policies_have_distinct_denominators() -> None:
    rows = parse_gateway_attendance(gateway_rows())
    overall = summarize_frequency(rows, subject_policy=False)
    subject = summarize_frequency(rows, subject_policy=True)
    assert (overall.attended_count, overall.total_count, overall.excluded_count) == (
        3,
        5,
        0,
    )
    assert overall.ratio == pytest.approx(0.6)
    assert (subject.attended_count, subject.total_count, subject.excluded_count) == (
        2,
        4,
        1,
    )
    assert subject.ratio == pytest.approx(0.5)
    empty = summarize_frequency((), subject_policy=False)
    assert empty.ratio is None and empty.total_count == 0


def test_unknown_type_is_preserved_and_never_fabricates_a_ratio() -> None:
    rows = parse_gateway_attendance(gateway_rows((100, 98765)))
    assert rows[1].type_id == "98765"
    for subject in (True, False):
        result = summarize_frequency(rows, subject_policy=subject)
        assert result.ratio is None
        assert result.unknown_count == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("Semester", 3),
        ("Semester", True),
        ("Date", "2026-02-30"),
        ("Type", {"Id": True}),
        ("Lesson", {"Id": "../1"}),
        ("LessonNo", "second"),
    ],
)
def test_gateway_schema_fails_without_partial_rows(field: str, value: object) -> None:
    payload = json.loads(gateway_rows())
    payload["Attendances"][1][field] = value
    with pytest.raises(ParseError):
        parse_gateway_attendance(json.dumps(payload).encode())


def test_gateway_ids_with_a_letter_prefix_are_counted() -> None:
    # librus-mcp#136: some rows of a parent login carried a non-numeric Id and
    # failed the frequency tools; the ID is opaque, digits or not.
    payload = json.loads(gateway_rows())
    payload["Attendances"][1]["Id"] = "t1"
    payload["Attendances"][2]["Id"] = "t2"
    rows = parse_gateway_attendance(json.dumps(payload).encode())
    assert [row.identifier for row in rows] == ["1", "t1", "t2", "4", "5"]
    assert summarize_frequency(rows, subject_policy=False).total_count == 5


@pytest.mark.parametrize("value", ["", "t 1", "t\u00f31", "t" * 65, "../1\n"])
def test_gateway_ids_outside_printable_ascii_fail(value: str) -> None:
    payload = json.loads(gateway_rows())
    payload["Attendances"][1]["Id"] = value
    with pytest.raises(ParseError):
        parse_gateway_attendance(json.dumps(payload).encode())


def test_gateway_duplicate_ids_fail() -> None:
    payload = json.loads(gateway_rows())
    payload["Attendances"][1]["Id"] = payload["Attendances"][0]["Id"]
    with pytest.raises(ParseError):
        parse_gateway_attendance(json.dumps(payload).encode())


def test_metadata_reference_mismatches_fail_instead_of_cross_subject_mapping() -> None:
    from librus_python_api.attendance_frequency import (
        parse_lesson_subject,
        parse_subject_name,
    )

    for parser, body in (
        (parse_lesson_subject, b'{"Lesson":{"Id":42,"Subject":{"Id":51}}}'),
        (parse_subject_name, b'{"Subject":{"Id":52,"Name":"Fixture subject"}}'),
    ):
        with pytest.raises(ParseError):
            parser(body, "41")


def test_metadata_caches_are_login_scoped_and_invalidated_with_session() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student-a", "parent-a")) as service:
                a, b = service.account("student-a"), service.account("parent-a")
                first, second = await asyncio.gather(
                    a.subject_frequency(), b.subject_frequency()
                )
                assert first.items[0].subject == "Fixture student-a"
                assert second.items[0].subject == "Fixture parent-a"
                assert len(fixture.metadata_requests) == 4
                a._invalidate()
                renewed = await a.subject_frequency()
                assert renewed.items == first.items
                assert (
                    renewed.observation.session_generation
                    > first.observation.session_generation
                )
                assert len(fixture.metadata_requests) == 6

    asyncio.run(scenario())


def test_metadata_ttl_and_result_cache_capacity_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("librus_python_api.service.ACCOUNT_RESULT_CACHE_SIZE", 2)
    monkeypatch.setattr("librus_python_api.service.ATTENDANCE_METADATA_CACHE_SIZE", 1)

    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                for identifier in ("1", "2", "3"):
                    await client.attendance_detail(identifier)
                await client.attendance_detail("1", max_age_seconds=60)
                assert fixture.metadata_requests[-1] == ("detail", "1")
                # Collection maps are independent of the per-reference cache size.
                await client.subject_frequency()
                await client.subject_frequency()
                assert fixture.metadata_requests[-2:] == [
                    ("lessons", "*"),
                    ("subjects", "*"),
                ]
                before = len(fixture.metadata_requests)
                await client.subject_frequency()
                assert len(fixture.metadata_requests) == before
                monkeypatch.setattr(
                    "librus_python_api.service.ATTENDANCE_METADATA_TTL_SECONDS", -1
                )
                await client.subject_frequency()
                assert len(fixture.metadata_requests) == before + 2

    asyncio.run(scenario())


def test_fixed_routes_reject_reference_ids_and_templates_require_numeric_ids() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            transport = service.account("student")._transport
            for operation, identifier in (
                ("identity", "1"),
                ("attendance_detail", None),
                ("attendance_lesson", "../1"),
                # Only the gateway account routes take string identifiers.
                ("attendance_lesson", "FIX-1"),
                ("descriptive_user_info", None),
                ("descriptive_user_info", "FIX/1"),
                ("descriptive_partial_grades", "FIX.1"),
                ("descriptive_partial_grades", "F" * 129),
                ("descriptive_token_info", "FIX-1"),
            ):
                with pytest.raises(InvalidInputError):
                    await transport.request(
                        operation, RequestBudget(), reference_id=identifier
                    )
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


def test_public_detail_frequency_and_metadata_reuse_are_real_http() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                detail = await client.attendance_detail("2468")
                assert detail.detail_id == "2468"
                assert detail.fields[1] == ("Temat zajęć", "Fixture topic")
                assert (
                    await client.attendance_detail("2468", max_age_seconds=60) is detail
                )
                frequency = await client.attendance_frequency()
                assert frequency.first_semester.ratio == pytest.approx(0.6)
                assert frequency.second_semester.ratio is None
                assert frequency.overall.ratio == pytest.approx(0.6)
                subjects = await client.subject_frequency(max_age_seconds=60)
                assert subjects.items[0].subject == "Fixture student"
                assert subjects.items[0].frequency.ratio == pytest.approx(0.5)
                assert fixture.metadata_requests == [
                    ("detail", "2468"),
                    ("lessons", "*"),
                    ("subjects", "*"),
                ]
                again = await client.subject_frequency()
                assert again.items == subjects.items
                assert len(fixture.metadata_requests) == 3
                empty = await client.subject_frequency(
                    date(2026, 10, 2), date(2026, 10, 2)
                )
                assert empty.items == ()
                assert len(fixture.metadata_requests) == 3

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "identifier", ["", "../1", "1?x=y", "1/2", "https://example.invalid/1", True]
)
def test_detail_injection_is_rejected_before_network(identifier: str) -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            with pytest.raises(InvalidInputError):
                await service.account("student").attendance_detail(identifier)
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())


def test_subject_resolution_budget_exhaustion_is_not_partial_success() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                budget = RequestBudget(max_requests=2)
                with pytest.raises(LimitError):
                    await client.subject_frequency(budget=budget)
                assert budget.requests_dispatched == 2
                assert fixture.metadata_requests == [("lessons", "*")]
                # An exhausted caller budget must not be cached as an unusable
                # collection that silently forces per-reference lookups later.
                await client.subject_frequency()
                assert fixture.metadata_requests[-2:] == [
                    ("lessons", "*"),
                    ("subjects", "*"),
                ]

    asyncio.run(scenario())


def test_subject_frequency_recovers_gateway_expiry_once() -> None:
    # It reads through the retry-safe gateway route, unlike view POSTs.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                fixture.gateway_expiry = 1
                result = await client.subject_frequency()
                assert result.items
                assert fixture.logins == {"student": 2}

    asyncio.run(scenario())


def many_subject_rows(count: int) -> bytes:
    return json.dumps(
        {
            "Attendances": [
                {
                    "Id": index + 1,
                    "Date": "2026-10-01",
                    "Semester": 1,
                    "Type": {"Id": 100},
                    "Lesson": {"Id": 1000 + index},
                }
                for index in range(count)
            ]
        }
    ).encode()


def test_subject_frequency_request_count_is_independent_of_subject_count() -> None:
    # Per-reference resolution needed 1 + lessons + subjects requests, which
    # exceeded the default 32-request operation budget near 16 subjects.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.gateway_body = many_subject_rows(60)
        fixture.collection_lessons = {1000 + i: 2000 + i for i in range(60)}
        fixture.collection_subjects = tuple(2000 + i for i in range(60))
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.identity()
                budget = RequestBudget()
                result = await client.subject_frequency(budget=budget)
                assert len(result.items) == 60
                assert {item.subject for item in result.items} == {"Fixture student"}
                assert budget.requests_dispatched == 3

    asyncio.run(scenario())


def test_references_missing_from_collections_resolve_individually() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.collection_lessons = {41: None, 99: 51}
        fixture.collection_subjects = ()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                result = await service.account("student").subject_frequency()
                assert result.items[0].subject == "Fixture student"
                assert fixture.metadata_requests == [
                    ("lessons", "*"),
                    ("lesson", "41"),
                    ("subjects", "*"),
                    ("subject", "51"),
                ]

    asyncio.run(scenario())


def test_malformed_collections_are_read_again_on_the_next_call() -> None:
    # A failed collection read used to be cached as an empty map for the
    # metadata TTL, so every later call paid one request per lesson.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.gateway_body = many_subject_rows(3)
        # Per-reference lessons all name subject 51; the collection names
        # 2000-2002, so the item count shows which source resolved them.
        fixture.collection_lessons = {1000 + i: 2000 + i for i in range(3)}
        fixture.collection_subjects = tuple(2000 + i for i in range(3))
        fixture.malformed_collections = {"lessons": 1, "subjects": 1}
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.subject_frequency()
                assert len(first.items) == 1
                assert fixture.metadata_requests == [
                    ("lessons", "*"),
                    ("lesson", "1000"),
                    ("lesson", "1001"),
                    ("lesson", "1002"),
                    ("subjects", "*"),
                    ("subject", "51"),
                ]
                fixture.metadata_requests.clear()
                second = await client.subject_frequency()
                assert len(second.items) == 3
                assert fixture.metadata_requests == [
                    ("lessons", "*"),
                    ("subjects", "*"),
                ]
                fixture.metadata_requests.clear()
                # Parsed maps keep their TTL.
                third = await client.subject_frequency()
                assert len(third.items) == 3
                assert fixture.metadata_requests == []

    asyncio.run(scenario())


@pytest.mark.parametrize("unavailable", ["status", "conflict"])
def test_unusable_collections_fall_back_to_per_reference_lookups(
    unavailable: str,
) -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        if unavailable == "status":
            fixture.collection_lessons = None
            fixture.collection_subjects = None
        else:
            # Conflicting duplicate rows are a parse failure, never a choice.
            fixture.gateway_body = gateway_rows()
            fixture.collection_subjects = (51, 51)
            fixture.collection_lessons = {41: 51}
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                first = await client.subject_frequency()
                assert first.items[0].subject == "Fixture student"
                await client.subject_frequency()
                requests = fixture.metadata_requests
                if unavailable == "status":
                    # A status failure may be transient: retried, then degraded again.
                    assert requests.count(("lessons", "*")) == 2
                    assert requests.count(("lesson", "41")) == 1
                else:
                    assert requests.count(("subjects", "*")) == 1

    asyncio.run(scenario())


def test_collection_parsers_bound_rows_and_omit_unresolvable_entries() -> None:
    from librus_python_api.attendance_frequency import (
        parse_lesson_subjects,
        parse_subject_names,
    )
    from librus_python_api.config import ATTENDANCE_MAX_LESSONS

    assert parse_lesson_subjects(
        b'{"Lessons":[{"Id":1,"Subject":{"Id":2}},{"Id":3},{"Id":1,"Subject":{"Id":2}}]}'
    ) == {"1": "2"}
    assert parse_subject_names(
        b'{"Subjects":[{"Id":2,"Name":" Fixture "},{"Id":3,"Name":"  "},{"Id":4}]}'
    ) == {"2": "Fixture"}
    for body in (
        b'{"Lessons":[{"Id":1,"Subject":{"Id":2}},{"Id":1,"Subject":{"Id":3}}]}',
        b'{"Lessons":[{"Id":"x"}]}',
        b'{"Lessons":{}}',
        b"[]",
    ):
        with pytest.raises(ParseError):
            parse_lesson_subjects(body)
    oversized = json.dumps(
        {"Lessons": [{"Id": i} for i in range(ATTENDANCE_MAX_LESSONS + 1)]}
    ).encode()
    with pytest.raises(LimitError):
        parse_lesson_subjects(oversized)


def test_result_cache_evicts_the_least_recently_refreshed_entry() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                for identifier in range(1, ACCOUNT_RESULT_CACHE_SIZE + 1):
                    await client.attendance_detail(str(identifier))
                await client.attendance_detail("1")  # refresh the oldest entry
                await client.attendance_detail(str(ACCOUNT_RESULT_CACHE_SIZE + 1))
                before = len(fixture.metadata_requests)
                await client.attendance_detail("1", max_age_seconds=60)
                assert len(fixture.metadata_requests) == before
                # The entry not refreshed since its first read went instead.
                await client.attendance_detail("2", max_age_seconds=60)
                assert fixture.metadata_requests[-1] == ("detail", "2")

    asyncio.run(scenario())


def test_metadata_cache_evicts_the_least_recently_refreshed_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("librus_python_api.service.ATTENDANCE_METADATA_CACHE_SIZE", 2)

    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")

                async def lesson(identifier: str) -> None:
                    await client._metadata_value(
                        "attendance_lesson", identifier, RequestBudget()
                    )

                await lesson("41")
                await lesson("42")
                with monkeypatch.context() as stale:
                    stale.setattr(
                        "librus_python_api.service.ATTENDANCE_METADATA_TTL_SECONDS", -1
                    )
                    await lesson("41")  # refresh the oldest entry
                await lesson("43")
                before = len(fixture.metadata_requests)
                await lesson("41")
                assert len(fixture.metadata_requests) == before
                await lesson("42")
                assert fixture.metadata_requests[-1] == ("lesson", "42")

    asyncio.run(scenario())


def _distinct_lessons(count: int) -> bytes:
    """`count` attendance rows, each in a lesson of its own."""
    return json.dumps(
        {
            "Attendances": [
                {
                    "Id": index + 1,
                    "Date": "2026-10-01",
                    "Semester": 1,
                    "Type": {"Id": 100},
                    "Lesson": {"Id": 1000 + index},
                    "LessonNo": 2,
                }
                for index in range(count)
            ]
        }
    ).encode()


@pytest.mark.parametrize("count", [257, ATTENDANCE_MAX_RECORDS])
def test_subject_counts_cover_every_lesson_the_row_cap_allows(count: int) -> None:
    # #199: more than 256 distinct lessons raised LIMIT although the rows
    # were within the attendance cap; the collections resolve them all.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.gateway_body = _distinct_lessons(count)
        fixture.collection_lessons = {1000 + index: 51 for index in range(count)}
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                result = await service.account("student").subject_frequency()
                assert [item.frequency.total_count for item in result.items] == [count]
                assert fixture.metadata_requests == [
                    ("lessons", "*"),
                    ("subjects", "*"),
                ]

    asyncio.run(scenario())


def test_lookups_past_the_budget_fail_before_any_is_sent() -> None:
    # Without the lessons collection every lesson costs a request: more than
    # the budget allows fails at once instead of after spending it.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.gateway_body = _distinct_lessons(40)
        fixture.collection_lessons = None
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                with pytest.raises(LimitError):
                    await service.account("student").subject_frequency()
                assert fixture.metadata_requests == [("lessons", "*")]

    asyncio.run(scenario())


def test_cached_lookups_are_not_counted_against_the_budget() -> None:
    # Review of #199: lessons the per-reference cache still holds cost no
    # request, so a later call within the default budget must not fail.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.gateway_body = _distinct_lessons(40)
        fixture.collection_lessons = None
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                await client.subject_frequency(budget=RequestBudget(max_requests=100))
                before = len(fixture.metadata_requests)
                result = await client.subject_frequency()
                assert [item.frequency.total_count for item in result.items] == [40]
                # Only the unavailable lessons collection is asked again; the
                # subjects map and every lesson come from the caches.
                assert fixture.metadata_requests[before:] == [("lessons", "*")]

    asyncio.run(scenario())


# A school's own types as the gateway lists them (shape from public client
# sources and a public sample): standard types, then custom ones naming the
# standard type they count as.
SCHOOL_TYPES: list[dict[str, object]] = [
    {"Id": 1, "Standard": True, "IsPresenceKind": False},
    {"Id": 100, "Standard": True, "IsPresenceKind": True},
    {"Id": 1266, "Standard": False, "StandardType": {"Id": 1, "Url": "fixture"}},
    {"Id": 2928, "Standard": False, "StandardType": {"Id": 1, "Url": "fixture"}},
    {"Id": 2930, "Standard": False, "StandardType": {"Id": 100, "Url": "fixture"}},
    {"Id": 2931, "Standard": False, "StandardType": {"Id": 999, "Url": "fixture"}},
    {"Id": 2932, "Standard": False},
]


def test_school_types_take_the_kind_of_their_standard_type() -> None:
    # librus-mcp#136: a type outside the fixed policy made every ratio null.
    from librus_python_api.attendance_frequency import (
        parse_attendance_types,
        resolve_type_kinds,
    )

    kinds = parse_attendance_types(json.dumps({"Types": SCHOOL_TYPES}).encode())
    assert kinds == {"1266": "absence", "2928": "absence", "2930": "present"}
    rows = resolve_type_kinds(
        parse_gateway_attendance(gateway_rows((2928, 2930, 1266, 2931, 2932))), kinds
    )
    # The fixed policy wins: 1266 stays an excursion whatever the list says.
    assert [row.kind for row in rows] == [
        "absence",
        "present",
        "excursion",
        "unknown",
        "unknown",
    ]


def test_conflicting_or_oversized_type_lists_fail_to_parse() -> None:
    from librus_python_api.attendance_frequency import parse_attendance_types

    conflict = [
        {"Id": 2928, "StandardType": {"Id": 1}},
        {"Id": 2928, "StandardType": {"Id": 100}},
    ]
    with pytest.raises(ParseError):
        parse_attendance_types(json.dumps({"Types": conflict}).encode())
    with pytest.raises(LimitError):
        parse_attendance_types(json.dumps({"Types": [{"Id": 1}] * 1025}).encode())


def test_school_types_are_read_once_and_only_when_a_type_is_unknown() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.types = SCHOOL_TYPES
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                known = await client.attendance_frequency()
                assert known.overall.unknown_count == 0
                assert fixture.metadata_requests == []
                fixture.gateway_body = gateway_rows((100, 2930, 2928))
                first = await client.attendance_frequency()
                assert first.overall.unknown_count == 0
                assert (first.overall.attended_count, first.overall.total_count) == (
                    2,
                    3,
                )
                assert first.overall.ratio == pytest.approx(2 / 3)
                by_subject = await client.subject_frequency()
                assert by_subject.items[0].frequency.unknown_count == 0
                # One list read serves both calls for the metadata TTL.
                assert fixture.metadata_requests.count(("types", "*")) == 1

    asyncio.run(scenario())


def test_an_unusable_type_list_leaves_the_rows_unknown() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.types = None
        fixture.gateway_body = gateway_rows((100, 2930))
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                result = await service.account("student").attendance_frequency()
                assert result.overall.unknown_count == 1
                assert result.overall.ratio is None
                assert fixture.metadata_requests == [("types", "*")]

    asyncio.run(scenario())


def _two_lesson_rows() -> bytes:
    payload = json.loads(gateway_rows((100, 1, 100, 2)))
    for row in payload["Attendances"][2:]:
        row["Lesson"] = {"Id": 42}
    return json.dumps(payload).encode()


@pytest.mark.parametrize("missing", ["lesson", "subject"])
def test_an_unresolvable_reference_is_counted_apart_not_fatal(missing: str) -> None:
    # Librus may not give a lesson or subject an attendance record names; that
    # failed the whole subject frequency read before.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.gateway_body = _two_lesson_rows()
        fixture.collection_lessons = {41: 51}
        fixture.collection_subjects = (51,)
        if missing == "lesson":
            fixture.missing_lessons = {"42": 404}
        else:
            # Lesson 42 resolves individually to subject 51 of the fixture, so
            # give it a subject of its own that the subject route lacks.
            fixture.collection_lessons = {41: 51, 42: 52}
            fixture.missing_subjects = {"52": 404}
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                result = await service.account("student").subject_frequency()
                (item,) = result.items
                assert item.subject_id == "51"
                assert (item.frequency.attended_count, item.frequency.total_count) == (
                    1,
                    2,
                )
                unresolved = result.unresolved
                assert unresolved is not None
                assert (unresolved.attended_count, unresolved.total_count) == (2, 2)
                assert unresolved.policy == "subject"

    asyncio.run(scenario())


def test_every_reference_resolved_leaves_no_unresolved_measure() -> None:
    async def scenario() -> None:
        fixture = FrequencyFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                result = await service.account("student").subject_frequency()
                assert result.items and result.unresolved is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, SessionExpiredError),
        (429, ThrottledError),
        (503, MaintenanceError),
    ],
)
@pytest.mark.parametrize("missing", ["lesson", "subject"])
def test_a_lookup_failing_for_the_session_or_service_still_fails(
    missing: str, status: int, error: type[Exception]
) -> None:
    # Only a reference Librus does not give is counted apart; an expired
    # session, throttling or maintenance is no answer about that reference.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.gateway_body = _two_lesson_rows()
        if missing == "lesson":
            fixture.missing_lessons = {"42": status}
        else:
            fixture.collection_lessons = {41: 51, 42: 52}
            fixture.missing_subjects = {"52": status}
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                with pytest.raises(error):
                    await service.account("student").subject_frequency()

    asyncio.run(scenario())


def test_nothing_resolved_fails_with_the_lookup_error() -> None:
    # Every lookup failing is a failing route, not missing references; an
    # all-unresolved success would hide it and could be cached.
    async def scenario() -> None:
        fixture = FrequencyFixture()
        fixture.collection_lessons = None
        fixture.missing_lessons = {"41": 404}
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                with pytest.raises(ConnectionError):
                    await service.account("student").subject_frequency()

    asyncio.run(scenario())
