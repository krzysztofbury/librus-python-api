"""Independently authored new-schema descriptive grade fixtures.

The table follows a structure-only observation (2026-10-12) of the grades page;
the JSON shapes follow the source-informed field names in contracts/grades.md.
Every value is invented; no populated gateway response has been observed.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from librus_python_api.config import ENDPOINTS
from tests.grade_records_support import GradeRecordsFixture, grades_html

GATEWAY_OPERATIONS = (
    "descriptive_token_info",
    "descriptive_user_info",
    "descriptive_partial_grades",
    "descriptive_subjects",
    "descriptive_users",
)
PARENT = "FIX-AUTH-PARENT-41"
STUDENT = "FIX-AUTH-STUDENT-42"


def descriptive_row(
    subject_id: str = "301",
    subject: str = "Fixture Nature",
    *,
    user: str = "77",
    first: str = "",
    second: str = "",
) -> str:
    """A subject row whose semester cells the page script fills later."""
    return (
        f'<tr class="line0 studentRow" data-user_id="{user}" '
        f'data-subject_id="{subject_id}"><td class="micro center screen-only"></td>'
        f'<td>{subject}</td><td class="gradesCell" data-semester="1">{first}</td>'
        f'<td class="gradesCell" data-semester="2">{second}</td></tr>'
    )


def descriptive_table(rows: str | None = None) -> str:
    if rows is None:
        rows = descriptive_row() + descriptive_row("302", "Fixture Music", user="77")
    return (
        '<table class="decorated stretch newSchemaGradesByStudentTable"><thead><tr>'
        "<td></td><td>Przedmiot</td><td>Okres 1</td><td>Okres 2</td></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def observed_descriptive_page(rows: str | None = None) -> str:
    """The layout of an owner's live page (2026-10-28), with original values.

    An unclosed row-less table of the same class comes first, so parsing nests
    the rest of the page in it. The real table has a period header row, a
    hidden details row after each subject row (one with a stray quote
    attribute, as served) and an empty footer.
    """
    if rows is None:
        rows = descriptive_row() + descriptive_row("302", "Fixture Music")
    details = "".join(
        f'<tr class="line0 studentGradesDetailsRow" " data-subject_id="{subject}" '
        f'data-user_id="77" id="details_{subject}" name="details" '
        'style="display: none;"><td class="studentGradesDetailsCell" colspan="4">'
        "</td></tr>"
        for subject in ("301", "302")
    )
    return (
        '<!doctype html><html><body><form><div class="container-background">'
        '<table class="decorated stretch newSchemaGradesByStudentTable">'
        "<script></script>"
        '<table class="decorated stretch newSchemaGradesByStudentTable"><thead>'
        '<tr class="bolded"><td class="micro center screen-only"></td><td class="">'
        "Przedmiot</td><td>Okres 1</td><td>Okres 2</td></tr></thead>"
        f'<tbody>{rows}{details}</tbody><tfoot><tr><td colspan="4"></td></tr>'
        "</tfoot></table>"
        f"{grades_html().split('<body>')[1].split('</body>')[0]}"
        "</div></form></body></html>"
    )


def descriptive_page(table: str | None = None) -> str:
    return f"<!doctype html><html><body>{table or descriptive_table()}</body></html>"


def partial_grade(**fields: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "subjectId": "SUBJ-A",
        "teacherId": "T-1",
        "addedBy": "T-2",
        "area": {"name": "Fixture listening"},
        "scaleValue": {"value": "B", "id": 3},
        "content": "Fixture follows spoken steps",
        "comments": "Fixture remark",
        "date": "2026-10-05T09:15:00+02:00",
        "semester": 1,
        "addDate": "2026-10-05 09:16:00",
    }
    item.update(fields)
    return item


def partial_grades(*items: dict[str, Any], **envelope: Any) -> dict[str, Any]:
    if not items:
        items = (
            partial_grade(),
            partial_grade(
                subjectId="SUBJ-B",
                teacherId="T-9",
                addedBy=None,
                area=None,
                scaleValue=None,
                content="Fixture sings in tune",
                comments=None,
                date="2027-02-10",
                semester=2,
            ),
        )
    return {"data": list(items), **envelope}


def gateway_subjects(*rows: dict[str, Any], **envelope: Any) -> dict[str, Any]:
    if not rows:
        rows = (
            {"identifier": "SUBJ-A", "numericIdentifier": 301, "name": "Gateway A"},
            {"identifier": "SUBJ-B", "numericIdentifier": 999, "name": "Fixture Choir"},
            {"identifier": "SUBJ-C", "numericIdentifier": None, "name": None},
        )
    return {"data": list(rows), **envelope}


def gateway_users(*rows: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        rows = (
            {"AccountId": "T-1", "FirstName": "Ada", "LastName": "Fixture"},
            {"AccountId": "T-2", "FirstName": None, "LastName": "Author"},
        )
    return {"Users": list(rows), "Resources": {"Fixture": {"Url": "unused"}}}


def default_bodies() -> dict[str, Any]:
    return {
        "descriptive_token_info": {"UserIdentifier": PARENT, "UserType": 2},
        "descriptive_user_info": {"IdentifierOfStudentAssignedWithUser": STUDENT},
        "descriptive_partial_grades": partial_grades(),
        "descriptive_subjects": gateway_subjects(),
        "descriptive_users": gateway_users(),
    }


class GatewayGradesFixture(GradeRecordsFixture):
    """The grades POST plus the five gateway reads, recorded on the wire."""

    def __init__(self) -> None:
        super().__init__()
        self.grade_body = descriptive_page()
        self.bodies: dict[str, Any] = default_bodies()
        # Raw replacements: (status, body, content type) served for a route.
        self.raw: dict[str, tuple[int, bytes, str]] = {}
        self.gateway: list[dict[str, Any]] = []

    def app(self) -> web.Application:
        app = super().app()
        for operation in GATEWAY_OPERATIONS:
            endpoint = ENDPOINTS[operation]
            app.router.add_route(
                endpoint.method, endpoint.path, self.handler(operation)
            )
        return app

    def operations(self) -> list[str]:
        return [call["operation"] for call in self.gateway]

    def handler(self, operation: str) -> Callable[[web.Request], Awaitable[Any]]:
        async def handle(request: web.Request) -> web.Response:
            login = self.record(request)
            self.gateway.append(
                {
                    "operation": operation,
                    "method": request.method,
                    "reference": request.match_info.get("id"),
                    "query": request.query_string,
                    "body": await request.read(),
                    "content_type": request.headers.get("Content-Type"),
                    "login": login,
                }
            )
            if not login:
                return web.Response(status=401)
            if operation in self.raw:
                status, body, kind = self.raw[operation]
                return web.Response(status=status, body=body, content_type=kind)
            return web.json_response(self.bodies[operation])

        return handle


def encoded(value: Any) -> bytes:
    return json.dumps(value).encode()
