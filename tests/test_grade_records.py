import asyncio
from datetime import date
from html import escape

import pytest

from librus_python_api import (
    Availability,
    BehaviourPointEntry,
    BehaviourPoints,
    GradeKind,
    GradeView,
)
from librus_python_api.config import GRADE_MAX_METADATA_LENGTH, GRADE_MAX_RECORDS
from librus_python_api.exceptions import (
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.grade_records import parse_grade_records
from tests.grade_records_support import (
    BEHAVIOUR_TOOLTIP,
    FORMATIVE_LINK,
    GradeRecordsFixture,
    behaviour_box,
    behaviour_grade_box,
    behaviour_points,
    behaviour_row,
    grade_box,
    grades_html,
    observed_point_page,
    point_box,
    point_row,
    point_table,
)
from tests.http_support import serve


@pytest.mark.parametrize(
    "day,expected",
    [
        ("2026-09-30", "2026-09-30"),
        ("2026-09-30 (śr.)", "2026-09-30"),
        ("2026-10-04 (nd.)", "2026-10-04"),
        ("2026-10-04 (ndz.)", "2026-10-04"),
    ],
)
def test_grade_date_is_a_civil_date_with_optional_display_weekday(
    day: str, expected: str
) -> None:
    # The short Sunday label was observed in a guarded structure-only capture.
    result = parse_grade_records(grades_html(first=grade_box(day=day)).encode())
    (grade,) = result.numeric
    assert grade.day.isoformat() == expected
    assert dict(grade.metadata)["Data"] == day


@pytest.mark.parametrize(
    "day", ["2026-02-30", "2026-09-30 (unknown)", "2026-09-30 12:00", ""]
)
def test_invalid_or_unevidenced_grade_date_is_not_silently_skipped(day: str) -> None:
    with pytest.raises(ParseError) as caught:
        parse_grade_records(grades_html(first=grade_box(day=day)).encode())
    assert caught.value.__context__ is None


def _with_behaviour(first: str | None = None, second: str | None = None) -> bytes:
    return grades_html(rows=behaviour_row(first, second)).encode()


def test_behaviour_starting_points_are_not_a_malformed_grade_cell() -> None:
    records = parse_grade_records(
        _with_behaviour(behaviour_points(), behaviour_points())
    )
    other = parse_grade_records(
        _with_behaviour(behaviour_points("45"), behaviour_points("0"))
    )
    # Only the tallies differ; grades and averages do not depend on them.
    assert (records.numeric, records.averages) == (other.numeric, other.averages)
    assert [(p.semester, p.tally) for p in other.behaviour_points] == [(1, 45), (2, 0)]
    assert [g.subject for g in records.numeric] == ["Fixture Language"]
    assert [
        (a.semester, a.value.availability)
        for a in records.averages
        if a.subject == "Zachowanie"
    ] == [
        (1, Availability.UNAVAILABLE),
        (2, Availability.UNAVAILABLE),
        (0, Availability.AVAILABLE),
    ]


def test_behaviour_running_total_alone_is_not_a_malformed_grade_cell() -> None:
    total = '<span class="tooltip" title="Fixture points history"> {} </span>'
    records = parse_grade_records(
        _with_behaviour(total.format("120"), total.format("-15"))
    )
    assert [g.subject for g in records.numeric] == ["Fixture Language"]
    assert records.descriptive == ()
    assert records.descriptive_summaries == ()


def test_behaviour_point_entries_are_recognized_but_never_reported_as_grades() -> None:
    boxes = behaviour_box() + behaviour_box("-2", "902")
    records = parse_grade_records(_with_behaviour(behaviour_points(boxes=boxes), "-"))
    assert [g.subject for g in records.numeric] == ["Fixture Language"]
    assert records.descriptive == ()


def test_behaviour_points_are_a_typed_value_beside_the_grades() -> None:
    boxes = behaviour_box("+5", "11") + behaviour_box("-3", "12")
    records = parse_grade_records(
        _with_behaviour(behaviour_points("50", boxes), behaviour_points("-7"))
    )
    remark = (
        ("Zakres od", "1"),
        ("Zakres do", "5"),
        ("Data wystawienia", "2026-09-21"),
        ("Dodał", "Teacher Fixture"),
        ("Komentarz", "Fixture remark"),
    )
    assert records.behaviour_points == (
        BehaviourPoints(
            1,
            50,
            (
                BehaviourPointEntry(
                    5, "11", "fixture points category(+5)", date(2026, 9, 21), remark
                ),
                BehaviourPointEntry(
                    -3, "12", "fixture points category(-3)", date(2026, 9, 21), remark
                ),
            ),
        ),
        BehaviourPoints(2, -7, ()),
    )
    # The page's grades are the same as with plain behaviour cells, so the
    # notification identities built from them do not change either.
    plain = parse_grade_records(_with_behaviour("-", "-"))
    assert plain.behaviour_points == ()
    assert (records.numeric, records.descriptive, records.averages) == (
        plain.numeric,
        plain.descriptive,
        plain.averages,
    )
    assert parse_grade_records(grades_html().encode()).behaviour_points == ()


def test_behaviour_points_keep_school_text_out_of_reprs() -> None:
    (item,) = parse_grade_records(
        _with_behaviour(behaviour_points(boxes=behaviour_box()), "-")
    ).behaviour_points
    assert "Teacher Fixture" not in repr(item)
    assert "fixture points category" not in repr(item)


def test_a_tally_alone_is_an_item_without_entries() -> None:
    total = '<span class="tooltip" title="Fixture points history"> {} </span>'
    records = parse_grade_records(_with_behaviour(total.format("120"), "-"))
    assert records.behaviour_points == (BehaviourPoints(1, 120, ()),)


def test_a_tally_in_a_cell_spanning_both_periods_fails() -> None:
    # Its period would be a guess; no page was seen with it.
    row = (
        '<tr><td class="center micro screen-only"></td><td>Zachowanie</td>'
        f'<td colspan="5">{behaviour_points()}</td><td>-</td><td>-</td><td>-</td></tr>'
    )
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(rows=row).encode())


