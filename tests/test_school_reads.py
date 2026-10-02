"""Calendar/homework integrity and owning service security/wire guarantees."""

from collections.abc import Callable
from datetime import date, datetime, time

import pytest

from librus_python_api import SchoolReference
from librus_python_api.completed_lessons import parse_completed_lessons
from librus_python_api.config import homework_form
from librus_python_api.exceptions import (
    InvalidInputError,
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
    ViewDisabledError,
)
from librus_python_api.school_reads import (
    parse_agenda,
    parse_homework,
    parse_school_detail,
)
from tests.school_reads_support import (
    HOMEWORK_EMPTY,
    RANGE_REJECTED,
    VIEW_DISABLED,
    agenda_html,
    detail_html,
    homework_html,
    homework_row,
    warning_html,
)


@pytest.mark.parametrize(
    "year,month,count", [(2026, 10, 31), (2026, 9, 30), (2028, 2, 29), (2026, 2, 28)]
)
def test_complete_month_retains_empty_days_events_metadata_and_references(
    year: int, month: int, count: int
) -> None:
    days = parse_agenda(agenda_html(year, month).encode(), year, month, "fixture")
    assert len(days) == count
    assert [day.day for day in days] == [
        date(year, month, i) for i in range(1, count + 1)
    ]
    event = days[1].events[0]
    assert event.title == "Fixture test"
    assert event.subject == "Fixture Biology"
    assert event.lesson_number == 2 and event.at_time is None
    assert (
        event.text == "Lekcja: 2\nFixture Biology\nFixture test\nFixture ancillary text"
    )
    assert dict(event.metadata)["Opis"] == "Fixture: description"
    assert event.reference == SchoolReference("agenda", "123", "fixture")
    assert all(not day.events for day in days if day.day.day != 2)
    assert "Fixture" not in repr(event)


def test_subjectless_nonlesson_and_metadata_notes_do_not_invent_defaults() -> None:
    cell = (
        '<td title="Fixture flag&lt;br&gt;Opis: Fixture note">'
        "09:30<br>Fixture meeting</td>"
    )
    event = parse_agenda(agenda_html(cell=cell).encode(), 2026, 10, "fixture")[
        1
    ].events[0]
    assert event.title == "Fixture meeting"
    assert event.subject is None
    assert event.lesson_number is None
    assert event.reference is None
    assert event.at_time == time(9, 30)
    assert event.metadata_notes == ("Fixture flag",)
    assert dict(event.metadata) == {"Opis": "Fixture note"}
    assert all(
        not day.events
        for day in parse_agenda(agenda_html(cell="").encode(), 2026, 10, "fixture")
    )


def test_tooltip_full_text_retains_intermediate_notes_and_label_spacing() -> None:
    cell = (
        '<td title="Nauczyciel : Fixture Teacher&lt;br /&gt;'
        'Fixture intermediate note&lt;br /&gt;Opis: Fixture detail">'
        "Fixture meeting</td>"
    )
    event = parse_agenda(agenda_html(cell=cell).encode(), 2026, 10, "fixture")[
        1
    ].events[0]
    assert event.metadata_text == (
        "Nauczyciel : Fixture Teacher\nFixture intermediate note\nOpis: Fixture detail"
    )
    assert event.metadata == (
        ("Nauczyciel", "Fixture Teacher"),
        ("Opis", "Fixture detail"),
    )
    assert event.metadata_notes == ("Fixture intermediate note",)


def test_multiline_description_stays_one_field_until_the_next_label() -> None:
    # Observed: a long meeting description, one line per <br>, some with colons.
    lines = [f"{n}. Fixture item: part {n}" for n in range(1, 40)]
    title = (
        "Nauczyciel: Fixture Teacher&lt;br&gt;Opis: Fixture agenda&lt;br&gt;"
        + "&lt;br&gt;".join(lines)
        + "&lt;br&gt;Data dodania: 2026-09-01 10:00:00"
    )
    cell = f'<td title="{title}">Fixture meeting</td>'
    event = parse_agenda(agenda_html(cell=cell).encode(), 2026, 10, "fixture")[
        1
    ].events[0]
    assert [label for label, _ in event.metadata] == [
        "Nauczyciel",
        "Opis",
        "Data dodania",
    ]
    assert dict(event.metadata)["Opis"] == "\n".join(["Fixture agenda", *lines])
    assert event.metadata_notes == ()


