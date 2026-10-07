"""The credentialed workflow can only run trusted main code, unattended and quiet."""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SECRETS = {
    f"LIBRUS_LIVE_{field}_{slot}"
    for field in ("LOGIN", "PASSWORD", "IDENTITY")
    for slot in (0, 1)
}


def workflow() -> dict[str, Any]:
    text = (ROOT / ".github/workflows/live-check.yml").read_text()
    # BaseLoader builds only strings, lists and dicts, and keeps "on" a string.
    loaded: dict[str, Any] = yaml.load(text, Loader=yaml.BaseLoader)
    return loaded


def steps() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = workflow()["jobs"]["live"]["steps"]
    return found


def test_triggers_permissions_and_serialization() -> None:
    data = workflow()
    assert set(data["on"]) == {"schedule", "workflow_dispatch"}
    assert data["on"]["schedule"] == [{"cron": "17 5 * * 1"}]
    assert data["permissions"] == {"contents": "read"}
    assert data["concurrency"] == {
        "group": "live-check",
        "cancel-in-progress": "false",
    }
    assert "env" not in data
    assert set(data["jobs"]) == {"live"}
    job = data["jobs"]["live"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["environment"] == "live-check"
    assert job["timeout-minutes"] == "15"
    assert "env" not in job and "strategy" not in job


def test_secrets_reach_only_the_checker_step() -> None:
    holders = [s for s in steps() if "secrets." in yaml.safe_dump(s)]
    assert [s["name"] for s in holders] == ["Run the live check"]
    checker = holders[0]
    assert {k for k, v in checker["env"].items() if "secrets." in v} == SECRETS
    assert "contracts/live-check-expectations.json" in checker["run"]
    assert "--summary" in checker["run"]


def test_actions_are_pinned_and_nothing_is_cached_or_uploaded() -> None:
    uses = [s["uses"] for s in steps() if "uses" in s]
    assert uses and all(re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", u) for u in uses)
    assert {u.split("@")[0] for u in uses} == {
        "actions/checkout",
        "astral-sh/setup-uv",
    }
    for step in steps():
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] == "false"
        if step.get("uses", "").startswith("astral-sh/setup-uv@"):
            assert step["with"]["enable-cache"] == "false"


def test_manual_version_input_is_validated_before_use() -> None:
    data = workflow()
    assert set(data["on"]["workflow_dispatch"]["inputs"]) == {"version", "record"}
    install = next(
        s for s in steps() if s.get("name") == "Install the build under test"
    )
    assert "inputs.version" not in install["run"]  # passed via env only
    assert install["env"]["VERSION"] == "${{ inputs.version }}"
    assert "=~ ^[0-9]+" in install["run"]
    # A rejected version says why instead of failing silently.
    assert "::error::" in install["run"]
