"""Stable detail keys from original markup through the public HTTP read boundary."""

import asyncio
from html import escape

import pytest

from librus_python_api import AttendanceDetail, SchoolDetail
from librus_python_api.exceptions import ParseError
from tests.http_support import serve
from tests.reads_support import ReadsFixture, read


def detail_body(fields: tuple[tuple[str, str], ...]) -> bytes:
    rows = "".join(
        f'<tr class="line0"><th>{escape(label)}</th><td>{escape(value)}</td></tr>'
        for label, value in fields
    )
    return (
        '<html><div class="container-background"><table>'
        + rows
        + '<tr class="line1"><td colspan="2">Fixture ancillary note</td></tr>'
        + "</table></div></html>"
    ).encode()


@pytest.mark.parametrize("label", ["Data", "Fixture extension"])
def test_attendance_detail_rejects_ambiguous_case_and_colon_variants(
    label: str,
) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        fixture.bodies["attendance_detail"] = (
            detail_body(
                ((label + ":", "2026-10-01"), (label.upper() + " :", "2026-10-02"))
            ),
            "text/html",
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student",)) as service:
                with pytest.raises(ParseError) as caught:
                    await service.account("student").attendance_detail("2468")
                assert caught.value.__context__ is None
                assert fixture.count("attendance_detail") == 1
                fixture.bodies["attendance_detail"] = (
                    detail_body((("Data:", "2026-10-03"),)),
                    "text/html",
                )
                # Failed normalization cannot publish a cache entry.
                result = await service.account("student").attendance_detail(
                    "2468", max_age_seconds=60
                )
                assert result.normalized_fields[0].value == "2026-10-03"
                assert fixture.count("attendance_detail") == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation,fields,keys",
    [
        (
            "agenda_detail",
            (
                (" DATA :", "2026-10-01 (czw.)"),
                ("Nr lekcji", "2"),
                ("Nauczyciel", "Fixture teacher"),
                ("Rodzaj", "Fixture event type"),
                ("Przedmiot", "Fixture subject"),
                ("Sala", ""),
                ("Opis:", "Fixture: complete description"),
                ("Data dodania", "2026-09-20 09:30"),
                ("Fixture extension", "Fixture extra"),
                ("Fixture second extension", "Fixture extra"),
            ),
            [
                "date",
                "lesson_number",
                "teacher",
                "category",
                "subject",
                "room",
                "description",
                "published_at",
                None,
                None,
            ],
        ),
        (
            "homework_detail",
            (
                ("Zajęcia edukacyjne", "Fixture subject"),
                ("Temat", "Fixture topic"),
                ("Kategoria", "Fixture category"),
                ("Data udostępnienia", "2026-09-20 09:30"),
                ("Termin wykonania", "2026-10-01"),
                ("Treść", "Fixture full content"),
                # A recognized agenda label is not necessarily a homework field.
                ("Data", "Fixture unknown date meaning"),
            ),
            ["subject", "topic", "category", "published_at", "due_at", "content", None],
        ),
        (
            "attendance_detail",
            (
                ("Data:", "2026-10-01"),
                ("Temat zajęć:", "Fixture topic"),
                ("Fixture extension", ""),
            ),
            ["date", "topic", None],
        ),
    ],
)
def test_details_expose_stable_keys_without_losing_raw_values(
    operation: str,
    fields: tuple[tuple[str, str], ...],
    keys: list[str | None],
) -> None:
    async def scenario() -> None:
        fixture = ReadsFixture()
        fixture.bodies[operation] = (detail_body(fields), "text/html")
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(("student", "parent")) as service:
                results = await asyncio.gather(
                    *(
                        read(service.account(alias), alias, operation)()
                        for alias in ("student", "parent")
                    )
                )
                for alias, result in zip(("student", "parent"), results, strict=True):
                    assert result.identity.owner.id == alias
                    assert [field.key for field in result.normalized_fields] == keys
                    assert [field.value for field in result.normalized_fields] == [
                        value for _, value in fields
                    ]
                    assert [
                        (field.raw_label, field.value)
                        for field in result.normalized_fields
                    ] == list(result.fields)
                    assert result.notes == ("Fixture ancillary note",)
                    # Existing callers can still construct/compare raw detail DTOs.
                    original: SchoolDetail | AttendanceDetail
                    if isinstance(result, SchoolDetail):
                        original = SchoolDetail(
                            result.identity,
                            result.reference,
                            result.title,
                            result.fields,
                            result.notes,
                            result.observation,
                        )
                    else:
                        original = AttendanceDetail(
                            result.identity,
                            result.detail_id,
                            result.fields,
                            result.notes,
                            result.observation,
                        )
                    assert original.normalized_fields == ()
                    assert original == result
                    assert hash(original) == hash(result)
                    assert "Fixture" not in repr(result.normalized_fields)
                    assert (
                        await read(service.account(alias), alias, operation)(
                            max_age_seconds=60
                        )
                        == result
                    )
                    assert fixture.count(operation, alias) == 1

    asyncio.run(scenario())
