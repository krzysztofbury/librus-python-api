"""Opt-in, original-response comparison with an external unmodified apix install.

This is synthetic differential evidence, not live upstream qualification. The
baseline is neither a package dependency nor a source/fixture ownership oracle.
"""

import asyncio
import base64
import hashlib
import importlib
import os
import socket
import sys
from collections.abc import Callable
from datetime import date
from importlib.metadata import distribution
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from librus_python_api import (
    AccountClient,
    AccountCredentials,
    Agenda,
    ConnectionSettings,
    Homework,
    HomeworkItem,
    LibrusService,
    RequestBudget,
    SchedulerLimits,
    SchoolDetail,
    SchoolReference,
)
from librus_python_api.config import Endpoint
from librus_python_api.exceptions import LibrusError
from librus_python_api.models import RequestForm, TransportResponse
from librus_python_api.school_reads import (
    parse_agenda,
    parse_homework,
    parse_school_detail,
)
from librus_python_api.transport import AiohttpTransport
from tests.http_support import FIXTURE_SECRET, serve
from tests.school_reads_support import (
    SchoolReadsFixture,
    agenda_html,
    detail_html,
    homework_html,
)

pytestmark = pytest.mark.integration


class OfflineResponseClient:
    """Supply identical original bytes without constructing an authenticated client."""

    SCHEDULE_URL = "https://offline.invalid/terminarz/"
    HOMEWORK_URL = "https://offline.invalid/moje_zadania"
    HOMEWORK_DETAILS_URL = "https://offline.invalid/moje_zadania/podglad/"

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def get(self, url: str) -> SimpleNamespace:
        assert url in {
            self.SCHEDULE_URL + "szczegoly/123",
            self.HOMEWORK_DETAILS_URL + "456",
        }
        self.calls.append(("GET", url, None))
        return SimpleNamespace(text=self.body.decode())

    def post(self, url: str, data: dict[str, str]) -> SimpleNamespace:
        expected = (
            {"rok": "2026", "miesiac": "10"}
            if url == self.SCHEDULE_URL
            else {
                "dataOd": "2026-09-01",
                "dataDo": "2026-10-31",
                "przedmiot": "-1",
                "status": "-1",
            }
        )
        assert url in {self.SCHEDULE_URL, self.HOMEWORK_URL}
        assert data == expected
        self.calls.append(("POST", url, data))
        return SimpleNamespace(text=self.body.decode())


@pytest.fixture
def baseline(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, ModuleType]:
    location = os.environ.get("LIBRUS_APIX_SITE_PACKAGES")
    if not location:
        pytest.skip("Set LIBRUS_APIX_SITE_PACKAGES to an external apix 1.5.3 install")
    path = Path(location).resolve()
    assert (path / "librus_apix").is_dir()
    monkeypatch.setattr(sys, "path", [*sys.path, str(path)])
    metadata = distribution("librus-apix")
    assert metadata.version == "1.5.3"
    for item in metadata.files or ():
        if item.suffix == ".py" and item.hash is not None:
            assert item.hash.mode == "sha256"
            digest = hashlib.sha256(metadata.locate_file(item).read_bytes()).digest()
            assert (
                base64.urlsafe_b64encode(digest).decode().rstrip("=") == item.hash.value
            )
    modules = tuple(
        importlib.import_module("librus_apix." + n) for n in ("schedule", "homework")
    )
    for module in modules:
        assert module.__file__ is not None
        assert Path(module.__file__).resolve().is_relative_to(path)
    return modules[0], modules[1]


