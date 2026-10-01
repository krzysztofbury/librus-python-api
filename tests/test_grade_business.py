"""Original grade business-flow regressions, independently authored examples."""

import asyncio
from datetime import date

import pytest

from librus_python_api import Availability, GradeKind, GradeView
from librus_python_api.exceptions import InvalidInputError, ParseError
from librus_python_api.grade_records import parse_grade_records
from tests.grade_records_support import GradeRecordsFixture, grade_box, grades_html
from tests.http_support import serve


def descriptive_html() -> str:
    return (
        '<html><body><table class="decorated stretch"><tbody>'
        '<tr><td class="screen-only micro center"></td><td>Fixture Arts</td>'
        "<td>"
        + grade_box("Progress in reading", descriptive=True)
        + "</td><td>"
        + grade_box("Progress in writing", "2027-02-03", descriptive=True)
        + "</td><td>-</td><td>-</td></tr></tbody></table></body></html>"
    )


def publication_html(period: str = "") -> str:
    return (
        "<table><tbody><tr><th><strong>Fixture report " + period + "</strong>"
        " (opublikowano: 2027-01-14 10:20, nauczyciel: Fixture Teacher)</th></tr>"
        "<tr><td><p>First independent paragraph.</p><p>Second paragraph.</p></td></tr>"
        "</tbody></table>"
    )


def test_dated_period_and_annual_marks_retain_metadata_without_undated_invention() -> (
    None
):
    body = (
        grades_html(first="")
        .replace(
            "<td>4,25</td><td>-</td>",
            "<td>4,25</td><td>" + grade_box("5", extra="") + "</td>",
        )
        .replace(
            "<td>-</td><td>-</td></tr>",
            "<td>-</td><td>" + grade_box("6", extra="") + "</td></tr>",
        )
    )
    records = parse_grade_records(body.encode())
    assert [(g.raw, g.semester, g.kind) for g in records.numeric] == [
        ("5", 1, GradeKind.PERIOD),
        ("6", 0, GradeKind.ANNUAL),
    ]
    assert all(g.teacher == "Fixture Teacher" for g in records.numeric)
    assert all(g.counts_toward_average is None for g in records.numeric)


def test_dated_predicted_annual_mark_is_not_silently_dropped() -> None:
    body = grades_html(first="").replace(
        "<td></td><td>-</td>\n    <td>-</td><td>-</td></tr>",
        "<td></td><td>"
        + grade_box("5", extra="")
        + "</td>\n    <td>-</td><td>-</td></tr>",
    )
    (grade,) = parse_grade_records(body.encode()).numeric
    assert (grade.kind, grade.semester, grade.raw) == (
        GradeKind.PREDICTED_ANNUAL,
        0,
        "5",
    )


def test_nested_correction_spans_keep_each_dated_mark_once() -> None:
    first = '<span class="fixture-correction">' + grade_box("2") + "</span>"
    second = "<span>" + grade_box("4", "2026-10-01") + "</span>"
    records = parse_grade_records(grades_html(first=first + second).encode())
    assert [(g.raw, g.day) for g in records.numeric] == [
        ("2", date(2026, 9, 30)),
        ("4", date(2026, 10, 1)),
    ]


@pytest.mark.parametrize("semester", [1, 2])
def test_dated_predicted_period_marks_preserve_their_explicit_semester(
    semester: int,
) -> None:
    header = (
        "Przewidywana ocena śródroczna z "
        + ("pierwszego" if semester == 1 else "drugiego")
        + " okresu"
    )
    body = (
        grades_html(first="")
        .replace("Ocena śródroczna z pierwszego okresu", header)
        .replace(
            "<td>4,25</td><td>-</td>",
            "<td>4,25</td><td>" + grade_box("4", extra="") + "</td>",
        )
    )
    (grade,) = parse_grade_records(body.encode()).numeric
    assert (grade.kind, grade.semester) == (GradeKind.PREDICTED_PERIOD, semester)


def test_descriptive_only_subjects_have_two_semesters_and_no_invented_average() -> None:
    records = parse_grade_records(descriptive_html().encode())
    assert not records.numeric
    assert [(g.raw, g.semester) for g in records.descriptive] == [
        ("Progress in reading", 1),
        ("Progress in writing", 2),
    ]
    assert all(g.subject == "Fixture Arts" for g in records.descriptive)
    assert all(
        a.value.availability == Availability.UNAVAILABLE for a in records.averages
    )


def test_undated_descriptive_semester_text_is_a_summary_not_a_dated_grade() -> None:
    body = descriptive_html().replace(
        grade_box("Progress in reading", descriptive=True), "Independent semester text"
    )
    records = parse_grade_records(body.encode())
    assert len(records.descriptive) == 1
    (summary,) = records.descriptive_summaries
    assert (summary.subject, summary.semester, summary.raw) == (
        "Fixture Arts",
        1,
        "Independent semester text",
    )
    assert "Independent semester text" not in repr(summary)


