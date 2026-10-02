"""Timetable business invariants at parser and actual loopback service boundaries."""

from datetime import time, timedelta

import pytest

from librus_python_api.exceptions import (
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.timetable import parse_timetable
from tests.timetable_support import (
    MONDAY,
    lesson,
    notice,
    timetable_html,
)


@pytest.mark.parametrize("tbody", [False, True])
def test_named_attributes_seven_days_empty_slots_and_recess(tbody: bool) -> None:
    days = parse_timetable(timetable_html(tbody=tbody).encode(), MONDAY)
    assert tuple(d.day for d in days) == tuple(
        MONDAY + timedelta(days=i) for i in range(7)
    )
    assert [p.number for p in days[0].periods] == [2, 4]
    first = days[0].periods[0]
    assert first.interval.starts_at == time(8, 10)
    assert first.interval.ends_at == time(8, 55)
    assert first.next_recess is not None
    assert first.next_recess.starts_at == time(8, 55)
    assert first.next_recess.ends_at == time(9, 15)
    assert days[0].periods[1].next_recess is None
    assert first.lessons[0].subject == "Fixture Biology"
    assert first.lessons[0].teacher_and_classroom == "Fixture Teacher - R12"
    assert first.changes == ()
    assert all(not p.lessons for d in days[1:] for p in d.periods)
    assert "Fixture" not in repr(first)


def test_substitution_notice_wrapped_in_its_tooltip_anchor_keeps_metadata() -> None:
    # Observed: the anchor carrying the tooltip wraps the notice element.
    content = (
        '<a href="javascript:void(0);" title="&lt;b&gt;Data:&lt;/b&gt; 2026-10-05'
        "&lt;br&gt;&lt;b&gt;Nr lekcji:&lt;/b&gt; 2&lt;br&gt;"
        "&lt;b&gt;Nauczyciel:&lt;/b&gt; Fixture Alternate&lt;br&gt;"
        '&lt;b&gt;Uwaga:&lt;/b&gt; Fixture: note">'
        '<div class="center plan-lekcji-info">zastępstwo</div></a>\n' + lesson()
    )
    period = parse_timetable(timetable_html(content=content).encode(), MONDAY)[
        0
    ].periods[0]
    assert [item.subject for item in period.lessons] == ["Fixture Biology"]
    (change,) = period.changes
    assert change.label == "zastępstwo"
    assert change.metadata == (
        ("Data", "2026-10-05"),
        ("Nr lekcji", "2"),
        ("Nauczyciel", "Fixture Alternate"),
        ("Uwaga", "Fixture: note"),
    )


def test_multiple_lessons_and_raw_change_metadata_are_not_flattened() -> None:
    content = (
        lesson("Fixture Bio-Chem")
        + lesson("Fixture Art")
        + notice(
            "Fixture replacement",
            "Nauczyciel: Fixture Alternate<br>Przedmiot: Fixture Arts<br>"
            "Sala: R9<br>Data dodania: 2026-10-01<br>Extra: left: right",
        )
    )
    first = parse_timetable(timetable_html(content=content).encode(), MONDAY)[
        0
    ].periods[0]
    assert [item.subject for item in first.lessons] == [
        "Fixture Bio-Chem",
        "Fixture Art",
    ]
    assert first.changes[0].label == "Fixture replacement"
    assert dict(first.changes[0].metadata)["Extra"] == "left: right"
    assert dict(first.changes[0].metadata)["Nauczyciel"] == "Fixture Alternate"


@pytest.mark.parametrize(
    "content,subject,teacher",
    [
        (
            '<div class="text">\n<b>Fixture Biology</b><br>\n'
            " - Fixture Teacher&nbsp; (R12)\n</div>",
            "Fixture Biology",
            "Fixture Teacher (R12)",
        ),
        (
            '<div class="text">\n<b>Fixture Bio-Chem</b><br>\n'
            " - Fixture North-South&nbsp; (R12-R14)\n</div>",
            "Fixture Bio-Chem",
            "Fixture North-South (R12-R14)",
        ),
        (
            '<div class="text"><b>Fixture Bio - Chem</b><br>'
            " - Fixture Teacher<br>(R12)</div>",
            "Fixture Bio - Chem",
            "Fixture Teacher (R12)",
        ),
    ],
)
def test_rendered_lesson_boundaries_preserve_teacher_and_subject_hyphens(
    content: str, subject: str, teacher: str
) -> None:
    first = parse_timetable(timetable_html(content=content).encode(), MONDAY)[
        0
    ].periods[0]
    assert len(first.lessons) == 1
    assert first.lessons[0].subject == subject
    assert first.lessons[0].teacher_and_classroom == teacher


def test_notice_only_and_valid_empty_grid_do_not_invent_lessons() -> None:
    first = parse_timetable(
        timetable_html(content=notice("Fixture cancelled")).encode(), MONDAY
    )[0].periods[0]
    assert first.lessons == ()
    assert first.changes[0].metadata == ()
    assert first.changes[0].label == "Fixture cancelled"
    days = parse_timetable(timetable_html(content="").encode(), MONDAY)
    assert all(not p.lessons and not p.changes for d in days for p in d.periods)


def test_centered_layout_prefix_does_not_make_number_or_recess_ambiguous() -> None:
    body = timetable_html().replace(
        "<th>Fixture time</th><td></td>",
        '<th>Fixture time</th><td class="center"></td>',
    )
    body = body.replace(
        '<tr class="line0"><td></td>', '<tr class="line0"><td class="center"></td>'
    )
    days = parse_timetable(body.encode(), MONDAY)
    assert [period.number for period in days[0].periods] == [2, 4]
    assert days[0].periods[0].next_recess is not None
    invalid = body.replace('<td class="center"></td>', '<td class="center">9</td>', 1)
    with pytest.raises(ParseError):
        parse_timetable(invalid.encode(), MONDAY)


def test_mirrored_number_prefix_requires_equal_values() -> None:
    body = timetable_html()
    for number in (2, 4):
        body = body.replace(
            f'<td class="center">{number}</td><th>Fixture time</th><td></td>',
            f'<td class="center">{number}</td><th class="center">Fixture time</th>'
            f'<td class="center">{number}</td>',
        )
    days = parse_timetable(body.encode(), MONDAY)
    assert [period.number for period in days[0].periods] == [2, 4]
    conflicting = body.replace(
        '<th class="center">Fixture time</th><td class="center">2</td>',
        '<th class="center">Fixture time</th><td class="center">3</td>',
        1,
    )
    with pytest.raises(ParseError):
        parse_timetable(conflicting.encode(), MONDAY)


@pytest.mark.parametrize(
    "before,after",
    [
        ('data-date="2026-10-05"', 'data-date="2026-10-12"'),
        ('data-date="2026-10-06"', 'data-date="2026-10-05"'),
        ('data-time_from="08:10"', 'data-time_from="25:10"'),
        ('data-time_to="08:55"', 'data-time_to="08:00"'),
        ("data-time_from=", "fixture-from="),
        ('<td class="center">4</td>', '<td class="center">2</td>'),
        ("08:55 - 09:15", "25:40 - 09:15"),
        ("<b>Fixture Biology</b>", "Fixture Biology"),
        ("Fixture Teacher - R12", "x" * 1025),
        ('class="line1" id="timetableEntryBox"', 'class="line1" id="unknownBox"'),
    ],
)
def test_malformed_week_fails_instead_of_partial_success(
    before: str, after: str
) -> None:
    with pytest.raises((ParseError, LimitError)):
        parse_timetable(timetable_html().replace(before, after).encode(), MONDAY)


@pytest.mark.parametrize(
    "change",
    ["missing", "duplicate", "outside_slot", "nested_table", "unparsed_content"],
)
def test_unknown_grids_and_unconsumed_content_fail(change: str) -> None:
    body = timetable_html()
    if change == "missing":
        body = "<html></html>"
    elif change == "duplicate":
        grid = body[body.index("<table") : body.index("</table>") + len("</table>")]
        body = body.replace("</body>", grid + "</body>")
    elif change == "outside_slot":
        body = body.replace("</body>", '<div id="timetableEntryBox"></div></body>')
    elif change == "nested_table":
        body = timetable_html(
            content="<table><tr><td>" + lesson() + "</td></tr></table>"
        )
    else:
        body = timetable_html(content="<div>Fixture unsupported lesson</div>")
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_timetable(body.encode(), MONDAY)


@pytest.mark.parametrize(
    "reported,first,last",
    [
        ("08:55 - 08:55", time(8, 55), time(8, 55)),
        ("09:15 - 08:55", time(9, 15), time(8, 55)),
    ],
)
def test_recess_is_a_reported_clock_pair_not_an_inferred_duration(
    reported: str,
    first: time,
    last: time,
) -> None:
    body = timetable_html().replace("08:55 - 09:15", reported)
    period = parse_timetable(body.encode(), MONDAY)[0].periods[0]
    assert period.next_recess is not None
    assert period.next_recess.starts_at == first
    assert period.next_recess.ends_at == last


def test_period_and_content_limits_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("librus_python_api.timetable.TIMETABLE_MAX_PERIODS", 1)
    with pytest.raises(LimitError):
        parse_timetable(timetable_html().encode(), MONDAY)


@pytest.mark.parametrize(
    "bound,content",
    [
        ("TIMETABLE_MAX_LESSONS_PER_SLOT", lesson() + lesson("Fixture Art")),
        ("TIMETABLE_MAX_CHANGES_PER_SLOT", notice() + notice("Fixture second change")),
    ],
)
def test_slot_content_limits(
    bound: str, content: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.timetable." + bound, 1)
    with pytest.raises(LimitError):
        parse_timetable(timetable_html(content=content).encode(), MONDAY)


def test_other_duplicate_ids_are_not_allowed_by_timetable_exception() -> None:
    body = timetable_html().replace(
        "</body>", '<div id="fixture-other"></div><div id="fixture-other"></div></body>'
    )
    with pytest.raises(ParseError):
        parse_timetable(body.encode(), MONDAY)


def test_tooltip_duplicate_fields_and_oversized_plain_values_fail() -> None:
    for title, expected in (
        ("Sala: R9<br>Sala: R10", ParseError),
        ("Extra: " + "x" * 1025, LimitError),
    ):
        with pytest.raises(expected):
            parse_timetable(
                timetable_html(content=notice(title=title)).encode(), MONDAY
            )