@pytest.mark.parametrize(
    "tooltip",
    [
        # A label outside the observed set.
        BEHAVIOUR_TOOLTIP + "<br/>Kategoria: Fixture",
        BEHAVIOUR_TOOLTIP.replace("Zakres od", "Zakres"),
        # A missing first line: the tooltip opens with a label.
        BEHAVIOUR_TOOLTIP.partition("<br/>")[2],
        "Dodał: Teacher Fixture<br/>" + BEHAVIOUR_TOOLTIP.partition("<br/>")[2],
        # A missing or malformed date.
        BEHAVIOUR_TOOLTIP.replace("<br />Data wystawienia: 2026-09-21", ""),
        BEHAVIOUR_TOOLTIP.replace("2026-09-21", "2026-02-30"),
        BEHAVIOUR_TOOLTIP.replace("Data wystawienia", "Data"),
        # No tooltip at all.
        "",
    ],
)
def test_behaviour_point_entry_tooltip_fails_closed(tooltip: str) -> None:
    cell = behaviour_points(boxes=behaviour_box(tooltip=tooltip))
    with pytest.raises(ParseError):
        parse_grade_records(_with_behaviour(cell, "-"))


@pytest.mark.parametrize("count", [GRADE_MAX_RECORDS, GRADE_MAX_RECORDS + 1])
def test_behaviour_point_entries_share_the_grade_record_bound(count: int) -> None:
    # Ordinary grades and point entries together are bounded, as one page.
    grades = grade_box(extra="") * (count - 2)
    cell = behaviour_points(boxes=behaviour_box() + behaviour_box("-1", "902"))
    body = grades_html(first=grades, rows=behaviour_row(cell, "-")).encode()
    if count == GRADE_MAX_RECORDS:
        records = parse_grade_records(body)
        assert len(records.numeric) + len(records.behaviour_points[0].entries) == count
    else:
        with pytest.raises(LimitError):
            parse_grade_records(body)


def _point_behaviour_row(cell: str) -> str:
    return (
        '<tr class="line0"><td class="center micro screen-only"><img '
        'id="przedmioty_OP_zachowanie_node"></td><td>Zachowanie</td>'
        f'<td colspan="2">{cell}</td><td class="center"> - </td>'
        f'<td colspan="2">-</td><td class="center"> - </td>'
        '<td class="center"> - </td></tr>'
    )


