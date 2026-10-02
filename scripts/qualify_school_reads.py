"""One-shot, explicitly authorized installed-wheel qualification, never CI.

Private credentials, HTML and domain rows exist only in memory. The report is
fixed technical metadata. Run synthetic preflight before allocating a live scope.
"""

import argparse
import asyncio
import base64
import hashlib
import importlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from importlib.metadata import distribution
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import librus_python_api as api
from librus_python_api.config import ENDPOINTS, UPSTREAM_ORIGINS, SideEffect
from librus_python_api.models import (
    AgendaSelection,
    CompletedLessonsPageSelection,
    HomeworkSelection,
)
from librus_python_api.transport import AiohttpTransport
from scripts.school_read_browser import (
    AGENDA_DOM,
    DETAIL_DOM,
    HOMEWORK_DOM,
    LESSONS_DOM,
    NOTES_DOM,
)
from scripts.school_read_comparison import (
    ComparisonFailure,
    agenda_baseline,
    assert_rendered_agenda,
    assert_rendered_details,
    assert_rendered_homework,
    assert_rendered_lessons,
    fields_baseline,
    homework_baseline,
    lessons_baseline,
    require,
)

START, END = date(2026, 9, 1), date(2026, 10, 31)
HOMEWORK_START = date(2026, 1, 1)
READS = {
    "completed_lessons",
    "agenda",
    "agenda_detail",
    "homework",
    "homework_detail",
    "behaviour_notes_probe",
}


class ScopeGuard:
    def __init__(self) -> None:
        self.requests = self.logins = self.lesson_requests = 0
        self.failed = False
        self.counts: Counter[str] = Counter()
        self.references: dict[str, set[str]] = {
            "agenda_detail": set(),
            "homework_detail": set(),
        }

    def admit(self, endpoint: Any, url: str, form: Any) -> None:
        require(not self.failed, "scope_closed_after_failure")
        require(self.requests < 24, "scope_request_ceiling")
        require(
            endpoint.operation_id in READS
            or endpoint.operation_id == "identity"
            or endpoint.side_effect == SideEffect.AUTHENTICATION,
            "scope_operation",
        )
        target = urlsplit(url)
        origin = urlsplit(UPSTREAM_ORIGINS[endpoint.origin])
        require(
            (target.scheme, target.netloc) == (origin.scheme, origin.netloc),
            "scope_origin",
        )
        require(
            not target.username and not target.password and not target.fragment,
            "scope_url",
        )
        path = endpoint.path
        if "{id}" in path:
            prefix = path.partition("{id}")[0]
            require(target.path.startswith(prefix), "scope_reference_path")
            identifier = target.path[len(prefix) :]
            require(
                identifier in self.references[endpoint.operation_id],
                "scope_returned_reference",
            )
        else:
            require(target.path == path, "scope_fixed_path")
        operation = endpoint.operation_id
        require(endpoint in ENDPOINTS.values(), "scope_catalogued_operation")
        if operation == "identity":
            require(self.counts[operation] == 0, "scope_identity_ceiling")
        if operation == "login_submit":
            require(self.logins == 0, "scope_login_ceiling")
            self.logins += 1
        elif operation == "completed_lessons":
            require(
                isinstance(form, CompletedLessonsPageSelection), "scope_lesson_form"
            )
            require(
                (form.start, form.end) == (START, END) and 0 <= form.page <= 2,
                "scope_lesson_window_page",
            )
            require(self.lesson_requests < 5, "scope_lesson_request_ceiling")
            self.lesson_requests += 1
        elif operation == "agenda":
            require(
                isinstance(form, AgendaSelection)
                and form.year == 2026
                and form.month in {9, 10},
                "scope_agenda_window",
            )
            require(self.counts[operation] < 2, "scope_agenda_ceiling")
        elif operation == "homework":
            require(
                isinstance(form, HomeworkSelection)
                and (form.start, form.end) == (HOMEWORK_START, END),
                "scope_homework_window",
            )
            require(self.counts[operation] == 0, "scope_homework_ceiling")
        elif operation in {"agenda_detail", "homework_detail"}:
            require(self.counts[operation] < 2, "scope_detail_ceiling")
        elif operation == "behaviour_notes_probe":
            require(self.counts[operation] == 0, "scope_notes_ceiling")
        self.requests += 1
        self.counts[operation] += 1


