"""Run one parser on a saved Synergia page and report the outcome offline.

    python -m librus_python_api.inspect_page grades page.html
    python -m librus_python_api.inspect_page profile informacja.html

The report holds counts, code locations and page structure built from
allowlists (see diagnostics.describe_failure), never page text or values.
It makes no network request.
"""

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from librus_python_api import __version__
from librus_python_api.config import TransportLimits
from librus_python_api.diagnostics import describe_failure, failure_frames
from librus_python_api.exceptions import LibrusError
from librus_python_api.grade_parsers import parse_final_grades
from librus_python_api.grade_records import parse_grade_records
from librus_python_api.models import Availability
from librus_python_api.parsers import parse_profile

NOTICE = (
    "This report holds counts, code locations and page structure only, no page "
    "text or values. Review it before sharing."
)


def _grades(body: bytes) -> dict[str, int]:
    records = parse_grade_records(body)
    return {
        "numeric": sum(1 for g in records.numeric if g.point_grade_id is None),
        "point": sum(1 for g in records.numeric if g.point_grade_id is not None),
        "formative_mirrors": sum(1 for g in records.numeric if g.formative_id),
        "descriptive": len(records.descriptive),
        "descriptive_summaries": len(records.descriptive_summaries),
        "averages": len(records.averages),
        "point_results": len(records.point_results),
        "formative": len(records.formative),
    }


def _final_grades(body: bytes) -> dict[str, int]:
    return {"subjects": len(parse_final_grades(body))}


def _profile(body: bytes) -> dict[str, int]:
    lucky = parse_profile(body).lucky_number.availability
    return {"fields": 5, "lucky_number": int(lucky == Availability.AVAILABLE)}


PARSERS: dict[str, Callable[[bytes], dict[str, int]]] = {
    "grades": _grades,
    "final-grades": _final_grades,
    "profile": _profile,
}
# macOS TextEdit saves a viewed page source as a new document holding the
# source as text, not the page itself.
_TEXT_EXPORT = re.compile(rb'<meta name="Generator" content="Cocoa HTML Writer"', re.I)


def inspect(parser: str, body: bytes) -> tuple[bool, list[str]]:
    """Parse `body` and return success and the report lines."""
    lines = [NOTICE, f"librus-python-api {__version__}, parser {parser}"]
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        # Synergia serves UTF-8; another encoding is a saving problem, not a layout.
        lines.append("FAILED input: the file is not UTF-8; save the page as UTF-8")
        return False, lines
    if _TEXT_EXPORT.search(body[:4096]):
        lines.append(
            "FAILED input: the file is page source saved as a text document; "
            "save the page itself (Safari: File > Save As, format Page Source)"
        )
        return False, lines
    if not re.search(rb"<html[\s>]", body[:4096], re.I):
        # A copied table (outerHTML) is a fragment; parsers expect a page.
        body = b"<!doctype html><html><body>" + body + b"</body></html>"
        lines.append("input: fragment, wrapped in a page")
    try:
        counts = PARSERS[parser](body)
    except LibrusError as error:
        lines.append(f"FAILED {error.kind.value}")
        lines.extend(f"  at {site}" for site in failure_frames(error, limit=12))
        lines.append(describe_failure(error) or "no page structure available")
        return False, lines
    except Exception as error:  # A parser bug is reported, never its message.
        lines.append(f"FAILED unexpected {type(error).__name__}")
        lines.extend(f"  at {site}" for site in failure_frames(error, limit=12))
        lines.append(describe_failure(error) or "no page structure available")
        return False, lines
    lines.append("OK " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    return True, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m librus_python_api.inspect_page",
        description="Parse a saved Synergia page offline and report counts or "
        "where parsing failed, without page text or values.",
    )
    parser.add_argument("parser", choices=sorted(PARSERS))
    parser.add_argument("file", type=Path)
    arguments = parser.parse_args(argv)
    stdout: Any = sys.stdout
    if hasattr(stdout, "reconfigure"):
        stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    limit = TransportLimits().parse_max_bytes
    try:
        with arguments.file.open("rb") as handle:
            body = handle.read(limit + 1)
    except OSError as error:
        print(f"cannot read the file: {type(error).__name__}", file=sys.stderr)
        return 2
    if len(body) > limit:
        print(
            f"{NOTICE}\nFAILED limit: the file is over {limit} bytes, "
            "the size the library parses",
        )
        return 1
    ok, lines = inspect(arguments.parser, body)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
