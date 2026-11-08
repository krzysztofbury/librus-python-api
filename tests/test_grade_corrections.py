"""Grade IDs and correction brackets (librus-mcp#88).

Fixtures are original. They follow a masked, structure-only observation of
owner logins (2026-11-08): in the all view a bare <span> directly in the grade
cell holds "[", the corrected grade's box, the correction's box and then "]"
as the last box's tail; only the correction's tooltip has a `Poprawa oceny`
line. The week view showed no brackets.
"""

import asyncio
from dataclasses import fields
from datetime import date

import pytest

from librus_python_api import GradeCorrection, GradeRecords, NumericGrade
from librus_python_api.exceptions import ParseError
from librus_python_api.grade_records import parse_grade_records
from tests.grade_records_support import (
    FORMATIVE_LINK,
    GradeRecordsFixture,
    grade_box,
    grades_html,
    point_box,
    point_row,
    point_table,
)
from tests.http_support import serve

LINK = "/przegladaj_oceny/szczegoly/{}"
CORRECTION = (
    "Licz do średniej: tak<br/>Dodał: Fixture Teacher<br/><br/>"
    "Poprawa oceny: 1 (Fixture quiz)"
)


def box(raw: str, grade: str, day: str = "2026-09-30", extra: str = "") -> str:
    return grade_box(
        raw, day, extra=extra or "Licz do średniej: tak", href=LINK.format(grade)
    )


def bracket(*boxes: str) -> str:
    """The observed layout, with the whitespace a rendered page carries."""
    inner = "\n  ".join(boxes)
    return f"<span>\n  [\n  {inner}\n  ]\n</span>"


def corrected(original: str = "11", correction: str = "12") -> str:
    return bracket(
        box("1", original),
        box("5", correction, "2026-10-07", CORRECTION),
    )


def records(first: str, second: str = "") -> GradeRecords:
    return parse_grade_records(grades_html(first=first, second=second).encode())


def test_a_bracket_links_the_correction_to_the_grade_it_corrects() -> None:
    result = records(box("4", "10") + corrected() + box("3", "13"))
    assert [grade.grade_id for grade in result.numeric] == ["10", "11", "12", "13"]
    assert result.corrections == (GradeCorrection("Fixture Language", 1, ("11", "12")),)
    # Both grades stay ordinary records with their own tooltips.
    original, correction = result.numeric[1:3]
    assert "Poprawa oceny" not in dict(original.metadata)
    assert dict(correction.metadata)["Poprawa oceny"] == "1 (Fixture quiz)"


def test_each_semester_and_group_is_its_own_correction() -> None:
    result = records(
        corrected("11", "12") + corrected("21", "22"), second=corrected("31", "32")
    )
    assert [(c.semester, c.grade_ids) for c in result.corrections] == [
        (1, ("11", "12")),
        (1, ("21", "22")),
        (2, ("31", "32")),
    ]


def test_a_chain_of_corrections_keeps_page_order() -> None:
    chain = bracket(box("1", "11"), box("2", "12", extra=CORRECTION), box("4", "13"))
    (group,) = records(chain).corrections
    assert group.grade_ids == ("11", "12", "13")


def test_a_correction_without_a_bracket_has_no_link() -> None:
    # The week view: the correction, maybe its original, no bracket.
    result = records(box("1", "11") + box("5", "12", extra=CORRECTION))
    assert result.corrections == ()
    assert [grade.grade_id for grade in result.numeric] == ["11", "12"]


@pytest.mark.parametrize(
    "cell",
    [
        corrected().replace("[", "[<!-- fixture -->", 1),
        corrected().replace("\n  ]", "<!-- fixture -->\n  ]", 1),
    ],
    ids=["after-open", "before-close"],
)
def test_a_comment_inside_a_bracket_is_not_a_grade(cell: str) -> None:
    (group,) = records(cell).corrections
    assert group.grade_ids == ("11", "12")


def test_a_period_correction_shown_by_both_tables_is_one_link() -> None:
    # Period grades shown by the ordinary and the point table are one record.
    page = grades_html(
        extra=point_table(point_row(subject="Fixture Language", node="72"))
    ).replace("<td>4,25</td><td>-</td>", "<td>4,25</td><td>" + corrected() + "</td>")
    point_midterm = '<td class="center"> - </td><td>Brak ocen</td>'
    assert page.count(point_midterm) == 1
    page = page.replace(
        point_midterm, f'<td class="center">{corrected()}</td><td>Brak ocen</td>'
    )
    result = parse_grade_records(page.encode())
    assert [c.grade_ids for c in result.corrections] == [("11", "12")]
    assert [g.grade_id for g in result.numeric if g.grade_id] == ["11", "12"]


