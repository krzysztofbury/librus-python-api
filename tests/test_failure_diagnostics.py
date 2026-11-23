import ast
import asyncio
import importlib
import inspect
import json
import pkgutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn, get_type_hints

import pytest

import librus_python_api
from librus_python_api.attendance_frequency import parse_gateway_attendance
from librus_python_api.diagnostics import (
    _SHAPE_COUNTS,
    RAISE_HELPERS,
    describe_failure,
    failure_frames,
    failure_locator,
)
from librus_python_api.exceptions import ErrorKind, LibrusError, ParseError
from librus_python_api.grade_records import parse_grade_records
from librus_python_api.inspect_page import main
from librus_python_api.models import DiagnosticEvent
from librus_python_api.parsers import parse_profile
from tests.attendance_support import gateway_rows
from tests.grade_records_support import (
    GradeRecordsFixture,
    behaviour_row,
    formative_table,
    grade_box,
    grades_html,
)
from tests.http_support import SchoolFixture, profile_html, serve

SECRET = "ZZSECRETZZ"


def _sentinel_page() -> str:
    """Private-looking values everywhere, and a tooltip line the parser rejects.

    The failing anchor and the cell around it carry the marker in every place
    a value could leak from: text, attributes, class, id, tag and attribute
    names.
    """
    box = (
        grade_box(
            SECRET + "grade",
            extra=f"Komentarz: {SECRET}comment<br>Waga: 2<br>Uwaga {SECRET}line"
            f"<br>{SECRET}label: {SECRET}value",
            href=f"/przegladaj_oceny/szczegoly/123?q={SECRET}query",
        )
        .replace(
            "<a ",
            f'<a id="przedmioty_OP_{SECRET}_node" class="line0 {SECRET.lower()}" '
            f'data-{SECRET.lower()}="{SECRET}" onclick="{SECRET}()" ',
        )
        .replace("</a>", f"<{SECRET.lower()}>{SECRET}</{SECRET.lower()}></a>")
    )
    return grades_html(first=box, subject=f"Subject {SECRET}subject").replace(
        "<td></td><td>Subject",
        f'<td id="Kowalski_{SECRET}" class="line0 Kowalski {SECRET.lower()}"></td>'
        "<td>Subject",
    )


def _failure(body: str) -> LibrusError:
    with pytest.raises(LibrusError) as caught:
        parse_grade_records(body.encode())
    return caught.value


def test_frames_name_the_failure_site_after_the_service_boundary() -> None:
    # The traceback survives the parser thread, single flight and re-raise.
    events: list[DiagnosticEvent] = []

    async def scenario() -> LibrusError:
        fixture = GradeRecordsFixture()
        fixture.grade_body = _sentinel_page()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(diagnostic_sink=events.append) as service:
                with pytest.raises(ParseError) as caught:
                    await service.account("student").grades()
                return caught.value

    error = asyncio.run(scenario())
    frames = failure_frames(error)
    assert frames[-1].startswith("markup:tooltip_fields:")
    assert frames[-2].startswith("grade_records:_numeric:")
    assert all(SECRET not in frame for frame in frames)
    (event,) = [event for event in events if event.outcome is ErrorKind.PARSE]
    assert event.frames == frames


def test_events_carry_the_http_status_a_read_failed_on() -> None:
    # A 2xx other than 200 (4xx and 5xx fail in the transport) or a 200 of
    # another media type fails as PARSE; the event says which status it was.
    events: list[DiagnosticEvent] = []

    async def scenario() -> None:
        fixture = SchoolFixture()
        fixture.profile_status["student"] = 204
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with fixture.service(diagnostic_sink=events.append) as service:
                with pytest.raises(ParseError):
                    await service.account("student").student_information()
                del fixture.profile_status["student"]
                await service.account("student").student_information()

    asyncio.run(scenario())
    failed, succeeded = [e for e in events if e.operation == "student_information"]
    assert (failed.outcome, failed.http_status) == (ErrorKind.PARSE, 204)
    assert "_validate_read_response" in failed.frames[-1]
    assert (succeeded.outcome, succeeded.http_status) == ("ok", 200)


def test_a_raise_helper_is_not_the_failure_site() -> None:
    table = formative_table().replace(
        '<td class="center no-border-left">1</td>',
        '<td class="center no-border-left"><b>1</b></td>',
        1,
    )
    error = _failure(grades_html(extra=table))
    assert error.kind is ErrorKind.UNSUPPORTED_CAPABILITY
    assert failure_frames(error)[-1].startswith("formative_grades:_plain:")


