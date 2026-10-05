"""Publication authority and artifact reuse are workflow-level security contracts."""

from pathlib import Path

import yaml


def test_publisher_is_manual_main_only_and_waits_for_exact_artifact_matrix() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/workflow.yaml").read_text(), Loader=yaml.BaseLoader
    )
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"]["inputs"]["target"]["options"] == [
        "verify",
        "pypi",
    ]
    jobs = workflow["jobs"]
    assert jobs["build"]["if"] == "github.ref == 'refs/heads/main'"
    assert jobs["qualify"]["needs"] == "build"
    assert set(jobs["publish"]["needs"]) == {"build", "qualify", "qualify-windows-disk"}
    windows = jobs["qualify-windows-disk"]
    assert windows["needs"] == "build" and windows["runs-on"] == "windows-2025"
    assert windows["strategy"]["matrix"] == {
        "python": ["3.13", "3.14"],
        "dependencies": ["locked", "latest"],
    }
    assert jobs["publish"]["if"] == "inputs.target != 'verify'"
    assert jobs["publish"]["environment"]["name"] == "pypi"
    assert jobs["publish"]["permissions"]["id-token"] == "write"
    for name, job in jobs.items():
        if name != "publish":
            assert job.get("permissions", {}).get("id-token") != "write"
    for name in ("qualify", "qualify-windows-disk", "publish", "confirm"):
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