@pytest.fixture(autouse=True)
def no_external_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    original = socket.socket.connect
    original_lookup = socket.getaddrinfo

    def connect(sock: socket.socket, address: Any) -> None:
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            assert address[0] in {"127.0.0.1", "::1"}, "External connection forbidden"
        original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)

    def lookup(host: Any, *args: Any, **kwargs: Any) -> Any:
        assert host in {"127.0.0.1", "::1", "localhost", None}, "External DNS forbidden"
        return original_lookup(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", lookup)


def canonical_homework() -> str:
    # The original fixture exercises class reordering. This case instead supplies
    # the canonical class order required by the baseline's positional selection.
    return homework_html().replace(
        "myHomeworkTable decorated", "decorated myHomeworkTable"
    )


def homework_projection(item: HomeworkItem) -> tuple[str, ...]:
    return (
        item.lesson,
        item.teacher,
        item.subject,
        item.category,
        item.assigned.raw_day + " " + item.assigned.raw_clock,
        item.due.raw_day + " " + item.due.raw_clock,
        item.reference.identifier if item.reference else "",
    )


def baseline_homework_projection(item: Any) -> tuple[str, ...]:
    return (
        item.lesson,
        item.teacher,
        item.subject,
        item.category,
        item.task_date,
        item.completion_date,
        item.href,
    )


@pytest.mark.parametrize(
    "variant", ["populated", "two_rows", "missing_clock", "extra_cells", "empty"]
)
def test_homework_common_fields_and_dates_match(
    baseline: tuple[ModuleType, ModuleType], variant: str
) -> None:
    _, homework = baseline
    body = canonical_homework()
    if variant == "two_rows":
        start = body.index('<tr class="line0">')
        end = body.index("</tr>", start) + len("</tr>")
        row = (
            body[start:end]
            .replace("line0", "line1")
            .replace("456", "457")
            .replace("Fixture topic", "Fixture second topic")
        )
        body = body.replace("</tbody>", row + "</tbody>")
    elif variant == "missing_clock":
        body = body.replace("08:15", "").replace("2026-10-03", "-")
    elif variant == "extra_cells":
        body = body.replace(
            "</td></tr></tbody>", "</td><td>Fixture status</td></tr></tbody>"
        )
    elif variant == "empty":
        body = '<html><p class="msgEmptyTable">Fixture no assignments</p></html>'
    data = body.encode()
    native = parse_homework(data, "fixture")
    client = OfflineResponseClient(data)
    old = homework.get_homework(client, "2026-09-01", "2026-10-31")
    assert [homework_projection(i) for i in native] == [
        baseline_homework_projection(i) for i in old
    ]
    assert len(native) == (
        0 if variant == "empty" else 2 if variant == "two_rows" else 1
    )
    if variant == "extra_cells":
        assert native[0].extra_cells == ("", "Fixture status")
    if variant == "two_rows":
        assert [i.lesson for i in native] == ["Fixture topic", "Fixture second topic"]
    if variant == "missing_clock":
        assert native[0].assigned.clock is None and native[0].due.day is None
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "variant",
    ["class_order", "linkless", "double_quote_reference", "line_break", "invalid_date"],
)
def test_homework_baseline_departures_are_explicit(
    baseline: tuple[ModuleType, ModuleType], variant: str
) -> None:
    _, homework = baseline
    body = canonical_homework()
    if variant == "class_order":
        body = homework_html()
    elif variant == "linkless":
        start = body.index('<input type="button"')
        end = body.index(">", start) + 1
        body = body[:start] + body[end:]
    elif variant == "double_quote_reference":
        body = body.replace(
            "open('/moje_zadania/podglad/456')",
            "open(&quot;/moje_zadania/podglad/456&quot;)",
        )
    elif variant == "line_break":
        body = body.replace("Fixture topic", "Fixture<br>topic")
    else:
        body = body.replace("2026-09-01", "2026-02-30")
    data = body.encode()
    client = OfflineResponseClient(data)
    if variant == "invalid_date":
        with pytest.raises(LibrusError) as failure:
            parse_homework(data, "fixture")
        assert failure.value.kind == "parse"
        assert (
            homework.get_homework(client, "2026-09-01", "2026-10-31")[0].task_date
            == "2026-02-30 08:15"
        )
        return
    native = parse_homework(data, "fixture")[0]
    if variant in {"class_order", "linkless"}:
        with pytest.raises(Exception) as baseline_failure:
            homework.get_homework(client, "2026-09-01", "2026-10-31")
        assert type(baseline_failure.value).__name__ == (
            "ParseError" if variant == "class_order" else "AttributeError"
        )
        assert native.lesson == "Fixture topic"
        assert (
            native.reference is None
            if variant == "linkless"
            else native.reference is not None
        )
    else:
        old = homework.get_homework(client, "2026-09-01", "2026-10-31")[0]
        if variant == "double_quote_reference":
            assert native.reference == SchoolReference("homework", "456", "fixture")
            assert old.href == ""
        else:
            assert native.lesson == "Fixture topic" and old.lesson == "Fixturetopic"