def test_behaviour_points_shown_by_both_tables_are_one_item() -> None:
    cell = behaviour_points("50", behaviour_box("+5", "11"))
    extra = point_table(point_row() + _point_behaviour_row(cell))
    body = grades_html(rows=behaviour_row(cell, "-"), extra=extra)
    (item,) = parse_grade_records(body.encode()).behaviour_points
    assert (item.semester, item.tally, len(item.entries)) == (1, 50, 1)
    # Only the point table shows them.
    alone = grades_html(rows=behaviour_row("-", "-"), extra=extra)
    assert parse_grade_records(alone.encode()).behaviour_points == (item,)
    other = point_table(point_row() + _point_behaviour_row(behaviour_points("49")))
    with pytest.raises(ParseError):
        parse_grade_records(
            grades_html(rows=behaviour_row(cell, "-"), extra=other).encode()
        )


def test_behaviour_grade_symbol_entries_are_grades_with_their_category() -> None:
    # Reported in #114 from a synthetic example: the point-entry layout with a
    # grade symbol and no points cell made the whole grades read fail.
    records = parse_grade_records(
        _with_behaviour(
            behaviour_grade_box(), behaviour_grade_box("bdb", "bardzo dobre", "904")
        )
    )
    behaviour = [g for g in records.numeric if g.subject == "Zachowanie"]
    assert [(g.raw, g.semester, g.category, g.day) for g in behaviour] == [
        ("wz", 1, "wzorowe", date(2026, 10, 16)),
        ("bdb", 2, "bardzo dobre", date(2026, 10, 16)),
    ]
    assert behaviour[0].teacher is None
    assert behaviour[0].counts_toward_average is None
    assert behaviour[0].weight is None
    assert behaviour[0].href == "/przegladaj_oceny/zachowanie_szczegoly/903"
    assert behaviour[0].metadata == (
        ("Data wystawienia", "2026-10-16"),
        ("Dodał", "Teacher Fixture"),
    )
    assert [g.subject for g in records.numeric if g.subject != "Zachowanie"] == [
        "Fixture Language"
    ]
    # The reporter's reproduction: the entry in an ordinary-width row.
    alone = parse_grade_records(
        grades_html(first=behaviour_grade_box(), subject="Zachowanie").encode()
    )
    assert [(g.raw, g.category) for g in alone.numeric] == [("wz", "wzorowe")]


@pytest.mark.parametrize(
    "first",
    [
        behaviour_grade_box("3"),
        behaviour_grade_box("+2"),
        behaviour_grade_box("1.5"),
        behaviour_grade_box("+ 3"),
        behaviour_grade_box(""),
        behaviour_grade_box().replace("Data wystawienia", "Data"),
        behaviour_grade_box().replace("Dodał:", "Dodał"),
        # A labelled first line means the heading is missing.
        behaviour_grade_box(heading="Dodał: Teacher Fixture").replace(
            "&lt;br /&gt;Dodał: Teacher Fixture", ""
        ),
        behaviour_grade_box(heading="Komentarz: Fixture remark"),
        behaviour_grade_box(heading="Data wystawienia: 2026-10-01"),
        behaviour_grade_box().replace('title="', 'data-x="'),
        # A point entry's tooltip with a symbol label.
        behaviour_box("wz"),
        behaviour_points(boxes=behaviour_grade_box()),
    ],
)
def test_behaviour_grade_entry_layout_fails_closed(first: str) -> None:
    with pytest.raises(ParseError):
        parse_grade_records(_with_behaviour(first, "-"))


def test_an_unlabelled_tooltip_line_still_fails_outside_behaviour_entries() -> None:
    entry = behaviour_grade_box()
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(first=entry).encode())
    ordinary = entry.replace("zachowanie_szczegoly", "szczegoly")
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(first=ordinary, subject="Zachowanie").encode())
    # A descriptive row has no category to keep the first line in.
    row = (
        '<tr><td class="micro center screen-only"></td><td>Zachowanie</td>'
        f"<td>{entry}</td><td></td></tr>"
    )
    with pytest.raises(ParseError):
        parse_grade_records(
            f'<html><body><table class="decorated">{row}</table></body></html>'.encode()
        )


