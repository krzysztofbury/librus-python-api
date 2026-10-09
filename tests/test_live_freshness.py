"""Watchdog decisions from projected public GitHub API evidence, no credentials."""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.check_live_freshness import check_freshness

RECORDED = Path(__file__).parent / "fixtures/live-check-runs.json"
NOW = datetime(2026, 10, 9, tzinfo=UTC)


def test_recorded_response_recent_and_stale_cli() -> None:
    for now, code in (
        ("2026-10-09T00:00:00+00:00", 0),
        ("2026-10-16T00:00:00+00:00", 1),
    ):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.check_live_freshness",
                "--response",
                str(RECORDED),
                "--now",
                now,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == code, result.stderr
    payload = json.loads(RECORDED.read_bytes())
    payload["workflow_runs"].reverse()
    assert check_freshness(payload, now=NOW) == 37620382335


@pytest.mark.parametrize(
    "key,value",
    [
        ("head_branch", "feature"),
        ("path", ".github/workflows/ci.yml"),
        ("status", "in_progress"),
        ("conclusion", None),
        ("conclusion", ""),
        ("conclusion", "invented"),
        ("created_at", "bad"),
        ("updated_at", "2026-10-10T00:00:00Z"),
        ("id", True),
    ],
)
def test_malformed_or_unrelated_evidence_fails_closed(key: str, value: object) -> None:
    payload = json.loads(RECORDED.read_bytes())
    payload["workflow_runs"][0][key] = value
    with pytest.raises(ValueError):
        check_freshness(payload, now=NOW)


@pytest.mark.parametrize(
    "payload", [{}, {"workflow_runs": []}, {"workflow_runs": None}]
)
def test_missing_run_fails(payload: object) -> None:
    with pytest.raises(ValueError):
        check_freshness(payload, now=NOW)


def test_eight_day_boundary_uses_completed_run_time() -> None:
    payload = json.loads(RECORDED.read_bytes())
    assert (
        check_freshness(payload, now=datetime(2026, 10, 15, 12, 21, 50, tzinfo=UTC))
        == 37620382335
    )
    with pytest.raises(ValueError):
        check_freshness(payload, now=datetime(2026, 10, 15, 12, 21, 51, tzinfo=UTC))
