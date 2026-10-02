"""Attendance business contracts at parser and real loopback service boundaries."""

import asyncio
from datetime import date

import pytest

from librus_python_api import AttendanceView
from librus_python_api.attendance import parse_attendance
from librus_python_api.exceptions import (
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from tests.attendance_support import AttendanceFixture, attendance_box, attendance_html
from tests.http_support import serve


@pytest.mark.parametrize("reverse", [False, True])
def test_attendance_preserves_explicit_semesters_and_civil_metadata(
    reverse: bool,
) -> None:
    result = parse_attendance(
        attendance_html(
            second=attendance_box("sp", "2027-02-03 (śr.)"), reverse=reverse
        ).encode()
    )
    assert result.semesters == ((2, 1) if reverse else (1, 2))
    rows = sorted(result.items, key=lambda r: r.semester)
    assert [(r.symbol, r.semester, r.day) for r in rows] == [
        ("nb", 1, date(2026, 10, 1)),
        ("sp", 2, date(2027, 2, 3)),
    ]
    assert rows[0].period == 3
    assert rows[0].excursion is False
    assert rows[0].detail_id == "2468"
    assert rows[0].subject == "Fixture Biology"
    assert rows[0].attendance_type == "Fixture absence"
    assert "Fixture" not in repr(rows[0])


def test_one_displayed_second_semester_is_not_invented_as_first() -> None:
    body = attendance_html().replace("I okres", "II okres", 1)
    body = (
        body[: body.index('<tr class="line0"><td class="center bolded">II okres')]
        + "</tbody></table></body></html>"
    )
    result = parse_attendance(body.encode())
    assert result.semesters == (2,)
    assert result.items[0].semester == 2


def test_numeric_period_headings_with_full_width_cells_preserve_semesters() -> None:
    body = attendance_html(second=attendance_box(day="2027-02-03"), reverse=True)
    body = body.replace(
        'class="bolded center">I okres', 'class="bolded center" colspan="7">Okres 1'
    )
    body = body.replace(
        'class="center bolded">II okres', 'class="center bolded" colspan="7">Okres 2'
    )
    result = parse_attendance(body.encode())
    assert result.semesters == (2, 1)
    assert [row.semester for row in result.items] == [2, 1]


def test_empty_is_only_success_with_a_valid_semester_grid() -> None:
    result = parse_attendance(attendance_html(first="", second="-").encode())
    assert result.items == ()
    assert result.semesters == (1, 2)
    with pytest.raises(ParseError):
        parse_attendance(
            b'<table class="big center decorated"><tr><td></td></tr></table>'
        )


def test_missing_optional_metadata_stays_unknown_and_custom_types_are_raw() -> None:
    body = attendance_html(first=attendance_box(extra="")).replace(
        "Fixture absence", "Fixture custom type"
    )
    (row,) = parse_attendance(body.encode()).items
    assert row.attendance_type == "Fixture custom type"
    assert row.period is None
    assert row.excursion is None
    assert row.subject is None
    assert row.topic is None


def test_bold_tooltip_blocks_and_colons_in_topics_are_preserved() -> None:
    from html import escape

    title = (
        "<b>Data: 2026-10-01</b><b>Rodzaj: Fixture custom type</b>"
        "<b>Temat zajęć: Topic: detail</b>"
    )
    first = '<a title="' + escape(title, quote=True) + '">nb</a>'
    row = parse_attendance(attendance_html(first=first).encode()).items[0]
    assert row.topic == "Topic: detail"
    assert row.detail_id is None


def test_unrecognized_dated_entries_outside_the_grid_are_not_omitted() -> None:
    body = attendance_html().replace(
        "</body>", "<div>" + attendance_box() + "</div></body>"
    )
    with pytest.raises(UnsupportedCapabilityError):
        parse_attendance(body.encode())


def test_nested_detail_tables_cannot_double_count_inline_attendance() -> None:
    body = attendance_html(
        first="<table><tr><td>" + attendance_box() + "</td></tr></table>"
    )
    with pytest.raises(UnsupportedCapabilityError):
        parse_attendance(body.encode())


def test_collection_limit_stops_without_partial_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("librus_python_api.attendance.ATTENDANCE_MAX_RECORDS", 1)
    with pytest.raises(LimitError):
        parse_attendance(attendance_html(second=attendance_box()).encode())


@pytest.mark.parametrize(
    "onclick",
    [
        "otworz_w_nowym_oknie('https://example.invalid/przegladaj_nb/szczegoly/2468','x')",
        "otworz_w_nowym_oknie('/przegladaj_nb/szczegoly/../2468','x')",
        "otworz_w_nowym_oknie('/przegladaj_nb/szczegoly/2468?token=fixture','x')",
        "alert('fixture')",
        "otworz_w_nowym_oknie('/przegladaj_nb/szczegoly/2468', evil())",
        "otworz_w_nowym_oknie('/przegladaj_nb/szczegoly/24\t68', 'x')",
        "",
    ],
)
def test_unknown_or_foreign_script_links_are_never_transport_references(
    onclick: str,
) -> None:
    row = parse_attendance(
        attendance_html(first=attendance_box(onclick=onclick)).encode()
    ).items[0]
    assert row.detail_id is None


def test_plain_tooltip_values_obey_the_rendered_value_bound() -> None:
    body = attendance_html(first=attendance_box(extra="Temat zajęć: " + "x" * 1025))
    with pytest.raises(LimitError):
        parse_attendance(body.encode())


@pytest.mark.parametrize(
    "change",
    [
        "invalid_date",
        "invalid_period",
        "invalid_boolean",
        "duplicate_key",
        "unknown_section",
        "duplicate_section",
        "missing_title",
        "nonempty_unknown_cell",
        "duplicate_table",
    ],
)
def test_malformed_attendance_never_returns_partial_success(change: str) -> None:
    body = attendance_html()
    replacements = {
        "invalid_date": ("2026-10-01", "2026-02-30"),
        "invalid_period": ("Godzina lekcyjna: 3", "Godzina lekcyjna: 3.5"),
        "invalid_boolean": ("Czy wycieczka: Nie", "Czy wycieczka: Maybe"),
        "duplicate_key": ("Rodzaj: Fixture absence", "Data: 2026-10-01"),
        "unknown_section": ("I okres", "Fixture unknown period"),
        "duplicate_section": ("II okres", "I okres"),
        "missing_title": ("title=", "fixture-title="),
        "nonempty_unknown_cell": (
            '<td class="center"></td>',
            '<td class="center">unparsed absence</td>',
        ),
    }
    if change == "duplicate_table":
        body = body.replace(
            "</body>",
            attendance_html().split("<body>")[1].split("</body>")[0] + "</body>",
        )
    else:
        body = body.replace(*replacements[change])
    with pytest.raises(ParseError):
        parse_attendance(body.encode())


def test_attendance_views_cache_and_windows_use_one_all_collection() -> None:
    async def scenario() -> None:
        fixture = AttendanceFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service() as service:
                client = service.account("student")
                all_rows, week, last = await asyncio.gather(
                    client.attendance(),
                    client.attendance(view=AttendanceView.WEEK),
                    client.attendance(view=AttendanceView.LAST_LOGIN),
                )
                assert [r.view for r in (all_rows, week, last)] == list(AttendanceView)
                assert [r.items[0].day for r in (all_rows, week, last)] == [
                    date(2026, 10, 1),
                    date(2026, 10, 2),
                    date(2026, 10, 3),
                ]
                assert len(fixture.view_posts) == 3
                for result in (all_rows, week, last):
                    assert (
                        await client.attendance(view=result.view, max_age_seconds=60)
                        is result
                    )
                window = await client.attendance_window(
                    date(2026, 10, 1), date(2026, 10, 1), max_age_seconds=60
                )
                assert window.items == (all_rows.items[0],)
                assert len(all_rows.items) == 2
                assert window.observation == all_rows.observation
                empty = await client.attendance_window(
                    date(2026, 10, 4), date(2026, 10, 4), max_age_seconds=60
                )
                assert empty.items == ()
                assert len(fixture.view_posts) == 3
                assert len(fixture.logins) == 1

    asyncio.run(scenario())