@pytest.mark.parametrize(
    "first",
    [
        behaviour_points("many"),
        behaviour_points("1.5"),
        behaviour_points("<b>50</b>"),
        '<span class="fixture">50</span>',
        behaviour_points() + behaviour_points(),
        behaviour_points() + "Fixture text",
        behaviour_points(boxes="<b>Fixture</b>"),
        behaviour_points(boxes=grade_box()),
        behaviour_points(boxes=behaviour_box(href="fixture-link")),
        behaviour_points(boxes=behaviour_box("many")),
        behaviour_points(boxes=behaviour_box().replace("</a>", "</a><a>1</a>")),
    ],
)
def test_behaviour_points_layout_fails_closed(first: str) -> None:
    with pytest.raises(ParseError):
        parse_grade_records(_with_behaviour(first))


def test_starting_points_outside_the_behaviour_row_fail() -> None:
    body = grades_html(first=behaviour_points(boxes=behaviour_box()))
    with pytest.raises(ParseError):
        parse_grade_records(body.encode())
    body = grades_html(first=behaviour_points())
    with pytest.raises(ParseError):
        parse_grade_records(body.encode())


def test_point_table_beside_the_ordinary_table_adds_percentage_scores() -> None:
    # Point-grade schools add an "Oceny punktowe" table with its own current
    # grade columns; both tables used to make the whole read ambiguous.
    rows = point_row(second=point_box("100", "7003", "2027-02-01")) + point_row(
        point_box("100", "7004"), subject="Fixture Language", node="72"
    )
    records = parse_grade_records(grades_html(extra=point_table(rows)).encode())
    symbol, first, low, later, same_subject = records.numeric
    assert symbol.point_grade_id is None
    assert [(g.subject, g.raw, g.semester) for g in (first, low, later)] == [
        ("Fixture Science", "90", 1),
        ("Fixture Science", "44", 1),
        ("Fixture Science", "100", 2),
    ]
    assert [g.point_grade_id for g in (first, low, later)] == ["7001", "7002", "7003"]
    assert first.category == "Fixture essay (0-100)"
    assert first.day == date(2026, 10, 5)
    assert first.counts_toward_average is None
    assert ("Licz do wyniku", "TAK") in first.metadata
    assert (same_subject.subject, same_subject.raw) == ("Fixture Language", "100")
    # "Wyn." results are on the score scale and stay apart from the ordinary
    # averages, even for a subject that both tables list.
    assert [(a.subject, a.semester, a.value.raw) for a in records.averages] == [
        ("Fixture Language", 1, "4,25"),
        ("Fixture Language", 2, ""),
        ("Fixture Language", 0, "-"),
    ]
    assert [(a.subject, a.semester, a.value.raw) for a in records.point_results] == [
        ("Fixture Science", 1, "67"),
        ("Fixture Science", 2, "-"),
        ("Fixture Science", 0, "-"),
        ("Fixture Language", 1, "67"),
        ("Fixture Language", 2, "-"),
        ("Fixture Language", 0, "-"),
    ]


@pytest.mark.parametrize("label", ["Wyn.I", "Wyn. I"])
def test_point_table_alone_is_a_complete_grade_page(label: str) -> None:
    table = point_table(annual=False).replace("Wyn.I", label)
    records = parse_grade_records(f"<html><body>{table}</body></html>".encode())
    assert [g.raw for g in records.numeric] == ["90", "44"]
    assert records.averages == ()
    assert records.point_results[0].value.raw == "67"