def observed_transport(
    guard: ScopeGuard, captured: list[tuple[str, bytes, Any]]
) -> Any:
    class Observed(AiohttpTransport):
        def _get_session(self) -> Any:
            session = super()._get_session()
            # Qualification must count every wire attempt, not aiohttp's implicit
            # persistent-connection GET retry. Check the installed dependency seam.
            require(hasattr(session, "_retry_connection"), "transport_retry_preflight")
            session._retry_connection = False
            return session

        async def _exchange(
            self, endpoint: Any, url: str, budget: Any, form: Any
        ) -> Any:
            guard.admit(endpoint, url, form)
            try:
                response = await super()._exchange(endpoint, url, budget, form)
            except Exception:
                guard.failed = True
                raise
            if endpoint.operation_id in READS:
                captured.append((endpoint.operation_id, response.body, form))
                if response.status != 200:
                    guard.failed = True
            return response

    return Observed


class OfflineResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.SCHEDULE_URL = "https://offline.invalid" + ENDPOINTS["agenda"].path
        self.HOMEWORK_URL = "https://offline.invalid" + ENDPOINTS["homework"].path
        self.HOMEWORK_DETAILS_URL = (
            "https://offline.invalid"
            + ENDPOINTS["homework_detail"].path.partition("{id}")[0]
        )
        self.COMPLETED_LESSONS_URL = (
            "https://offline.invalid" + ENDPOINTS["completed_lessons"].path
        )

    def get(self, url: str) -> SimpleNamespace:
        require(urlsplit(url).hostname == "offline.invalid", "baseline_destination")
        return SimpleNamespace(text=self.body.decode())

    def post(self, url: str, data: Any) -> SimpleNamespace:
        return self.get(url)


def load_baseline(location: Path) -> None:
    sys.path.append(str(location.resolve()))
    metadata = distribution("librus-apix")
    require(metadata.version == "1.5.3", "baseline_version")
    for item in metadata.files or ():
        if item.suffix == ".py" and item.hash is not None:
            digest = hashlib.sha256(metadata.locate_file(item).read_bytes()).digest()
            require(
                item.hash.mode == "sha256"
                and base64.urlsafe_b64encode(digest).decode().rstrip("=")
                == item.hash.value,
                "baseline_integrity",
            )
    for name in ("schedule", "homework", "completed_lessons"):
        module = importlib.import_module("librus_apix." + name)
        if module.__file__ is None:
            raise ComparisonFailure("baseline_location")
        require(
            Path(module.__file__).resolve().is_relative_to(location.resolve()),
            "baseline_location",
        )


async def compare(page: Any, body: bytes, result: Any, kind: str) -> dict[str, Any]:
    await page.set_content(body.decode(), wait_until="domcontentloaded", timeout=10000)
    dom = {
        "agenda": AGENDA_DOM,
        "homework": HOMEWORK_DOM,
        "completed_lessons": LESSONS_DOM,
    }.get(kind, DETAIL_DOM)
    rendered = await page.evaluate(dom)
    checks: dict[str, Callable[[Any, Any], None]] = {
        "agenda": assert_rendered_agenda,
        "homework": assert_rendered_homework,
        "completed_lessons": assert_rendered_lessons,
    }
    check: Callable[[Any, Any], None] = checks.get(kind, assert_rendered_details)
    check(result, rendered)
    # Native/browser agreement is established before invoking the fallible baseline.
    report: dict[str, Any] = {"kind": kind, "native_rendered_match": True}
    report["items"] = (
        sum(len(d.events) for d in result.days)
        if kind == "agenda"
        else len(result.fields)
        if kind.endswith("detail")
        else len(result.items)
    )
    try:
        report["baseline"] = compare_baseline(body, result, kind)
    except Exception:
        # A baseline exception is not classified business divergence. Stop before
        # another school request, with a fixed reason rather than a raw exception.
        raise ComparisonFailure("baseline_offline_failure") from None
    return report


