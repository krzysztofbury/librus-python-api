"""Capture one login's Librus pages for offline diagnosis and release smoke checks.

Live use requires the owner's authorization. The run submits credentials once,
dispatches at most --max-requests requests, refuses every operation outside an
allowlist of reads and view selections, and keeps going after a failed read, so
one run shows the state of the whole public read surface. Raw pages are private
school data: they are written with 0600 permissions to a new directory that
must be outside any Git work tree. Delete it after diagnosis and publish only
independently authored fixtures.

    uv run python scripts/live_capture.py --secrets FILE --account 0 --out DIR
"""

import argparse
import asyncio
import json
import os
import traceback
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

from librus_python_api import (
    AccountCredentials,
    LibrusService,
    OperationLimits,
    RequestBudget,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import LoginSubmission, RequestForm, TransportResponse
from librus_python_api.transport import AiohttpTransport

REPOSITORY = Path(__file__).resolve().parent.parent
# Ordinary reads plus view-selection POSTs, which change only the filter shown
# in that login's own session. Messages, sends and read-once routes stay out.
ALLOWED = frozenset(
    {
        "identity",
        "student_information",
        "final_grades",
        "grades",
        "attendance",
        "attendance_detail",
        "gateway_attendance",
        "attendance_lesson",
        "attendance_subject",
        "timetable",
        "announcements",
        "agenda",
        "agenda_detail",
        "homework",
        "homework_detail",
        "completed_lessons",
        "behaviour_notes_probe",
    }
)


def private_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    # Any Git work tree could be committed and published, not only this one.
    if any((folder / ".git").exists() for folder in (resolved, *resolved.parents)):
        raise SystemExit("Refusing to write private captures inside a Git work tree")
    resolved.mkdir(mode=0o700, parents=True, exist_ok=False)
    return resolved


def private_file(path: Path) -> Path:
    """Refuse a private output file inside any Git work tree, like captures."""
    resolved = path.expanduser().resolve()
    if any((folder / ".git").exists() for folder in resolved.parents):
        raise SystemExit("Refusing to write private output inside a Git work tree")
    return resolved


def form_fields(form: RequestForm) -> dict[str, str] | None:
    if form is None or isinstance(form, LoginSubmission):
        return None
    return dict(form)


class ReadOnlyCaptureTransport(AiohttpTransport):
    """Refuse every transport path that bypasses the per-request allowlist.

    Sends, modern authentication and read-once consumption use dedicated
    exchanges instead of request()/_exchange(), so an allowlist there alone
    cannot stop them. Capture runs never need them.
    """

    async def send_message(self, *args: object, **kwargs: object) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    async def send_modern_message(self, *args: object, **kwargs: object) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    async def authenticate_modern(self, *args: object, **kwargs: object) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    async def consume_schedule_events(
        self, *args: object, **kwargs: object
    ) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


class CapturingTransport(ReadOnlyCaptureTransport):
    """Allowlist each endpoint and keep a copy of every non-login response."""

    out: Path
    index: list[dict[str, Any]]
    logins = 0

    async def request(
        self,
        endpoint_id: str,
        budget: RequestBudget,
        *,
        form: RequestForm = None,
        reference_id: str | None = None,
    ) -> TransportResponse:
        if endpoint_id == "login_submit":
            CapturingTransport.logins += 1
            if CapturingTransport.logins > 1:
                raise SystemExit("Refusing a second credential submission")
        elif not endpoint_id.startswith("login_") and endpoint_id not in ALLOWED:
            raise SystemExit(f"Refusing operation outside the allowlist: {endpoint_id}")
        response = await super().request(
            endpoint_id, budget, form=form, reference_id=reference_id
        )
        if not endpoint_id.startswith("login_"):
            name = f"{len(self.index):02d}-{endpoint_id}.html"
            path = self.out / name
            path.write_bytes(response.body)
            path.chmod(0o600)
            self.index.append(
                {
                    "file": name,
                    "endpoint": endpoint_id,
                    "form": form_fields(form),
                    "status": response.status,
                    "content_type": response.headers.get("content-type"),
                    "bytes": len(response.body),
                }
            )
        return response


async def capture(
    credentials: AccountCredentials, out: Path, max_requests: int
) -> None:
    CapturingTransport.out, CapturingTransport.index = out, []
    outcomes: list[dict[str, Any]] = []
    budget = RequestBudget(max_requests=max_requests, timeout_seconds=240)

    async def step(name: str, read: Callable[[], Awaitable[Any]]) -> Any:
        try:
            result = await read()
        except Exception as error:  # Diagnosis continues past a failed family.
            frame = traceback.extract_tb(error.__traceback__)[-1]
            outcomes.append(
                {"step": name, "error": type(error).__name__, "at": frame.name}
            )
            return None
        outcomes.append({"step": name, "result": type(result).__name__})
        return result

    today = date.today()
    month_start = today.replace(day=1)
    previous = month_start - timedelta(days=1)
    async with LibrusService(
        {"capture": credentials},
        transport_factory=CapturingTransport,
        operation_limits=OperationLimits(max_requests=max_requests),
    ) as service:
        client = service.account("capture")
        await step("identity", lambda: client.identity(budget=budget))
        await step(
            "student_information", lambda: client.student_information(budget=budget)
        )
        await step("final_grades", lambda: client.final_grades(budget=budget))
        await step("grades", lambda: client.grades(budget=budget))
        attendance = await step("attendance", lambda: client.attendance(budget=budget))
        details = [
            row.detail_id
            for row in (attendance.items if attendance is not None else ())
            if row.detail_id is not None
        ]
        if details:
            await step(
                "attendance_detail",
                lambda: client.attendance_detail(details[-1], budget=budget),
            )
        await step(
            "attendance_frequency", lambda: client.attendance_frequency(budget=budget)
        )
        rows = await step(
            "gateway_attendance",
            lambda: client.gateway_attendance(budget=budget, max_age_seconds=60),
        )
        if rows is not None and rows.items:
            # One school day keeps the per-lesson metadata fan-out small.
            day = max(row.day for row in rows.items)
            await step(
                "subject_frequency",
                lambda: client.subject_frequency(day, day, budget=budget),
            )
        monday = today - timedelta(days=today.weekday())
        await step("timetable", lambda: client.timetable(monday, budget=budget))
        await step("announcements", lambda: client.announcements(budget=budget))
        homework = await step(
            "homework",
            lambda: client.homework(month_start, today, budget=budget),
        )
        agendas = []
        for day in (today, previous):
            year, month = day.year, day.month
            agendas.append(
                await step(
                    f"agenda {year}-{month:02d}",
                    partial(client.agenda, year, month, budget=budget),
                )
            )
        events = [
            event.reference
            for agenda in agendas
            if agenda is not None
            for day in agenda.days
            for event in day.events
            if event.reference is not None
        ]
        if events:
            await step(
                "agenda_detail", lambda: client.agenda_detail(events[0], budget=budget)
            )
        # Open only an assignment already marked done, so a possible read
        # marker on the detail page cannot change the account's state.
        done = [
            item.reference
            for item in (homework.items if homework is not None else ())
            if item.marked_done_at is not None and item.reference is not None
        ]
        if done:
            await step(
                "homework_detail",
                lambda: client.homework_detail(done[0], budget=budget),
            )
        await step(
            "completed_lessons",
            lambda: client.completed_lessons_page(month_start, today, budget=budget),
        )
        await step(
            "behaviour_notes_probe",
            lambda: client._transport.request("behaviour_notes_probe", budget),
        )
    report = {
        "captured": CapturingTransport.index,
        "outcomes": outcomes,
        "requests": budget.requests_dispatched,
        "logins": CapturingTransport.logins,
    }
    index = out / "index.json"
    index.write_text(json.dumps(report, indent=1))
    index.chmod(0o600)
    print(json.dumps(outcomes, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--account", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, default=64)
    arguments = parser.parse_args()
    out = private_directory(arguments.out)
    account = json.loads(arguments.secrets.read_text())["accounts"][arguments.account]
    credentials = AccountCredentials(
        login=account["username"], password=account["password"]
    )
    os.umask(0o077)
    asyncio.run(capture(credentials, out, arguments.max_requests))


if __name__ == "__main__":
    main()
