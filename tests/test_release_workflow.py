"""Publication authority and artifact reuse are workflow-level security contracts."""

import tomllib
from pathlib import Path
from typing import Any

import yaml


def script(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_only_a_release_publishes_and_it_waits_for_exact_artifact_matrix() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/workflow.yaml").read_text(), Loader=yaml.BaseLoader
    )
    assert set(workflow["on"]) == {"release", "workflow_dispatch"}
    assert workflow["on"]["release"]["types"] == ["published"]
    assert set(workflow["on"]["workflow_dispatch"]["inputs"]) == {"tag"}
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert (
        jobs["build"]["if"]
        == "github.event_name == 'release' || github.ref == 'refs/heads/main'"
    )
    assert jobs["qualify"]["needs"] == "build"
    assert set(jobs["publish"]["needs"]) == {"build", "qualify", "qualify-windows-disk"}
    windows = jobs["qualify-windows-disk"]
    assert windows["needs"] == "build" and windows["runs-on"] == "windows-2025"
    assert windows["strategy"]["matrix"] == {
        "python": ["3.13", "3.14"],
        "dependencies": ["locked", "latest"],
    }
    assert jobs["publish"]["if"] == "github.event_name == 'release'"
    assert jobs["publish"]["environment"]["name"] == "pypi"
    assert jobs["publish"]["permissions"]["id-token"] == "write"
    for name, job in jobs.items():
        if name != "publish":
            assert job.get("permissions", {}).get("id-token") != "write"
    assert jobs["attach"]["permissions"] == {"contents": "write", "actions": "read"}
    assert "if" not in jobs["confirm"] and "if" not in jobs["attach"]
    for name, job in jobs.items():
        if name != "attach":
            assert job.get("permissions", {}).get("contents") != "write"
        # Release values reach shell only through the environment.
        assert "${{" not in script(job)
        for step in job["steps"]:
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
    assert '== "$GITHUB_SHA"' in script(jobs["build"])
    assert "release_gate.py identity" in script(jobs["build"])
    assert "release_gate.py identity" in script(jobs["publish"])
    for name in ("publish", "confirm", "attach"):
        assert "release_gate.py verify" in script(jobs[name])
    for name in ("qualify", "qualify-windows-disk", "publish", "confirm", "attach"):
        downloads = [
            step
            for step in jobs[name]["steps"]
            if step.get("uses", "").startswith("actions/download-artifact@")
        ]
        assert len(downloads) == 1
        assert (
            downloads[0]["with"]["artifact-ids"]
            == "${{ needs.build.outputs.artifact }}"
        )
    assert set(jobs["confirm"]["needs"]) == {"build", "publish"}
    assert set(jobs["attach"]["needs"]) == {"build", "confirm"}


def test_confirm_can_resolve_the_version_it_just_published() -> None:
    """`confirm` installs the new release from this checkout seconds after upload.

    The project's window would hide that version for 7 days (1.10.0), so the
    project's own package is exempt while its dependencies stay windowed.
    """
    root = Path(__file__).resolve().parents[1]
    uv = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["uv"]
    assert uv["exclude-newer"] == "7 days"
    assert uv["exclude-newer-package"] == {"librus-python-api": False}
    workflow = yaml.load(
        (root / ".github/workflows/workflow.yaml").read_text(), Loader=yaml.BaseLoader
    )
    assert '"librus-python-api==$VERSION"' in script(workflow["jobs"]["confirm"])