def compare_baseline(body: bytes, result: Any, kind: str) -> dict[str, int]:
    offline = OfflineResponse(body)
    if kind == "agenda":
        module = importlib.import_module("librus_apix.schedule")
        return agenda_baseline(
            result,
            module.get_schedule(
                offline, f"{result.month:02d}", str(result.year), include_empty=True
            ),
        )
    if kind == "homework":
        module = importlib.import_module("librus_apix.homework")
        return homework_baseline(
            result,
            module.get_homework(
                offline, result.start.isoformat(), result.end.isoformat()
            ),
        )
    if kind == "completed_lessons":
        module = importlib.import_module("librus_apix.completed_lessons")
        old = module.get_completed(
            offline, START.isoformat(), END.isoformat(), page=result.page
        )
        count = module.get_max_page_number(offline, START.isoformat(), END.isoformat())
        return lessons_baseline(result, old, count)
    if kind == "agenda_detail":
        module = importlib.import_module("librus_apix.schedule")
        old = module.schedule_detail(offline, "szczegoly", result.reference.identifier)
    else:
        module = importlib.import_module("librus_apix.homework")
        old = module.homework_detail(offline, result.reference.identifier)
    return fields_baseline(result.fields, old)


def structure_only(body: bytes) -> dict[str, Any]:
    from lxml import html

    document = html.document_fromstring(body)
    tables = [
        t for t in document.iter("table") if "decorated" in t.get("class", "").split()
    ]
    rows = [
        r
        for t in tables
        for r in t.iter("tr")
        if next(r.iterancestors("thead"), None) is None
    ]
    labels = [
        " ".join(s.text_content().split())
        for d in document.iter("div")
        if "pagination" in d.get("class", "").split()
        for s in d
        if s.tag == "span"
    ]
    return {
        "decorated_tables": len(tables),
        "empty_markers": len(
            document.xpath(
                '//*[contains(concat(" ",normalize-space(@class)," "),'
                '" msgEmptyTable ")]'
            )
        ),
        "row_column_counts": dict(
            Counter(str(len([c for c in r if c.tag in {"td", "th"}])) for r in rows)
        ),
        "pagination_spans": len(labels),
        "pagination_has_colon": any(":" in s for s in labels),
        "pagination_digit_group_counts": [len(re.findall(r"\d+", s)) for s in labels],
    }


def failure_site(error: BaseException) -> dict[str, str]:
    # Walk code locations only. Never serialize messages, source, locals or URLs.
    files = {"qualify_school_reads.py", "school_read_comparison.py"}
    files.update(path.name for path in Path(api.__file__).parent.glob("*.py"))
    result: dict[str, str] = {}
    frame = error.__traceback__
    while frame is not None:
        filename = Path(frame.tb_frame.f_code.co_filename).name
        if filename in files:
            result = {
                "module_file": filename,
                "function": frame.tb_frame.f_code.co_name,
            }
        frame = frame.tb_next
    return result


async def failed_response_evidence(page: Any, body: bytes, kind: str) -> dict[str, Any]:
    await page.set_content(body.decode(), wait_until="domcontentloaded", timeout=10000)
    result: dict[str, Any] = {"structure": structure_only(body)}
    if kind == "completed_lessons":
        rendered = await page.evaluate(LESSONS_DOM)
        result["rendered"] = {
            "rows": len(rendered["rows"]),
            "empty_markers": rendered["empty"],
            "pagination_spans": len(rendered["pagination"]),
        }
        # Even an invalid native page gets identical-byte business-reference
        # evidence, without treating an empty baseline list as a valid empty page.
        try:
            module = importlib.import_module("librus_apix.completed_lessons")
            offline = OfflineResponse(body)
            items = module.get_completed(offline, START.isoformat(), END.isoformat())
            count = module.get_max_page_number(
                offline, START.isoformat(), END.isoformat()
            )
            result["baseline"] = {"items": len(items), "page_count": count}
        except Exception as error:
            result["baseline"] = {"offline_failure": type(error).__name__}
    return result