def test_subjectless_multiline_title_is_not_replaced_with_its_note() -> None:
    event = parse_agenda(
        agenda_html(
            cell="<td>Fixture school closure<br>Fixture explanation</td>"
        ).encode(),
        2026,
        10,
        "fixture",
    )[1].events[0]
    assert event.title == "Fixture school closure"
    assert event.lesson_number is None and event.subject is None


def test_inline_subject_header_does_not_hide_lesson_number_or_punctuation() -> None:
    cell = (
        "<td>Lekcja nr: 4, <span>Fixture Biology</span><br>Fixture quiz, revision</td>"
    )
    event = parse_agenda(agenda_html(cell=cell).encode(), 2026, 10, "fixture")[
        1
    ].events[0]
    assert event.lesson_number == 4
    assert event.title == "Fixture quiz, revision"
    assert event.subject == "Fixture Biology"


@pytest.mark.parametrize(
    "before,after",
    [
        (">31</div>", ">32</div>"),
        (">31</div>", ">30</div>"),
        ("kalendarz-numer-dnia", "unknown-number"),
        ("/terminarz/szczegoly/123", "/terminarz/dodane_od_ostatniego_logowania"),
        ("/terminarz/szczegoly/123", "https://example.invalid/123"),
        (
            "<span>Fixture Biology</span>",
            "<span>Fixture Biology</span><span>Fixture ambiguous</span>",
        ),
        ("<td title=", '<td colspan="2" title='),
        (
            "Fixture ancillary text",
            "<table><tr><td>Fixture nested event</td></tr></table>",
        ),
        ("Nauczyciel: Fixture Teacher", "Opis: Fixture duplicate"),
    ],
)
def test_malformed_calendar_never_becomes_partial(before: str, after: str) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_agenda(agenda_html().replace(before, after).encode(), 2026, 10, "fixture")


def test_homework_maps_observed_columns_by_header() -> None:
    done = (
        '<img class="tooltip helper-icon" '
        'title="Zadanie oznaczono jako wykonane (2026-09-27, 17:59)">'
    )
    rows = homework_row("456") + homework_row(
        "789",
        topic="Fixture second",
        assigned=("2026-09-24", "czw."),
        due=("2026-09-25", "pt."),
        options=done,
    )
    first, second = parse_homework(homework_html(rows=rows).encode(), "fixture")
    assert (first.subject, first.teacher, first.topic, first.category) == (
        "Fixture Biology",
        "Fixture Teacher",
        "Fixture topic",
        "Fixture category",
    )
    assert (first.assigned_on, first.due_on) == (date(2026, 9, 16), date(2026, 9, 17))
    assert first.submission_status == "-"
    assert first.marked_done_at is None
    assert first.reference == SchoolReference("homework", "456", "fixture")
    assert second.marked_done_at == datetime(2026, 9, 27, 17, 59)
    assert second.reference == SchoolReference("homework", "789", "fixture")
    assert "Fixture" not in repr(first)


def test_homework_empty_page_is_empty_but_rejected_range_is_not() -> None:
    assert parse_homework(HOMEWORK_EMPTY.encode(), "fixture") == ()
    with pytest.raises(InvalidInputError):
        parse_homework(warning_html(RANGE_REJECTED, "Brak wpisów").encode(), "fixture")
    for body in (
        "<html></html>",
        warning_html("Fixture unknown notice", "Brak wpisów"),
        homework_html().replace("</body>", '<p class="msgEmptyTable">x</p></body>'),
    ):
        with pytest.raises(ParseError):
            parse_homework(body.encode(), "fixture")


@pytest.mark.parametrize(
    "parse",
    [
        lambda body: parse_homework(body, "fixture"),
        lambda body: parse_agenda(body, 2026, 10, "fixture"),
        lambda body: parse_completed_lessons(
            body, date(2026, 9, 1), date(2026, 9, 30), 0
        ),
    ],
)
def test_view_disabled_by_school_is_typed_not_parse_failure(
    parse: Callable[[bytes], object],
) -> None:
    with pytest.raises(ViewDisabledError):
        parse(warning_html(VIEW_DISABLED).encode())