def test_observed_point_page_reads_scores_results_and_formative_mirror() -> None:
    # 1.7.0 failed this layout: a formative entry among the point entries and
    # an over-wide empty footer.
    records = parse_grade_records(observed_point_page().encode())
    first, low, mirror = records.numeric
    assert [(g.raw, g.point_grade_id) for g in (first, low)] == [
        ("90", "7001"),
        ("44", "7002"),
    ]
    assert (mirror.raw, mirror.point_grade_id, mirror.formative_id) == (
        "T",
        None,
        "951",
    )
    (assessment,) = records.formative
    assert (assessment.detail_id, assessment.text) == ("951", "+ Fixture text")
    assert [(a.subject, a.semester, a.value.raw) for a in records.point_results] == [
        ("Fixture Science", 1, "67"),
        ("Fixture Science", 2, "-"),
        ("Fixture Science", 0, "67.00"),
        ("Fixture Workshop", 1, "-"),
        ("Fixture Workshop", 2, "-"),
        ("Fixture Workshop", 0, "0.00"),
        ("Zachowanie", 1, None),
        ("Zachowanie", 2, None),
        ("Zachowanie", 0, None),
    ]
    # The midterm title breaks its own label; it still names the period column.
    box = grade_box("5", extra="")
    (period,) = [
        g
        for g in parse_grade_records(observed_point_page(box).encode()).numeric
        if g.kind == GradeKind.PERIOD
    ]
    assert (period.raw, period.semester) == ("5", 1)


def test_a_period_grade_shown_by_both_tables_is_one_record() -> None:
    box = grade_box("5", extra="")
    ordinary = grades_html().replace(
        "<td>4,25</td><td>-</td>", f"<td>4,25</td><td>{box}</td>"
    )
    row = point_row(subject="Fixture Language").replace(
        '<td class="center"> - </td>', f"<td>{box}</td>", 1
    )
    records = parse_grade_records(
        ordinary.replace("</body>", point_table(row) + "</body>").encode()
    )
    assert [g.raw for g in records.numeric if g.kind == GradeKind.PERIOD] == ["5"]


@pytest.mark.parametrize(
    "extra",
    [
        point_table() + point_table(point_row(subject="Fixture Other", node="73")),
        point_table(point_row() + point_row(node="73")),
        point_table().replace('<td class="center">67</td>', ""),
        point_table().replace("<td>Wyn.I</td>", "<td>Oceny bieżące</td>"),
        point_table().replace(
            "/przegladaj_oceny_punktowe/szczegoly/7001", "fixture-link"
        ),
    ],
    ids=[
        "two-point-tables",
        "duplicate-subject",
        "short-row",
        "third-current",
        "entry-without-point-link",
    ],
)
def test_ambiguous_point_table_fails_closed(extra: str) -> None:
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(extra=extra).encode())


def test_numeric_symbols_descriptive_entries_and_school_averages_are_lossless() -> None:
    body = grades_html(
        first=grade_box("np", extra=""),
        second=grade_box("making progress", "2027-01-12", descriptive=True),
    )
    records = parse_grade_records(body.encode())
    (numeric,) = records.numeric
    assert numeric.raw == "np"
    assert numeric.counts_toward_average is None
    assert numeric.weight is None
    assert numeric.semester == 1
    assert numeric.teacher == "Fixture Teacher"
    assert numeric.category == "Fixture quiz"
    assert numeric.href == "fixture-link"
    (descriptive,) = records.descriptive
    assert descriptive.raw == "making progress"
    assert descriptive.semester == 2
    assert descriptive.day == date(2027, 1, 12)
    assert descriptive.comment == "Synthetic: note"
    assert [(a.semester, a.value.raw) for a in records.averages] == [
        (1, "4,25"),
        (2, ""),
        (0, "-"),
    ]
    assert all(a.value.availability == Availability.AVAILABLE for a in records.averages)
    for item in (records, numeric, descriptive, *records.averages):
        assert "Fixture" not in repr(item)
        assert "progress" not in repr(item)
        assert "2027" not in repr(item)


def test_optional_average_column_is_unavailable_not_zero() -> None:
    body = grades_html().replace('<th title="Średnia roczna">Average</th>', "")
    body = body.replace("<td>-</td><td>-</td></tr></tbody>", "<td>-</td></tr></tbody>")
    records = parse_grade_records(body.encode())
    annual = next(a for a in records.averages if a.semester == 0)
    assert annual.value.raw is None
    assert annual.value.availability == Availability.UNAVAILABLE


def test_inline_revised_grades_are_preserved_without_expanded_detail_duplicates() -> (
    None
):
    inline = "<span>" + grade_box("3") + grade_box("5") + "</span>"
    body = grades_html(first=inline).replace(
        "</tbody>",
        '<tr><td colspan="10"><table><tr><td>'
        + grade_box("5")
        + "</td></tr></table></td></tr></tbody>",
    )
    records = parse_grade_records(body.encode())
    assert [g.raw for g in records.numeric] == ["3", "5"]