@pytest.mark.parametrize("kind", ["agenda", "homework"])
@pytest.mark.parametrize(
    "value,expected",
    [
        ("Fixture content", "Fixture content"),
        ("", ""),
        ("Fixture long " + "x" * 2048, "Fixture long " + "x" * 2048),
        ("Fixture<br>content", "Fixture\ncontent"),
        ("<p>Fixture first</p><p>Fixture second</p>", "Fixture first\nFixture second"),
    ],
)
def test_detail_fields_long_text_and_rendered_boundaries(
    baseline: tuple[ModuleType, ModuleType], kind: str, value: str, expected: str
) -> None:
    schedule, homework = baseline
    body = detail_html(kind, value).encode()
    title, fields, notes = parse_school_detail(body)
    client = OfflineResponseClient(body)
    old = (
        schedule.schedule_detail(client, "szczegoly", "123")
        if kind == "agenda"
        else homework.homework_detail(client, "456")
    )
    assert title == "Fixture heading" and notes == ("Fixture separate note",)
    assert dict(fields) == {"Opis:": expected, "Fixture unknown label": ""}
    assert list(old) == ["Opis:", "Fixture unknown label"]
    assert old["Fixture unknown label"] == ""
    if "<br>" in value or "<p>" in value:
        assert old["Opis:"] == expected.replace("\n", "")
        assert old["Opis:"] != expected
    else:
        assert old == dict(fields)
    assert len(client.calls) == 1


@pytest.mark.parametrize("kind", ["agenda", "homework"])
@pytest.mark.parametrize(
    "variant", ["duplicate", "missing_container", "active_content"]
)
def test_detail_integrity_is_not_weakened_for_baseline_parity(
    baseline: tuple[ModuleType, ModuleType], kind: str, variant: str
) -> None:
    schedule, homework = baseline
    body = detail_html(kind)
    if variant == "duplicate":
        body = body.replace("Fixture unknown label", "Opis:")
    elif variant == "missing_container":
        body = body.replace("container-background", "unknown-container")
    else:
        body = body.replace(
            "Fixture<br>complete content", "<script>Fixture unsafe()</script>"
        )
    data = body.encode()
    with pytest.raises(LibrusError) as failure:
        parse_school_detail(data)
    assert failure.value.kind == (
        "unsupported_capability" if variant == "active_content" else "parse"
    )
    client = OfflineResponseClient(data)
    operation: Callable[[], dict[str, str]] = (
        (lambda: schedule.schedule_detail(client, "szczegoly", "123"))
        if kind == "agenda"
        else (lambda: homework.homework_detail(client, "456"))
    )
    if variant == "missing_container":
        with pytest.raises(schedule.ParseError) as baseline_failure:
            operation()
        assert type(baseline_failure.value).__name__ == "ParseError"
    else:
        old = operation()
        assert old["Opis:"] == ""


AGENDA_CELLS = {
    "empty": "",
    "inline_subject": (
        "<td>Nr: 4, <span>Fixture Biology</span><br>Fixture quiz, revision</td>"
    ),
    "standalone_subject": (
        "<td>Nr: 4<br><span>Fixture Biology</span><br>Fixture quiz</td>"
    ),
    "clock": "<td>09:30<br>Fixture meeting</td>",
    "subjectless": "<td>Fixture closure<br>Fixture explanation</td>",
    "tooltip_notes": (
        '<td title="Opis: Fixture detail&lt;br /&gt;'
        'Fixture flag&lt;br /&gt;">Fixture closure</td>'
    ),
    "tooltip_break_alias": (
        '<td title="Nauczyciel: Fixture Teacher&lt;br&gt;'
        'Opis: Fixture detail">Fixture closure</td>'
    ),
}