def test_overlapping_grade_families_do_not_duplicate_subject_averages() -> None:
    extra = descriptive_html().replace("Fixture Arts", "Fixture Language")
    body = grades_html().replace(
        "</body>", extra.split("<body>")[1].split("</body>")[0] + "</body>"
    )
    records = parse_grade_records(body.encode())
    assert len(records.numeric) == 1
    assert len(records.descriptive) == 2
    assert len(records.averages) == 3
    assert records.averages[0].value.raw == "4,25"


def test_nested_descriptive_anchors_keep_metadata_and_discard_script_links() -> None:
    body = descriptive_html().replace(
        grade_box("Progress in reading", descriptive=True),
        "<table><tr><td>"
        + grade_box("Progress in reading").replace(
            'href="fixture-link"', 'href="javascript:displayFixture()"'
        )
        + "</td></tr></table>",
    )
    records = parse_grade_records(body.encode())
    assert records.descriptive[0].raw == "Progress in reading"
    assert records.descriptive[0].href is None


def test_malformed_descriptive_only_row_is_not_omitted_from_numeric_results() -> None:
    extra = descriptive_html().replace("<td>-</td><td>-</td>", "<td>-</td>")
    extra = extra.replace(grade_box("Progress in reading", descriptive=True), "")
    extra = extra.replace(
        grade_box("Progress in writing", "2027-02-03", descriptive=True), ""
    )
    body = grades_html().replace(
        "</body>", extra.split("<body>")[1].split("</body>")[0] + "</body>"
    )
    with pytest.raises(ParseError):
        parse_grade_records(body.encode())


@pytest.mark.parametrize(
    "period,semester", [("", None), ("pierwszy okres", 1), ("drugi okres", 2)]
)
def test_multiple_publications_preserve_paragraphs_and_only_explicit_semesters(
    period: str, semester: int | None
) -> None:
    body = grades_html().replace("</body>", publication_html(period) + "</body>")
    records = parse_grade_records(body.encode())
    (entry,) = records.descriptive
    assert entry.kind == GradeKind.PUBLICATION
    assert entry.semester == semester
    assert entry.day == date(2027, 1, 14)
    assert entry.teacher == "Fixture Teacher"
    assert entry.raw == "First independent paragraph.\nSecond paragraph."
    both = parse_grade_records(
        body.replace("</body>", publication_html("drugi okres") + "</body>").encode()
    )
    assert len(both.descriptive) == 2


def test_publication_wrong_or_missing_date_is_not_ignored() -> None:
    body = grades_html().replace(
        "</body>", publication_html().replace("2027-01-14", "2027-02-30") + "</body>"
    )
    with pytest.raises(ParseError):
        parse_grade_records(body.encode())


def test_publication_inside_subject_table_is_not_a_malformed_subject() -> None:
    rows = publication_html("drugi okres").split("<tbody>")[1].split("</tbody>")[0]
    records = parse_grade_records(
        grades_html().replace("</tbody>", rows + "</tbody>").encode()
    )
    assert records.numeric[0].subject == "Fixture Language"
    assert records.descriptive[0].semester == 2


def test_upstream_filters_are_isolated_and_windows_always_use_all_view() -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        descriptions = descriptive_html().replace(
            grade_box("Progress in reading", descriptive=True),
            "Independent semester text",
        )
        fixture.grade_body = grades_html().replace(
            "</body>", descriptions.split("<body>")[1].split("</body>")[0] + "</body>"
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                all_grades, week, last = await asyncio.gather(
                    client.grades(),
                    client.grades(view=GradeView.WEEK),
                    client.grades(view=GradeView.LAST_LOGIN),
                )
                assert all_grades.view == GradeView.ALL
                assert week.view == GradeView.WEEK
                assert last.view == GradeView.LAST_LOGIN
                assert len(fixture.view_posts) == 3
                assert await client.grades(max_age_seconds=60) is all_grades
                assert (
                    await client.grades(view=GradeView.WEEK, max_age_seconds=60) is week
                )
                assert (
                    await client.grades(view=GradeView.LAST_LOGIN, max_age_seconds=60)
                    is last
                )
                window = await client.grades_window(
                    date(2026, 9, 30), date(2026, 9, 30), max_age_seconds=60
                )
                assert window.numeric == all_grades.records.numeric
                assert all_grades.records.descriptive_summaries
                assert not window.descriptive
                assert len(fixture.view_posts) == 3
                assert {next(iter(form)) for _, form in fixture.view_posts} == {
                    "zmiany_logowanie_wszystkie",
                    "zmiany_logowanie_tydzien",
                    "zmiany_logowanie",
                }

    asyncio.run(scenario())


def test_unknown_grade_filter_is_rejected_before_login() -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.origin = "http://localhost:8080"
        async with fixture.service() as service:
            with pytest.raises(InvalidInputError):
                await service.account("student").grades(view="week")  # type: ignore[arg-type]
            assert service.snapshot().requests_dispatched == 0

    asyncio.run(scenario())