@pytest.mark.parametrize("empty_marker", ["", "Brak ocen"])
def test_valid_subject_table_without_grade_entries_is_empty_not_wrong_page(
    empty_marker: str,
) -> None:
    records = parse_grade_records(grades_html(first=empty_marker).encode())
    assert records.numeric == ()
    assert records.descriptive == ()
    assert len(records.averages) == 3
    with pytest.raises(ParseError):
        parse_grade_records(b"<html>No grade contract</html>")


def test_html_comments_are_not_grade_markers() -> None:
    body = grades_html(first=grade_box("4<!-- invisible -->+")).replace(
        "<body>", "<body><!-- Original display comment -->"
    )
    records = parse_grade_records(body.encode())
    assert records.numeric[0].raw == "4+"


@pytest.mark.parametrize("count", [GRADE_MAX_RECORDS, GRADE_MAX_RECORDS + 1])
def test_grade_record_bound_is_not_partial_success(count: int) -> None:
    body = grades_html(first=grade_box(extra="") * count).encode()
    if count == GRADE_MAX_RECORDS:
        assert len(parse_grade_records(body).numeric) == count
    else:
        with pytest.raises(LimitError):
            parse_grade_records(body)


def test_unrecognized_current_grade_markup_does_not_mean_empty_success() -> None:
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(first="<span>4+</span>").encode())


@pytest.mark.parametrize(
    "extra",
    [
        "Data: 2026-09-30",
        "Licz do średniej: unknown",
        "Waga: -1",
        "Waga: 1.5",
        "Waga: 10000",
        "Malformed field",
        # Only the free-text comment continues on unlabelled lines.
        "Waga: 2\nMalformed field",
    ],
)
def test_malformed_metadata_fails_the_whole_collection(extra: str) -> None:
    with pytest.raises(ParseError) as caught:
        parse_grade_records(grades_html(first=grade_box(extra=extra)).encode())
    assert caught.value.__context__ is None
    assert "Fixture" not in str(caught.value)


def test_a_multi_line_comment_continues_on_unlabelled_lines() -> None:
    # Observed live 2026-10-27: a comment line break, blank lines and a short
    # unlabelled line, which failed the whole grade read up to 1.7.0.
    extra = "Waga: 2<br>Komentarz: first part<br><br>\n\nsecond part\n<br>"
    (grade,) = parse_grade_records(
        grades_html(first=grade_box(extra=extra)).encode()
    ).numeric
    assert grade.comment == "first part\nsecond part"
    assert grade.weight == 2


@pytest.mark.parametrize("counts", ["tak", "nie", "TAK"])
def test_count_and_weight_are_taken_only_from_explicit_metadata(counts: str) -> None:
    records = parse_grade_records(
        grades_html(
            first=grade_box(
                extra=f"Licz do średniej: {counts}<br/>Waga: 0<br/>Extra: Preserved",
            )
        ).encode()
    )
    (grade,) = records.numeric
    assert grade.counts_toward_average == (counts.casefold() == "tak")
    assert grade.weight == 0
    assert dict(grade.metadata)["Extra"] == "Preserved"


def test_metadata_length_bound_is_enforced_without_value_disclosure() -> None:
    with pytest.raises(LimitError):
        parse_grade_records(
            grades_html(
                first=grade_box(
                    extra="Comment: " + "x" * GRADE_MAX_METADATA_LENGTH,
                )
            ).encode()
        )


@pytest.mark.parametrize(
    "outside,expected",
    [
        (
            "<table><tr><td>" + grade_box() + "</td></tr></table>",
            UnsupportedCapabilityError,
        ),
        (
            "<table><tr><th><strong>Fixture semester report</strong> "
            "opublikowano: Fixture publication metadata</th></tr></table>",
            ParseError,
        ),
    ],
)
def test_unsupported_extra_grade_layouts_do_not_return_partial_success(
    outside: str,
    expected: type[Exception],
) -> None:
    with pytest.raises(expected):
        parse_grade_records(
            grades_html().replace("</body>", outside + "</body>").encode()
        )