@pytest.mark.parametrize("variant", AGENDA_CELLS)
def test_agenda_missing_live_variants_against_unmodified_baseline(
    baseline: tuple[ModuleType, ModuleType], variant: str
) -> None:
    schedule, _ = baseline
    data = agenda_html(cell=AGENDA_CELLS[variant]).encode()
    native = parse_agenda(data, 2026, 10, "fixture")
    client = OfflineResponseClient(data)
    old = schedule.get_schedule(client, "10", "2026", include_empty=True)
    assert len(native) == len(old) == 31
    assert (
        sum(len(d.events) for d in native)
        == sum(map(len, old.values()))
        == (0 if variant == "empty" else 1)
    )
    if variant == "empty":
        return
    event, legacy = native[1].events[0], old[2][0]
    if variant == "inline_subject":
        assert (
            event.title == "Fixture quiz, revision"
            and legacy.title == "Fixture quizrevision"
        )
        assert event.subject == legacy.subject == "Fixture Biology"
        assert event.lesson_number == legacy.number == 4
    elif variant == "standalone_subject":
        assert event.title == "Fixture quiz" and legacy.title == ""
        assert event.subject == legacy.subject == "Fixture Biology"
    elif variant == "clock":
        assert event.at_time is not None and event.at_time.isoformat() == "09:30:00"
        assert (
            event.lesson_number is None
            and legacy.number == "unknown"
            and legacy.hour == "09:30"
        )
    elif variant == "subjectless":
        assert (
            event.title == "Fixture closure" and legacy.title == "Fixture explanation"
        )
        assert event.subject is None and legacy.subject == "Fixture closure"
    elif variant == "tooltip_notes":
        assert event.metadata == (("Opis", "Fixture detail"),)
        assert event.metadata_notes == ("Fixture flag",)
        assert legacy.data == {
            "Opis": "Fixture detail",
            "Fixture flag": "unknown",
            "": "unknown",
        }
    else:
        assert dict(event.metadata) == {
            "Nauczyciel": "Fixture Teacher",
            "Opis": "Fixture detail",
        }
        assert legacy.data == {"Nauczyciel": "Fixture Teacher<br>Opis: Fixture detail"}
    assert len(client.calls) == 1


async def read_four_public_apis(
    account: AccountClient,
) -> tuple[Agenda, SchoolDetail, Homework, SchoolDetail]:
    agenda = await account.agenda(2026, 10)
    reference = agenda.days[1].events[0].reference
    assert reference is not None
    event_detail = await account.agenda_detail(reference)
    assignments = await account.homework(date(2026, 9, 1), date(2026, 10, 31))
    reference = assignments.items[0].reference
    assert reference is not None
    assignment_detail = await account.homework_detail(reference)
    return agenda, event_detail, assignments, assignment_detail


def assert_public_baseline(
    baseline: tuple[ModuleType, ModuleType],
    captured: dict[str, bytes],
    results: tuple[Agenda, SchoolDetail, Homework, SchoolDetail],
) -> None:
    schedule, homework = baseline
    agenda, event_detail, assignments, assignment_detail = results
    old_agenda = schedule.get_schedule(
        OfflineResponseClient(captured["agenda"]),
        "10",
        "2026",
        include_empty=True,
    )
    assert agenda.days[1].events[0].title == old_agenda[2][0].title == "Fixture quiz"
    old_homework = homework.get_homework(
        OfflineResponseClient(captured["homework"]),
        "2026-09-01",
        "2026-10-31",
    )
    assert homework_projection(assignments.items[0]) == baseline_homework_projection(
        old_homework[0]
    )
    assert dict(event_detail.fields) == schedule.schedule_detail(
        OfflineResponseClient(captured["agenda_detail"]),
        "szczegoly",
        "123",
    )
    assert dict(assignment_detail.fields) == homework.homework_detail(
        OfflineResponseClient(captured["homework_detail"]),
        "456",
    )


def test_public_reads_and_returned_details_use_identical_bytes(
    baseline: tuple[ModuleType, ModuleType],
) -> None:
    captured: dict[str, bytes] = {}

    class CaptureTransport(AiohttpTransport):
        async def _exchange(
            self,
            endpoint: Endpoint,
            url: str,
            budget: RequestBudget,
            form: RequestForm,
        ) -> TransportResponse:
            response = await super()._exchange(endpoint, url, budget, form)
            if endpoint.operation_id in {
                "agenda",
                "agenda_detail",
                "homework",
                "homework_detail",
            }:
                captured[endpoint.operation_id] = response.body
            return response

    async def scenario() -> None:
        fixture = SchoolReadsFixture()
        fixture.bodies.update(
            agenda=agenda_html(
                cell="<td onclick=\"open('/terminarz/szczegoly/123')\">"
                "Nr: 4<br>Fixture quiz</td>"
            ),
            homework=canonical_homework(),
            agenda_detail=detail_html("agenda", "Fixture content"),
            homework_detail=detail_html("homework", "Fixture content"),
        )
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            async with LibrusService(
                {
                    "student": AccountCredentials(
                        login="student", password=FIXTURE_SECRET
                    )
                },
                connection=ConnectionSettings(
                    synergia_origin=origin, api_origin=origin
                ),
                scheduler_limits=SchedulerLimits(requests_per_second=1000, burst=16),
                transport_factory=CaptureTransport,
            ) as service:
                results = await read_four_public_apis(service.account("student"))
                assert_public_baseline(baseline, captured, results)
                assert len(fixture.forms) == len(fixture.detail_gets) == 2
                assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())