def test_a_new_bracket_in_the_point_tables_period_column_fails() -> None:
    # Not a repeat of an ordinary-table bracket, and never observed there.
    page = grades_html(extra=point_table(point_row(node="72")))
    point_midterm = '<td class="center"> - </td><td>Brak ocen</td>'
    page = page.replace(
        point_midterm,
        f'<td class="center">{corrected("91", "92")}</td><td>Brak ocen</td>',
    )
    with pytest.raises(ParseError):
        parse_grade_records(page.encode())


def test_brackets_are_markup_not_grade_text() -> None:
    # A bracket inside a grade's own tooltip or symbol is not a correction.
    inside = grade_box("[5]", extra="Komentarz: see [1]", href=LINK.format("11")) + box(
        "4", "12"
    )
    result = records(inside)
    assert result.corrections == ()
    assert [grade.raw for grade in result.numeric] == ["[5]", "4"]


@pytest.mark.parametrize(
    "cell",
    [
        pytest.param(
            "<span>[" + box("1", "11") + box("5", "12") + "</span>", id="open"
        ),
        pytest.param(box("1", "11") + box("5", "12") + "]", id="stray-close"),
        pytest.param("[" + box("1", "11") + box("5", "12") + "]", id="no-wrapper"),
        pytest.param(bracket(box("1", "11")), id="single-box"),
        pytest.param(
            bracket(box("1", "11"), bracket(box("2", "12"), box("4", "13"))),
            id="nested",
        ),
        pytest.param(
            corrected().replace("<span>", '<span class="fixture">', 1), id="attribute"
        ),
        pytest.param(
            "<span>[" + box("1", "11") + "]" + box("5", "12") + "</span>",
            id="close-early",
        ),
        pytest.param("<div>" + corrected() + "</div>", id="not-in-the-cell"),
        pytest.param(
            bracket(box("1", "11"), box("5", "11", extra=CORRECTION)), id="same-grade"
        ),
        pytest.param(corrected("11", "12") + corrected("12", "13"), id="shared-grade"),
        pytest.param(corrected("11", "12") + corrected("11", "12"), id="repeated"),
        pytest.param(
            corrected().replace("</span>\n  <span", "</span><!-- c --> x <span", 1),
            id="text-after-comment",
        ),
        pytest.param(
            bracket(
                box("1", "11"),
                grade_box("5", href=FORMATIVE_LINK.format("12")),
            ),
            id="formative-member",
        ),
        pytest.param(
            bracket(box("1", "11"), grade_box("5", href="fixture-link")),
            id="unlinked-member",
        ),
    ],
)
def test_an_unseen_bracket_layout_fails_instead_of_dropping_the_link(
    cell: str,
) -> None:
    with pytest.raises(ParseError):
        records(cell)


def test_a_bracket_in_the_point_table_fails() -> None:
    first = bracket(point_box(), point_box("44", "7002", "2026-10-12 (pon.)"))
    page = grades_html(extra=point_table(point_row(first)))
    with pytest.raises(ParseError):
        parse_grade_records(page.encode())


@pytest.mark.parametrize(
    "href,grade,formative,point",
    [
        (LINK.format("2222222"), "2222222", None, None),
        (FORMATIVE_LINK.format("961"), None, "961", None),
        ("/przegladaj_oceny_punktowe/szczegoly/7001", None, None, "7001"),
        (LINK.format("12") + "?x=1", None, None, None),
        ("https://elsewhere.example" + LINK.format("12"), None, None, None),
        (None, None, None, None),
    ],
)
def test_one_link_gives_at_most_one_kind_of_id(
    href: str | None, grade: str | None, formative: str | None, point: str | None
) -> None:
    record = NumericGrade(
        "Fixture", "4", date(2026, 9, 30), 1, None, None, None, None, None, href, ()
    )
    assert (record.grade_id, record.formative_id, record.point_grade_id) == (
        grade,
        formative,
        point,
    )


def test_grade_id_is_computed_so_notification_identities_stay_unchanged() -> None:
    assert "grade_id" not in {field.name for field in fields(NumericGrade)}
    assert "corrections" not in {field.name for field in fields(NumericGrade)}


def test_a_window_keeps_each_correction_with_a_grade_inside_it() -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.grade_body = grades_html(first=corrected() + box("4", "13"))
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                whole = await client.grades_window()
                assert [c.grade_ids for c in whole.corrections] == [("11", "12")]
                # Only the correction is in the window; the link stays whole.
                later = await client.grades_window(
                    start=date(2026, 10, 1), max_age_seconds=60
                )
                assert [g.grade_id for g in later.numeric] == ["12"]
                assert [c.grade_ids for c in later.corrections] == [("11", "12")]
                before = await client.grades_window(
                    end=date(2026, 9, 1), max_age_seconds=60
                )
                assert before.numeric == () and before.corrections == ()

    asyncio.run(scenario())