def test_public_grade_read_and_windows_share_one_account_scoped_collection() -> None:
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.grade_body = grades_html(
            first=grade_box(day="2026-09-29") + grade_box(day="2026-09-30"),
            second=grade_box("good progress", "2026-10-01", descriptive=True),
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                result = await client.grades()
                window = await client.grades_window(
                    date(2026, 9, 30), date(2026, 10, 1), max_age_seconds=60
                )
                assert [g.day for g in window.numeric] == [date(2026, 9, 30)]
                assert [g.day for g in window.descriptive] == [date(2026, 10, 1)]
                assert window.observation is result.observation
                assert result.observation.source == "grades"
                assert result.identity.owner.id == "student"
                assert await client.grades(max_age_seconds=60) is result
                assert len(fixture.view_posts) == 1
                assert len(fixture.calls) == service.snapshot().requests_dispatched == 6
                assert await client.grades() is not result
                assert len(fixture.view_posts) == 2
                last = await client.grades_window(
                    end=date(2026, 9, 29), view=GradeView.LAST_LOGIN
                )
                assert last.view is GradeView.LAST_LOGIN and last.start is None
                assert [g.day for g in last.numeric] == [date(2026, 9, 29)]
                assert last.descriptive == ()
                assert fixture.view_posts[-1][1] == {"zmiany_logowanie": "1"}
                unfiltered = await client.grades_window(
                    view=GradeView.LAST_LOGIN, max_age_seconds=60
                )
                assert len(unfiltered.numeric) == 2
                assert len(unfiltered.descriptive) == 1
                assert unfiltered.observation == last.observation
                assert len(fixture.view_posts) == 3
                # MCP's accepted 370-day difference also remains cache-only.
                wide = await client.grades_window(
                    date(2026, 1, 1), date(2027, 1, 6), max_age_seconds=60
                )
                assert len(wide.numeric) == 2 and len(wide.descriptive) == 1
                assert len(fixture.view_posts) == 3

    asyncio.run(scenario())


def test_a_window_keeps_behaviour_points_with_an_entry_inside_it() -> None:
    later = BEHAVIOUR_TOOLTIP.replace("2026-09-21", "2026-10-05")
    boxes = behaviour_box("+5", "11") + behaviour_box("-3", "12", tooltip=later)
    total = '<span class="tooltip" title="Fixture points history"> 80 </span>'

    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        fixture.grade_body = grades_html(
            rows=behaviour_row(behaviour_points("50", boxes), total)
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                result = await client.grades()
                whole = await client.grades_window(max_age_seconds=60)
                late = await client.grades_window(
                    date(2026, 10, 1), date(2026, 10, 31), max_age_seconds=60
                )
                none = await client.grades_window(
                    date(2026, 11, 1), date(2026, 11, 30), max_age_seconds=60
                )
        assert [(p.semester, p.tally) for p in result.records.behaviour_points] == [
            (1, 50),
            (2, 80),
        ]
        # The undated tally alone stays outside every window, like averages.
        assert whole.behaviour_points == result.records.behaviour_points[:1]
        (item,) = late.behaviour_points
        assert (item.semester, item.tally) == (1, 50)
        assert [(e.points, e.detail_id) for e in item.entries] == [(-3, "12")]
        assert none.behaviour_points == ()

    asyncio.run(scenario())


def test_a_logged_out_grade_page_is_posted_again_in_a_fresh_session() -> None:
    # The view POST answered with a logged-out page was not applied to the
    # account, so it is repeated once after signing in again.
    async def scenario() -> None:
        fixture = GradeRecordsFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                await service.account("student").grades()
                fixture.logged_out["student"] = 1
                grades = await service.account("student").grades()
        assert grades.records.numeric
        assert len(fixture.view_posts) == 3 and fixture.logins == {"student": 2}

    asyncio.run(scenario())


def _formative_mirror(lines: str, href: str = FORMATIVE_LINK.format(961)) -> str:
    title = escape(
        f"Ocena: +<br/>{lines}Kategoria: Fixture task<br/>Data: 2026-11-07"
        "<br/>Nauczyciel: Fixture Teacher<br/>Dodał: Fixture Teacher<br/>",
        quote=True,
    )
    return f'<span class="grade-box"><a href="{href}" title="{title}">T</a></span>'


# The layout of an owner's live page (2026-11-08, structure only): the
# assessment text of a formative grid entry spans lines between blank ones,
# one of them holding a colon, before the labelled fields.
MULTILINE_ASSESSMENT = (
    "<br/>Fixture line one<br/><br/>Fixture line two<br/><br/>Fixture line three"
    "<br/><br/>Fixture aspect: what went well<br/><br/>Short<br/><br/>Fixture line six"
    "<br/><br/><br/><br/>Fixture closing line<br/>"
)


def test_a_formative_grid_entry_keeps_its_multiline_assessment_text() -> None:
    (grade,) = parse_grade_records(
        grades_html(first=_formative_mirror(MULTILINE_ASSESSMENT)).encode()
    ).numeric
    assert grade.formative_id == "961"
    assert grade.raw == "T" and grade.day == date(2026, 11, 7)
    assert grade.category == "Fixture task"
    assert grade.metadata == (
        ("Ocena", "+\nFixture line one\nFixture line two\nFixture line three"),
        (
            "Fixture aspect",
            "what went well\nShort\nFixture line six\nFixture closing line",
        ),
        ("Kategoria", "Fixture task"),
        ("Data", "2026-11-07"),
        ("Nauczyciel", "Fixture Teacher"),
        ("Dodał", "Fixture Teacher"),
    )


def test_known_labels_inside_formative_assessment_text_stay_text() -> None:
    lines = (
        "<br/>Fixture line one<br/>Komentarz: fixture remark<br/>Data: next week"
        "<br/>Waga: fixture<br/>Fixture last line<br/>"
    )
    (grade,) = parse_grade_records(
        grades_html(first=_formative_mirror(lines)).encode()
    ).numeric
    assert grade.comment is None and grade.weight is None
    assert grade.day == date(2026, 11, 7)
    assert dict(grade.metadata)["Ocena"] == (
        "+\nFixture line one\nKomentarz: fixture remark\nData: next week"
        "\nWaga: fixture\nFixture last line"
    )
    assert list(dict(grade.metadata))[1:] == [
        "Kategoria",
        "Data",
        "Nauczyciel",
        "Dodał",
    ]


@pytest.mark.parametrize(
    "first",
    [
        # Only a formative entry's assessment text may span lines.
        _formative_mirror(MULTILINE_ASSESSMENT, href="/przegladaj_oceny/szczegoly/971"),
        # A known label never takes a continuation line.
        _formative_mirror("<br/>").replace(
            escape("Data: 2026-11-07<br/>"),
            escape("Data: 2026-11-07<br/>Fixture stray<br/>"),
        ),
    ],
    ids=["ordinary-entry", "after-known-label"],
)
def test_other_unlabelled_tooltip_lines_still_fail(first: str) -> None:
    with pytest.raises(ParseError):
        parse_grade_records(grades_html(first=first).encode())


def test_a_repeated_correction_line_keeps_both_values() -> None:
    # The week view of an owner's live page (2026-11-08, structure only): a
    # correction listed `Poprawa oceny` twice, both naming the same original,
    # the first ending in a comma. The all view listed it once.
    extra = (
        "Licz do średniej: tak<br/>Dodał: Fixture Teacher<br/><br/>"
        "Poprawa oceny: 1 (Fixture quiz),<br/>Poprawa oceny: 1 (Fixture quiz)"
    )
    (grade,) = parse_grade_records(
        grades_html(first=grade_box("4", extra=extra)).encode()
    ).numeric
    assert dict(grade.metadata)["Poprawa oceny"] == (
        "1 (Fixture quiz),\n1 (Fixture quiz)"
    )
    single = extra.replace(",<br/>Poprawa oceny: 1 (Fixture quiz)", "")
    (grade,) = parse_grade_records(
        grades_html(first=grade_box("4", extra=single)).encode()
    ).numeric
    assert dict(grade.metadata)["Poprawa oceny"] == "1 (Fixture quiz)"
    # Other labels still may not repeat.
    with pytest.raises(ParseError):
        parse_grade_records(
            grades_html(
                first=grade_box("4", extra="Dodał: Fixture A<br/>Dodał: Fixture B")
            ).encode()
        )