@pytest.mark.parametrize(
    "before,after,error",
    [
        ("2026-09-16", "2026-02-30", ParseError),
        ("2026-09-16", "16.09.2026", ParseError),
        ("<td>śr.</td>", "<td>pt.</td>", ParseError),
        ('<td class=" bold">Fixture Teacher</td>', "", ParseError),
        ('class=" bold">Fixture Teacher', 'rowspan="2">Fixture Teacher', ParseError),
        ("<a>Kategoria</a>", "<a>Fixture new column</a>", UnsupportedCapabilityError),
        (
            "/moje_zadania/podglad/456",
            "/moje_zadania/podglad/%34",
            UnsupportedCapabilityError,
        ),
    ],
)
def test_invalid_homework_fails_not_silently_dropped(
    before: str, after: str, error: type[Exception]
) -> None:
    with pytest.raises(error):
        parse_homework(homework_html().replace(before, after, 1).encode(), "fixture")


def test_unknown_homework_handler_fails_instead_of_dropping_reference() -> None:
    body = homework_html().replace(
        "showConfirmQuestion(1, 2);", "openPreview(&quot;\\/moje_zadania&quot;);"
    )
    with pytest.raises(UnsupportedCapabilityError):
        parse_homework(body.encode(), "fixture")


@pytest.mark.parametrize(
    "start,end,valid",
    [
        (date(2026, 9, 1), date(2026, 10, 1), True),
        (date(2026, 9, 1), date(2026, 10, 2), False),
        (date(2026, 1, 31), date(2026, 2, 28), True),
        (date(2026, 1, 31), date(2026, 3, 1), False),
        (date(2026, 10, 2), date(2026, 10, 1), False),
    ],
)
def test_homework_window_is_limited_to_one_calendar_month(
    start: date, end: date, valid: bool
) -> None:
    # The upstream form rejects longer ranges with an inline warning.
    if valid:
        assert homework_form(start, end)["dataDo"] == end.isoformat()
    else:
        with pytest.raises(InvalidInputError):
            homework_form(start, end)


@pytest.mark.parametrize("kind", ["agenda", "homework"])
def test_detail_fields_preserve_long_text_empty_values_header_and_notes(
    kind: str,
) -> None:
    title, fields, notes = parse_school_detail(
        detail_html(kind, "Fixture<br>" + ("x" * 2048)).encode()
    )
    assert title == "Fixture heading"
    assert dict(fields) == {
        "Opis:": "Fixture\n" + "x" * 2048,
        "Fixture unknown label": "",
    }
    assert notes == ("Fixture separate note",)


@pytest.mark.parametrize(
    "before,after",
    [
        ("container-background", "unknown-container"),
        ("Fixture unknown label", "Opis"),
        ("Fixture unknown label", "Opis :"),
        (
            "<td>Fixture<br>complete content</td>",
            '<td colspan="2">Fixture invalid</td>',
        ),
        ("Fixture<br>complete content", "<script>Fixture unsupported()</script>"),
    ],
)
def test_unsafe_or_ambiguous_details_fail(before: str, after: str) -> None:
    with pytest.raises((ParseError, UnsupportedCapabilityError)):
        parse_school_detail(detail_html().replace(before, after).encode())


@pytest.mark.parametrize(
    "bound,value,parser,body",
    [
        ("SCHOOL_MAX_ITEMS", 0, "agenda", agenda_html()),
        ("SCHOOL_MAX_ITEMS", 0, "homework", homework_html()),
        ("SCHOOL_MAX_CONTENT_LENGTH", 10, "detail", detail_html()),
        ("SCHOOL_MAX_DETAIL_FIELDS", 1, "detail", detail_html()),
        ("SCHOOL_MAX_TOTAL_TEXT_LENGTH", 10, "agenda", agenda_html()),
        ("SCHOOL_MAX_TOTAL_TEXT_LENGTH", 10, "homework", homework_html()),
    ],
)
def test_explicit_bounds_fail_without_truncation(
    bound: str, value: int, parser: str, body: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("librus_python_api.school_reads." + bound, value)
    with pytest.raises(LimitError):
        if parser == "agenda":
            parse_agenda(body.encode(), 2026, 10, "fixture")
        elif parser == "homework":
            parse_homework(body.encode(), "fixture")
        else:
            parse_school_detail(body.encode())