def test_every_no_return_raiser_is_a_registered_helper() -> None:
    """Module-level functions annotated `-> NoReturn` only; methods, nested
    helpers and `-> Never` are not covered (none exist today)."""
    raisers = set()
    for module_info in pkgutil.iter_modules(librus_python_api.__path__):
        name = f"librus_python_api.{module_info.name}"
        try:
            module = importlib.import_module(name)
        except ImportError:  # Platform-only modules such as the Windows one.
            continue
        for function_name, function in inspect.getmembers(module, inspect.isfunction):
            if function.__module__ != name:
                continue
            try:
                hints = get_type_hints(function)
            except Exception:
                continue
            if hints.get("return") is NoReturn:
                raisers.add((name, function_name))
    assert raisers == set(RAISE_HELPERS)


def test_a_suppressed_inner_failure_still_shows_where_it_happened() -> None:
    def inner() -> None:
        raise ValueError(SECRET)

    try:
        try:
            inner()
        except ValueError:
            raise LibrusError(ErrorKind.PARSE) from None
    except LibrusError as error:
        frames = failure_frames(error, packages=("tests",))
    assert [frame.split(":")[1] for frame in frames][-1].endswith("inner")
    assert all(SECRET not in frame for frame in frames)


def test_failure_report_keeps_structure_and_masks_every_value() -> None:
    report = describe_failure(_failure(_sentinel_page()))
    assert report is not None
    assert SECRET.casefold() not in report.casefold()
    assert "at markup:tooltip_fields:" in report
    assert "span.grade-box[1] > a.line0.?10[1]" in report
    assert "[Komentarz], [Waga], NO-COLON(len=" in report
    assert "LABEL?(len=" in report
    assert "Kowalski" not in report


def test_the_locator_names_the_failing_cell_and_the_widths_without_values() -> None:
    # A behaviour row one column wider than the header because of a cell
    # before the last, which stays unsupported; every value is the marker.
    row = (
        '<tr class="bolded line0"><td class="center micro screen-only"></td>'
        f'<td>Zachowanie</td><td colspan="4">{SECRET}a</td>'
        f'<td class="center">{SECRET}b</td><td colspan="2">{SECRET}c</td>'
        f'<td>{SECRET}d</td><td class="center">{SECRET}e</td></tr>'
    )
    error = _failure(grades_html(rows=row))
    assert failure_locator(error) == (
        "table.stretch.decorated[1] > tbody[1] > tr.bolded.line0[2] > "
        "td.center[7]; cells 7, columns 11, width 10, span 1"
    )
    report = describe_failure(error)
    assert report is not None and "\nwidth: 10\n" in report
    assert SECRET not in report
    assert failure_locator(ValueError(SECRET)) is None


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param(
            lambda rows: rows[1].pop("Lesson"),
            "wire Attendances[1].Lesson missing",
            id="missing",
        ),
        pytest.param(
            lambda rows: rows[2].update(Semester=SECRET),
            "wire Attendances[2].Semester value_error",
            id="semester",
        ),
        pytest.param(
            lambda rows: rows[0].update(LessonNo=100, Type={"Id": SECRET}),
            "wire Attendances[0].Type.Id string_pattern_mismatch; "
            "Attendances[0].LessonNo less_than_equal",
            id="two-fields",
        ),
    ],
)
def test_a_gateway_envelope_failure_names_its_field_and_rule_only(
    change: Callable[[list[dict[str, Any]]], object], expected: str
) -> None:
    # librus-mcp#136: the attendance gateway failed validation and nothing said
    # which field; the report shows wire field names and rule types, no value.
    payload = json.loads(gateway_rows())
    change(payload["Attendances"])
    with pytest.raises(ParseError) as caught:
        parse_gateway_attendance(json.dumps(payload).encode())
    assert failure_locator(caught.value) == expected
    assert describe_failure(caught.value) == expected
    assert SECRET not in expected


def test_a_body_that_is_no_envelope_is_named_as_the_body() -> None:
    with pytest.raises(ParseError) as caught:
        parse_gateway_attendance(json.dumps([SECRET]).encode())
    assert failure_locator(caught.value) == "wire (body) model_type"


