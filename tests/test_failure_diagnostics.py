import asyncio
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import NoReturn, get_type_hints

import pytest

import librus_python_api
from librus_python_api.diagnostics import (
    RAISE_HELPERS,
    describe_failure,
    failure_frames,
)
from librus_python_api.exceptions import ErrorKind, LibrusError, ParseError
from librus_python_api.grade_records import parse_grade_records
from librus_python_api.inspect_page import main
from librus_python_api.models import DiagnosticEvent
from librus_python_api.parsers import parse_profile
from tests.grade_records_support import (
    GradeRecordsFixture,
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


@pytest.mark.parametrize("fragment", [False, True])
def test_inspect_page_reports_counts_or_the_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fragment: bool
) -> None:
    good = tmp_path / "good.html"
    body = grades_html()
    good.write_text(body.split("<body>")[1] if fragment else body, encoding="utf-8")
    assert main(["grades", str(good)]) == 0
    output = capsys.readouterr().out
    assert "OK numeric=1" in output
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
