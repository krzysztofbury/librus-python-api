"""One loopback fixture serving every catalogued read with original markup."""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import date
from typing import Any

from aiohttp import web

from librus_python_api import (
    AccountClient,
    MessageFolder,
    MessageReference,
    RecipientGroupReference,
    SchoolReference,
)
from librus_python_api.config import ENDPOINTS
from tests.announcements_support import announcement_table, page
from tests.attendance_support import DETAIL, attendance_html, gateway_rows
from tests.completed_lessons_support import lessons_html
from tests.grade_records_support import grades_html
from tests.grade_support import summary_html
from tests.http_support import SchoolFixture, profile_html
from tests.message_content_support import content_html
from tests.messages_support import message_row, messages_html
from tests.recipients_support import groups_html, recipient_html
from tests.school_reads_support import agenda_html, detail_html, homework_html
from tests.school_year_archive_support import archive_page
from tests.timetable_support import MONDAY, timetable_html

HTML, JSON = "text/html", "application/json"
VALID: dict[str, tuple[bytes, str]] = {
    "student_information": (profile_html().encode(), HTML),
    "final_grades": (summary_html().encode(), HTML),
    "grades": (grades_html().encode(), HTML),
    "attendance": (attendance_html().encode(), HTML),
    "attendance_detail": (DETAIL.encode(), HTML),
    "gateway_attendance": (gateway_rows(), JSON),
    "timetable": (timetable_html().encode(), HTML),
    "announcements": (page(announcement_table()).encode(), HTML),
    "agenda": (agenda_html().encode(), HTML),
    "agenda_detail": (detail_html("agenda").encode(), HTML),
    "homework": (homework_html().encode(), HTML),
    "homework_detail": (detail_html("homework").encode(), HTML),
    "completed_lessons": (lessons_html().encode(), HTML),
    "messages_received": (messages_html(count=3).encode(), HTML),
    "messages_sent": (messages_html(MessageFolder.SENT, count=3).encode(), HTML),
    "message_content_received": (content_html().encode(), HTML),
    "message_content_sent": (content_html(MessageFolder.SENT).encode(), HTML),
    "recipient_groups": (groups_html().encode(), HTML),
    "recipients": (recipient_html().encode(), HTML),
    "school_year_archive": (archive_page().encode(), HTML),
}
OPERATIONS = tuple(VALID)


def selected(operation: str, form: dict[str, Any]) -> tuple[bytes, str]:
    """Render the month or week the form actually selected."""
    if operation == "agenda":
        body = agenda_html(int(form["rok"]), int(form["miesiac"]))
        return body.encode(), HTML
    if operation == "timetable":
        monday = date.fromisoformat(str(form["tydzien"]).partition("_")[0])
        return timetable_html(monday).encode(), HTML
    if operation.startswith("messages_"):
        folder = MessageFolder(operation.removeprefix("messages_"))
        number = int(form["numer_strony105"])
        items = message_row(str(101 + number * 2), folder=folder) + message_row(
            str(102 + number * 2), folder=folder
        )
        return messages_html(folder, page=number, count=3, rows=items).encode(), HTML
    return VALID[operation]


HTML_OPERATIONS = tuple(op for op, (_, kind) in VALID.items() if kind == HTML)

type Read = Callable[..., Coroutine[Any, Any, Any]]


def read(client: AccountClient, alias: str, operation: str) -> Read:
    """The public call for an operation, with a valid selection."""
    selections: dict[str, Read] = {
        "attendance_detail": lambda **kw: client.attendance_detail("2468", **kw),
        "timetable": lambda **kw: client.timetable(MONDAY, **kw),
        "agenda": lambda **kw: client.agenda(2026, 10, **kw),
        "agenda_detail": lambda **kw: client.agenda_detail(
            SchoolReference("agenda", "123", alias), **kw
        ),
        "homework": lambda **kw: client.homework(
            date(2026, 9, 1), date(2026, 9, 30), **kw
        ),
        "homework_detail": lambda **kw: client.homework_detail(
            SchoolReference("homework", "456", alias), **kw
        ),
        "completed_lessons": lambda **kw: client.completed_lessons_page(
            date(2026, 10, 1), date(2026, 10, 31), **kw
        ),
        "messages_received": lambda **kw: client.messages_page(
            MessageFolder.RECEIVED, **kw
        ),
        "messages_sent": lambda **kw: client.messages_page(MessageFolder.SENT, **kw),
        "message_content_received": lambda **kw: client.message_content(
            MessageReference(MessageFolder.RECEIVED, "101", alias),
            allow_mark_read=True,
            **kw,
        ),
        "message_content_sent": lambda **kw: client.message_content(
            MessageReference(MessageFolder.SENT, "101", alias), **kw
        ),
        "recipient_groups": client.recipient_groups,
        "recipients": lambda **kw: client.recipients(
            RecipientGroupReference("nauczyciel", alias), **kw
        ),
    }
    method: Read = selections.get(operation) or getattr(client, operation)
    return method


class ReadsFixture(SchoolFixture):
    def __init__(self) -> None:
        super().__init__()
        self.reads: list[tuple[str, str]] = []
        self.wire: dict[str, tuple[dict[str, str], str, bytes]] = {}
        self.bodies: dict[str, tuple[bytes, str]] = {}
        self.page_bodies: dict[tuple[str, int], tuple[bytes, str]] = {}
        # Statuses served once each, in order, before the operation's body.
        self.failures: dict[str, list[int]] = {}
        self.hold: asyncio.Event | None = None
        self.held = asyncio.Event()

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/loguj/portalRodzina", self.portal)
        app.router.add_get("/OAuth/Authorization", self.authorization)
        app.router.add_post("/OAuth/Authorization", self.submit)
        app.router.add_get("/loguj", self.callback)
        app.router.add_get("/gateway/api/2.0/Me", self.identity)
        for operation in OPERATIONS:
            endpoint = ENDPOINTS[operation]
            app.router.add_route(
                endpoint.method, endpoint.path, self.handler(operation)
            )
        return app

    def handler(self, operation: str) -> Callable[[web.Request], Awaitable[Any]]:
        async def handle(request: web.Request) -> web.Response:
            login = self.record(request)
            self.reads.append((operation, login))
            if self.hold is not None:
                self.held.set()
                await self.hold.wait()
            if self.failures.get(operation):
                status = self.failures[operation].pop(0)
                location = {"Location": "/loguj"} if status == 302 else None
                return web.Response(status=status, headers=location)
            body = await request.read()
            form = (
                {k: str(v) for k, v in (await request.post()).items()}
                if request.method == "POST"
                else {}
            )
            self.wire[operation] = (
                form,
                request.query_string,
                body if not form else b"",
            )
            selection = int(form.get("numer_strony105", "0"))
            page, kind = (
                self.bodies.get(operation)
                or self.page_bodies.get((operation, selection))
                or selected(operation, form)
            )
            return web.Response(body=page, content_type=kind)

        return handle

    def count(self, operation: str, login: str | None = None) -> int:
        return sum(
            1 for op, who in self.reads if op == operation and login in (None, who)
        )