# Every binding of a name `describe_failure` and `failure_locator` show as a
# layout count. Each was checked to hold a column count, span or position,
# never a value read from page text (formative_grades' `span` is a string and
# is skipped). Add a new one only after the same check.
_REVIEWED_LAYOUT_BINDINGS = {
    "completed_lessons:_closing_row:width=arg",
    "completed_lessons:_optional_columns:position",
    "completed_lessons:_optional_columns:span",
    "formative_grades:read_formative_table:span",
    "grade_parsers:_candidates:width",
    "grade_parsers:_header:position",
    "grade_parsers:_header:span",
    "grade_parsers:_subject_columns:span",
    "grade_parsers:_subject_columns:width=arg",
    "grade_parsers:_subject_rows:width=arg",
    "grade_parsers:_summary:width=arg",
    "grade_parsers:parse_final_grades:width",
    "grade_records:_layout:position",
    "grade_records:_period_columns:position",
    "grade_records:_read_numeric_table:width",
    "markup:colspan:span",
    "message_content:_recipient_receipts:width",
    "messages:_header:width",
    "messages:_summary:width=arg",
    "messages:parse_messages:width",
    "school_reads:_homework_columns:span",
}


def test_layout_counts_shown_in_diagnostics_come_from_reviewed_bindings() -> None:
    root = Path(librus_python_api.__file__).parent
    found = set()
    for path in sorted(root.glob("*.py")):
        if path.stem == "diagnostics":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = function.args
            for argument in (
                arguments.posonlyargs + arguments.args + arguments.kwonlyargs
            ):
                if argument.arg in _SHAPE_COUNTS:
                    found.add(f"{path.stem}:{function.name}:{argument.arg}=arg")
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Name)
                    and isinstance(node.ctx, ast.Store)
                    and node.id in _SHAPE_COUNTS
                ):
                    found.add(f"{path.stem}:{function.name}:{node.id}")
    assert found == _REVIEWED_LAYOUT_BINDINGS


def test_only_observed_id_shapes_and_lowercase_classes_are_shown() -> None:
    table = (
        '<table class="decorated stretch"><tbody><tr class="line0 Kowalski">'
        '<td id="przedmioty_OP_96760_node" class="center micro screen-only"></td>'
        '<td id="Jan_Kowalski_7"><span class="grade-box"><a title="Waga: x">1</a>'
        "</span></td></tr></tbody></table>"
    )
    page = grades_html(extra=table)
    report = describe_failure(_failure(page))
    assert report is not None
    assert "kowalski" not in report.casefold() and "jan" not in report.casefold()


def test_failure_report_is_bounded_and_never_raises() -> None:
    entries = "".join(grade_box(f"{SECRET}{n}") for n in range(400))
    # A missing second current-grade header fails with the whole table local.
    page = grades_html(first=entries).replace(
        '<th>Oceny bieżące</th><th title="Średnia ocen z drugiego',
        '<th>X</th><th title="Średnia ocen z drugiego',
    )
    report = describe_failure(_failure(page))
    assert report is not None and "..." in report
    assert len(report.encode()) <= 32 * 1024
    assert SECRET not in report
    assert describe_failure(ValueError(SECRET)) is None
    assert failure_frames(ValueError(SECRET)) == ()


def test_a_correction_bracket_is_shown_and_its_grades_stay_masked() -> None:
    group = (
        "<span>["
        + grade_box(f"{SECRET}1", href="/przegladaj_oceny/szczegoly/11")
        + grade_box(f"{SECRET}5", href="/przegladaj_oceny/szczegoly/12")
        + "]</span>"
    )
    # A missing second current-grade header fails with the whole table local.
    page = grades_html(first=group).replace(
        '<th>Oceny bieżące</th><th title="Średnia ocen z drugiego',
        '<th>X</th><th title="Średnia ocen z drugiego',
    )
    report = describe_failure(_failure(page))
    assert report is not None
    assert (
        "<td><span>'['<span class=grade-box>...</span>"
        "<span class=grade-box>...</span>']'</span></td>"
    ) in report
    assert SECRET not in report


