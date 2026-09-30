"""Opt-in paired parser measurements on new synthetic, common-contract HTML."""

import gc
import importlib
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from librus_python_api.grade_parsers import parse_final_grades
from tests.grade_support import summary_html

pytestmark = pytest.mark.performance


def test_summary_parser_comparison(
    mcp_checkout: Path,
    record_property: Callable[[str, object], None],
) -> None:
    # Import the installed consumer implementation, never copy its source/fixtures
    # into this MIT library. No client construction, credentials, or HTTP calls.
    sys.path.insert(0, str(mcp_checkout))
    try:
        legacy_parse = importlib.import_module("src.scraping").parse_final_grades
    finally:
        sys.path.remove(str(mcp_checkout))
    rows = []
    expected = []
    for index in range(32):
        subject = f"Fixture topic {index}"
        row = summary_html(subject=subject).split("<tbody>")[1].split("</tbody>")[0]
        rows.append(row.replace("<tr>", '<tr class="line0">'))
        expected.append((subject, "progressing", "-", "4+"))
    template = summary_html()
    start, end = template.index("<tbody>") + len("<tbody>"), template.index("</tbody>")
    text = (
        (template[:start] + "".join(rows) + template[end:])
        .replace("<th ", "<td ")
        .replace("</th>", "</td>")
        .replace("Ocena roczna&lt;br /&gt;fixture year", "Ocena roczna")
    )
    body = text.encode()
    native = parse_final_grades(body)
    assert [
        (r.subject, r.midterm.raw, r.predicted_annual.raw, r.annual.raw) for r in native
    ] == expected
    legacy = legacy_parse(text)
    assert [
        (r.subject, r.midterm, r.predicted_final, r.final) for r in legacy
    ] == expected

    actions: dict[str, Callable[[], Any]] = {
        "native": lambda: parse_final_grades(body),
        "legacy": lambda: legacy_parse(text),
    }
    times: dict[str, list[float]] = {name: [] for name in actions}
    # Alternate order across samples. Keep tracing separate from timing, and
    # avoid machine-dependent speed ratios as portable regression assertions.
    for sample in range(7):
        for name in tuple(actions) if sample % 2 == 0 else tuple(actions)[::-1]:
            gc.collect()
            started = time.process_time()
            for _ in range(20):
                actions[name]()
            times[name].append((time.process_time() - started) * 1000 / 20)
    assert not tracemalloc.is_tracing()
    for name, action in actions.items():
        gc.collect()
        tracemalloc.start()
        try:
            for _ in range(10):
                action()
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        record_property(f"{name}_median_parser_cpu_ms", statistics.median(times[name]))
        record_property(f"{name}_python_allocation_peak_bytes", peak)
    record_property("subjects", 32)
    record_property("body_bytes", len(body))