async def qualify_lessons(
    client: Any, budget: Any, page: Any, captured: Any, report: Any
) -> None:
    report["phase"] = "completed_lessons_page"
    initial = await client.completed_lessons_page(START, END, budget=budget)
    _, body, _ = captured[0]
    report["pages"].append(await compare(page, body, initial, "completed_lessons"))
    captured.pop(0)
    report["completed_page_count"] = initial.page_count
    report["phase"] = "completed_lessons_resume"
    first = await client.completed_lessons(
        START, END, max_pages=1, limit=1, budget=budget
    )
    _, body, _ = captured[0]
    report["pages"].append(await compare(page, body, initial, "completed_lessons"))
    captured.pop(0)
    require(first.items == initial.items[:1], "lesson_first_batch")
    cursor = first.next_cursor
    report["midpage_resume_exercised"] = bool(cursor and cursor.offset)
    boundary = False
    for _ in range(3):
        if cursor is None or cursor.page > 2:
            break
        boundary = boundary or cursor.offset == 0
        result = await client.completed_lessons(
            START, END, cursor=cursor, max_pages=1, limit=256, budget=budget
        )
        _, body, _ = captured[0]
        from librus_python_api.completed_lessons import parse_completed_lessons

        rows, count, fingerprint = parse_completed_lessons(
            body, START, END, cursor.page
        )
        projected = replace(
            initial,
            page=cursor.page,
            items=rows,
            page_count=count,
            fingerprint=fingerprint,
        )
        report["pages"].append(
            await compare(page, body, projected, "completed_lessons")
        )
        captured.pop(0)
        if cursor.offset:
            require(
                first.items + result.items == initial.items,
                "lesson_midpage_continuation",
            )
        cursor = result.next_cursor
    report["page_boundary_resume_exercised"] = boundary
    before = budget.requests_dispatched
    require(
        await client.completed_lessons_page(
            START, END, max_age_seconds=60, budget=budget
        )
        is initial,
        "lesson_cached_page",
    )
    require(before == budget.requests_dispatched, "lesson_cache_traffic")


async def qualify_school(
    client: Any, budget: Any, page: Any, captured: Any, report: Any, guard: ScopeGuard
) -> None:
    references: list[Any] = []
    for month in (10, 9):
        report["phase"] = "agenda"
        result = await client.agenda(2026, month, budget=budget)
        _, body, _ = captured[0]
        report["pages"].append(await compare(page, body, result, "agenda"))
        captured.pop(0)
        for day in result.days:
            for item in day.events:
                if item.reference and item.reference not in references:
                    references.append(item.reference)
        before = budget.requests_dispatched
        require(
            await client.agenda(2026, month, max_age_seconds=60, budget=budget)
            is result,
            "agenda_cached_page",
        )
        require(before == budget.requests_dispatched, "agenda_cache_traffic")
    guard.references["agenda_detail"] = {r.identifier for r in references[:2]}
    for reference in references[:2]:
        report["phase"] = "agenda_detail"
        result = await client.agenda_detail(reference, budget=budget)
        _, body, _ = captured[0]
        report["pages"].append(await compare(page, body, result, "agenda_detail"))
        captured.pop(0)
    report["phase"] = "homework"
    assignments = await client.homework(HOMEWORK_START, END, budget=budget)
    _, body, _ = captured[0]
    report["pages"].append(await compare(page, body, assignments, "homework"))
    captured.pop(0)
    before = budget.requests_dispatched
    require(
        await client.homework(HOMEWORK_START, END, max_age_seconds=60, budget=budget)
        is assignments,
        "homework_cached_page",
    )
    require(before == budget.requests_dispatched, "homework_cache_traffic")
    references = list(
        dict.fromkeys(i.reference for i in assignments.items if i.reference)
    )[:2]
    guard.references["homework_detail"] = {r.identifier for r in references}
    for reference in references:
        report["phase"] = "homework_detail"
        result = await client.homework_detail(reference, budget=budget)
        _, body, _ = captured[0]
        report["pages"].append(await compare(page, body, result, "homework_detail"))
        captured.pop(0)


async def probe_notes(
    client: Any, budget: Any, page: Any, captured: Any, report: Any
) -> None:
    report["phase"] = "behaviour_notes_probe"
    async with client._lock:
        response = await client._transport.request("behaviour_notes_probe", budget)
        client._validate_read_response(response)
        client._require_content_type(response, "text/html")
    _, body, _ = captured[0]
    await page.set_content(body.decode(), wait_until="domcontentloaded")
    rendered = await page.evaluate(NOTES_DOM)
    rows = sum(len(t["rows"]) for t in rendered["tables"])
    report["notes"] = {
        "explicit_empty_markers": rendered["empty"],
        "decorated_tables": len(rendered["tables"]),
        "candidate_rows": rows,
        "apix_operation_exists": False,
    }
    report["notes"]["decision"] = "public_capability_deferred"
    require(
        rendered["empty"] == 1 and rows == 0 or rendered["empty"] == 0 and rows > 0,
        "notes_unrecognized_or_contradictory_layout",
    )
    captured.pop(0)