@pytest.mark.parametrize("fragment", [False, True])
def test_inspect_page_reports_counts_or_the_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fragment: bool
) -> None:
    good = tmp_path / "good.html"
    body = grades_html(rows=behaviour_row())
    good.write_text(body.split("<body>")[1] if fragment else body, encoding="utf-8")
    assert main(["grades", str(good)]) == 0
    output = capsys.readouterr().out
    assert "OK numeric=1" in output and "descriptive_table=0" in output
    assert "behaviour_points=2, behaviour_point_entries=1" in output
    assert ("fragment" in output) is fragment
    bad = tmp_path / "bad.html"
    bad.write_text(_sentinel_page(), encoding="utf-8")
    assert main(["grades", str(bad)]) == 1
    output = capsys.readouterr().out
    assert "FAILED parse" in output and "at markup:tooltip_fields:" in output
    assert SECRET.casefold() not in output.casefold()


def test_inspect_page_applies_the_parse_size_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    large = tmp_path / "large.html"
    large.write_bytes(b"<html>" + b" " * (256 * 1024) + b"</html>")
    assert main(["final-grades", str(large)]) == 1
    assert "FAILED limit" in capsys.readouterr().out
    assert main(["grades", str(tmp_path / "missing.html")]) == 2


def test_inspect_page_names_a_non_utf8_file_instead_of_a_layout_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "page.html"
    page.write_bytes(grades_html(subject="Język").encode("utf-16"))
    assert main(["grades", str(page)]) == 1
    assert "not UTF-8" in capsys.readouterr().out


def test_inspect_page_summarizes_a_page_that_fails_as_a_whole(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "page.html"
    page.write_text(profile_html(), encoding="utf-8")
    assert main(["profile", str(page)]) == 0
    assert "OK lucky_number=1" in capsys.readouterr().out
    # No five-label table: an unknown tutor label, an unknown notice, and
    # private values in every cell, attribute and in the head.
    failing = (
        profile_html(school=f"{SECRET}school")
        .replace("Wychowawca", f"{SECRET}label")
        .replace("<body>", f'<body><div class="warning-content">{SECRET}</div>')
        .replace("<html>", f"<html><head><title>{SECRET}</title></head>")
        .replace("<table>", f'<table class="decorated {SECRET.lower()}">')
        .replace(
            "</table>",
            f'<tr><td colspan="{SECRET}">x</td></tr>'
            f"<tr><th>Login</th><td>{SECRET}</td></tr></table>",
        )
    )
    page.write_text(failing, encoding="utf-8")
    assert main(["profile", str(page)]) == 1
    output = capsys.readouterr().out
    assert SECRET.casefold() not in output.casefold()
    assert "document: page" in output and "notices: 1 TEXT(len=" in output
    assert "th['Klasa'] td[TEXT(len=6)]" in output
    assert f"th[TEXT(len={len(SECRET) + 5})]" in output
    assert "th['Login'] td[TEXT(len=" in output and "table.decorated.?10" in output
    page.write_text(
        '<html><head><meta name="Generator" content="Cocoa HTML Writer"></head>'
        f"<body><p>&lt;html&gt;{SECRET}</p></body></html>",
        encoding="utf-8",
    )
    assert main(["profile", str(page)]) == 1
    assert "saved as a text document" in capsys.readouterr().out


def test_a_page_summary_tells_a_login_page_apart_and_stays_bounded() -> None:
    login = (
        "<html><head><title>Login</title></head><body><h1>Login</h1>"
        f'<form action="/OAuth/Authorization?q={SECRET}"><input name="login">'
        f'<input type="password" value="{SECRET}"><input type="{SECRET}"></form>'
        "</body></html>"
    )
    with pytest.raises(LibrusError) as caught:
        parse_profile(login.encode())
    report = describe_failure(caught.value)
    assert report is not None and SECRET.casefold() not in report.casefold()
    assert "graphic-menu=no user-section=no" in report
    assert "forms: 1 <other len" in report and "inputs ?=1 password=1 text=1" in report
    # Large tables before the student table: the summary is cut, the
    # failing row still shown first.
    cells = "".join(f"<td>{SECRET}</td>" for _ in range(8))
    rows = "".join(f"<tr>{cells}</tr>" for _ in range(40))
    page = (
        profile_html()
        .replace("Wychowawca", "X")
        .replace("<table>", f"<table>{rows}</table>" * 6 + "<table>")
    )
    with pytest.raises(LibrusError) as caught:
        parse_profile(page.encode())
    report = describe_failure(caught.value)
    assert report is not None and SECRET not in report
    assert report.index("row: ") < report.index("document: page")
    assert "...(truncated)" in report and len(report.encode()) <= 32 * 1024
