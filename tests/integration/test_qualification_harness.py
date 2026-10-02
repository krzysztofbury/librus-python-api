"""Optional real Chromium/HTTP preflight before spending any live authorization."""

import asyncio
import os
from typing import Any

import pytest
from aiohttp import web

from scripts.qualify_school_reads import (
    ScopeGuard,
    failed_response_evidence,
    load_baseline,
    observed_transport,
    qualification_operations,
)
from tests.completed_lessons_support import lesson_row, lessons_html
from tests.http_support import serve
from tests.school_reads_support import SchoolReadsFixture

pytestmark = pytest.mark.integration


class QualificationFixture(SchoolReadsFixture):
    def response(self, kind: str, body: str) -> web.Response:
        if kind == "agenda":
            body = body.replace("<body>", "<body><table><tr><td>").replace(
                "</body>", "</td></tr></table></body>"
            )
        elif kind == "homework":
            body = body.replace(
                "myHomeworkTable decorated", "decorated myHomeworkTable"
            )
        return super().response(kind, body)

    def app(self) -> web.Application:
        app = super().app()
        app.router.add_post("/zrealizowane_lekcje", self.lessons)
        app.router.add_get("/uwagi", self.notes)
        return app

    async def lessons(self, request: web.Request) -> web.Response:
        self.record(request)
        form = await request.post()
        number = int(str(form["numer_strony1001"]))
        rows = lesson_row(f"Fixture {number}:first") + lesson_row(
            f"Fixture {number}:last"
        )
        return web.Response(
            text=lessons_html(number, 3, rows)
            .replace("<body>", "<body><!-- Fixture comment -->")
            .replace("extra decorated", "decorated"),
            content_type="text/html",
        )

    async def notes(self, request: web.Request) -> web.Response:
        self.record(request)
        return web.Response(
            text='<html><p class="msgEmptyTable">Brak uwag</p></html>',
            content_type="text/html",
        )


def test_full_one_shot_harness_on_original_loopback_and_network_disabled_chromium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    import librus_python_api as api

    location = os.environ.get("LIBRUS_APIX_SITE_PACKAGES")
    if not location:
        pytest.skip("Explicit external apix installation required")
    load_baseline(Path(location))
    playwright = pytest.importorskip("playwright.async_api")

    async def scenario() -> None:
        fixture = QualificationFixture()
        async with serve(fixture.app()) as origin:
            fixture.origin = origin
            monkeypatch.setattr(
                "scripts.qualify_school_reads.UPSTREAM_ORIGINS",
                {"api": origin, "synergia": origin},
            )
            guard = ScopeGuard()
            captured: list[tuple[str, bytes, Any]] = []
            async with playwright.async_playwright() as engine:
                browser = await engine.chromium.launch(
                    executable_path="/usr/bin/chromium",
                    headless=True,
                    args=["--disable-background-networking"],
                )
                context = await browser.new_context(
                    java_script_enabled=False, service_workers="block"
                )
                await context.route("**/*", lambda route: route.abort())
                page = await context.new_page()
                async with fixture.service() as service:
                    service._factory = observed_transport(guard, captured)
                    client = service.account("student")
                    budget = api.RequestBudget(max_requests=24, timeout_seconds=30)
                    report: dict[str, Any] = {"pages": []}
                    await client.identity(budget=budget)
                    await qualification_operations(
                        client, budget, page, captured, report, guard
                    )
                    assert guard.logins == 1 and guard.requests <= 24
                    assert report["midpage_resume_exercised"] is True
                    assert report["page_boundary_resume_exercised"] is True
                    assert len(report["pages"]) == 10
                    assert all(p["native_rendered_match"] for p in report["pages"])
                    assert all(
                        "offline_failure" not in p["baseline"] for p in report["pages"]
                    ), [(p["kind"], p["baseline"]) for p in report["pages"]]
                    assert report["notes"]["explicit_empty_markers"] == 1
                    assert captured == []
                    diagnostic = await failed_response_evidence(
                        page,
                        b"<html><body><!-- Fixture comment -->"
                        b"Fixture unknown</body></html>",
                        "completed_lessons",
                    )
                    assert diagnostic["rendered"] == {
                        "rows": 0,
                        "empty_markers": 0,
                        "pagination_spans": 0,
                    }
                    assert diagnostic["baseline"] == {"items": 0, "page_count": 0}
                    assert "Fixture" not in str(diagnostic)
                await context.close()
                await browser.close()

    asyncio.run(scenario())