async def qualification_operations(
    client: Any, budget: Any, page: Any, captured: Any, report: Any, guard: ScopeGuard
) -> None:
    try:
        await qualify_school(client, budget, page, captured, report, guard)
        await probe_notes(client, budget, page, captured, report)
        await qualify_lessons(client, budget, page, captured, report)
    except Exception:
        # Collect diagnostics while the offline browser is still alive. They do
        # not change the stop-on-failure policy or dispatch another school request.
        guard.failed = True
        if captured:
            try:
                report["failed_response_evidence"] = await failed_response_evidence(
                    page, captured[-1][1], captured[-1][0]
                )
            except Exception as diagnostic_error:
                report["diagnostic_failure_type"] = type(diagnostic_error).__name__
        raise


def preflight(args: argparse.Namespace) -> dict[str, str]:
    require(
        Path(api.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
        and "site-packages" in str(api.__file__),
        "installed_artifact_required",
    )
    load_baseline(args.apix)
    require(args.credentials.stat().st_size <= 1024 * 1024, "credential_file_bound")
    require(args.credentials.stat().st_mode & 0o077 == 0, "credential_file_permissions")
    data = json.loads(args.credentials.read_text())
    selected = data["accounts"][args.account_position - 1]
    require(
        isinstance(selected.get("username"), str)
        and isinstance(selected.get("password"), str),
        "credential_schema",
    )
    return {"username": selected["username"], "password": selected["password"]}


async def run(selected: dict[str, str], report: dict[str, Any]) -> None:
    guard = ScopeGuard()
    captured: list[tuple[str, bytes, Any]] = []
    playwright = importlib.import_module("playwright.async_api")
    try:
        async with playwright.async_playwright() as engine:
            browser = await engine.chromium.launch(
                executable_path="/usr/bin/chromium",
                headless=True,
                args=[
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--disable-extensions",
                    "--disable-breakpad",
                ],
            )
            context = await browser.new_context(
                java_script_enabled=False,
                service_workers="block",
                accept_downloads=False,
            )
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            await page.set_content("<p>Fixture preflight</p>")
            require(
                await page.locator("p").inner_text() == "Fixture preflight",
                "browser_preflight",
            )
            report["chromium_version"] = browser.version
            report["phase"] = "authentication"
            budget = api.RequestBudget(max_requests=24, timeout_seconds=240)
            async with api.LibrusService(
                {
                    "approved": api.AccountCredentials(
                        login=selected["username"], password=selected["password"]
                    )
                },
                transport_factory=observed_transport(guard, captured),
            ) as service:
                client = service.account("approved")
                await client.identity(budget=budget)
                await qualification_operations(
                    client, budget, page, captured, report, guard
                )
            await context.close()
            await browser.close()
        report["status"] = "completed"
    except Exception as error:
        guard.failed = True
        report["status"] = "stopped"
        report["error_type"] = type(error).__name__
        report["failure_site"] = failure_site(error)
        if isinstance(error, ComparisonFailure):
            report["classification"] = str(error)
        if hasattr(error, "kind"):
            report["error_kind"] = str(error.kind)
        if captured:
            report["failed_response_structure"] = structure_only(captured[-1][1])
    finally:
        captured.clear()
        selected.clear()
        report.update(
            requests=guard.requests, logins=guard.logins, operations=dict(guard.counts)
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument(
        "--account-position", type=int, choices=range(1, 5), required=True
    )
    parser.add_argument("--apix", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(args.authorized, "fresh_authorization_required")
    # Exclusive report creation is also the one-shot marker. A process restart
    # never authorizes replay, even when its final request accounting is missing.
    report: dict[str, Any] = {
        "status": "started",
        "max_requests": 24,
        "max_logins": 1,
        "installed_version": api.__version__,
        "pages": [],
    }
    descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(json.dumps(report, indent=2))
    try:
        selected = preflight(args)
        asyncio.run(asyncio.wait_for(run(selected, report), timeout=300))
    except BaseException as error:
        report.update(
            status="interrupted_or_preflight_failed", error_type=type(error).__name__
        )
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
