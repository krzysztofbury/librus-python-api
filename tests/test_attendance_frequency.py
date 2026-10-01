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
from librus_python_api.exceptions import InvalidInputError, LimitError, ParseError
from tests.attendance_support import AttendanceFixture
from tests.http_support import serve


def gateway_rows(types: tuple[int, ...] = (1, 2, 100, 1266, 3)) -> bytes:
    return json.dumps(
        {
            "Attendances": [
                {
                    "Id": index + 1,
                    "Date": "2026-10-01",
                    "Semester": 1,
                    "Type": {"Id": kind},
                    "Lesson": {"Id": 41},
                    "LessonNo": 2,
                }
                for index, kind in enumerate(types)
            ]
        }
    ).encode()


DETAIL = (
    '<div class="container-background"><table>'
    '<tr class="line0"><th>Data:</th><td>2026-10-01</td></tr>'
    '<tr class="line1"><th>Temat zajęć:</th><td>Fixture<br>topic</td></tr>'
    "</table></div>"
)


class FrequencyFixture(AttendanceFixture):
    def __init__(self) -> None:
        super().__init__()
        self.gateway_body = gateway_rows()
        self.detail_body = DETAIL
        self.metadata_requests: list[tuple[str, str]] = []

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_get("/przegladaj_nb/szczegoly/{id}", self.detail)
        app.router.add_get("/gateway/api/2.0/Attendances", self.gateway)
        app.router.add_get("/gateway/api/2.0/Lessons/{id}", self.lesson)
        app.router.add_get("/gateway/api/2.0/Subjects/{id}", self.subject)
        return app

    async def gateway(self, request: web.Request) -> web.Response:
        self.record(request)
        return web.Response(body=self.gateway_body, content_type="application/json")

    async def detail(self, request: web.Request) -> web.Response:
        self.record(request)
        self.metadata_requests.append(("detail", request.match_info["id"]))
        return web.Response(text=self.detail_body, content_type="text/html")

    async def lesson(self, request: web.Request) -> web.Response:
        self.record(request)
        self.metadata_requests.append(("lesson", request.match_info["id"]))
        return web.json_response(
            {"Lesson": {"Id": int(request.match_info["id"]), "Subject": {"Id": 51}}}
        )

    async def subject(self, request: web.Request) -> web.Response:
        login = self.record(request)
        self.metadata_requests.append(("subject", request.match_info["id"]))
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
    monkeypatch.setattr("librus_python_api.service.ATTENDANCE_RESULT_CACHE_SIZE", 2)
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
                await client.subject_frequency()
                await client.subject_frequency()
                assert fixture.metadata_requests[-4:] == [
                    ("lesson", "41"),
                    ("subject", "51"),
                    ("lesson", "41"),
                    ("subject", "51"),
                ]
                monkeypatch.setattr(
                    "librus_python_api.service.ATTENDANCE_METADATA_CACHE_SIZE", 256
                )
                await client.subject_frequency()
                monkeypatch.setattr(
                    "librus_python_api.service.ATTENDANCE_METADATA_TTL_SECONDS", -1
                )
                before = len(fixture.metadata_requests)
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
                    ("lesson", "41"),
                    ("subject", "51"),
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
                assert fixture.metadata_requests == [("lesson", "41")]

    asyncio.run(scenario())
