"""Read-only watchdog, independent of the credentialed live workflow."""

import argparse
import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MAX_AGE = timedelta(days=8)
WORKFLOW = ".github/workflows/live-check.yml"


def check_freshness(payload: Any, *, now: datetime) -> int:
    """Return the latest completed main run ID, or fail closed on bad evidence."""
    if now.tzinfo is None or not isinstance(payload, dict):
        raise ValueError("invalid freshness evidence")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("no completed live-check run")
    candidates: list[tuple[datetime, int]] = []
    for run in runs:
        if (
            not isinstance(run, dict)
            or run.get("head_branch") != "main"
            or run.get("path") != WORKFLOW
            or run.get("status") != "completed"
            or run.get("conclusion")
            not in (
                "success",
                "failure",
                "neutral",
                "cancelled",
                "skipped",
                "timed_out",
                "action_required",
                "stale",
                "startup_failure",
            )
            or type(run.get("id")) is not int
            or run["id"] <= 0
        ):
            raise ValueError("invalid completed main run")
        times = []
        for key in ("created_at", "updated_at"):
            value = run.get(key)
            if not isinstance(value, str) or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
            ):
                raise ValueError("invalid run timestamp")
            times.append(datetime.fromisoformat(value))
        created, updated = times
        if created > updated or updated > now:
            raise ValueError("inconsistent run timestamps")
        candidates.append((updated, run["id"]))
    newest, identifier = max(candidates)
    if now - newest > MAX_AGE:
        raise ValueError("latest completed live-check run is older than eight days")
    return identifier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path, help="Offline recorded API response")
    parser.add_argument("--now", help="Offline clock override, ISO 8601 with timezone")
    args = parser.parse_args()
    try:
        if args.response is not None:
            raw = args.response.read_bytes()
        else:
            if args.now is not None:
                raise ValueError("clock override requires an offline response")
            repository = os.environ.get("GITHUB_REPOSITORY", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
                raise ValueError("missing repository")
            raw = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{repository}/actions/workflows/live-check.yml/runs"
                    "?branch=main&status=completed&per_page=20",
                ],
                check=True,
                capture_output=True,
                timeout=30,
            ).stdout
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
        identifier = check_freshness(json.loads(raw), now=now)
    except (ValueError, OSError, subprocess.SubprocessError):
        raise SystemExit(
            "Live-check freshness failed: missing, stale or invalid evidence"
        ) from None
    print(f"Live-check freshness passed: completed main run {identifier}")


if __name__ == "__main__":
    main()
