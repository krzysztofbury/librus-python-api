"""Test the sealed archives in disposable environments, without rebuilding them."""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def run(*args: str, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


WINDOWS_DISK_TESTS = (
    "test_windows_disk.py",
    "test_attachment_files.py",
    "test_persistence.py",
    "test_context_keys.py",
    "test_notification_persistence.py",
    "test_notification_persistence_faults.py",
    "test_notification_persistence_limits.py",
    "test_notification_persistence_processes.py",
    "test_notification_modern.py",
    "test_notification_bootstrap.py",
    "test_notification_recovery.py",
)


def qualify(
    directory: Path, python: str, dependencies: str, *, scope: str = "all"
) -> None:
    repo = Path(__file__).resolve().parents[1]
    wheels, sdists = list(directory.glob("*.whl")), list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Qualification requires one wheel and one sdist")
    with tempfile.TemporaryDirectory(prefix="release-qualify-") as temporary:
        root = Path(temporary)
        requirements = root / "requirements.txt"
        environment = dict(os.environ, TMPDIR=str(root), TMP=str(root), TEMP=str(root))
        run(
            "uv",
            "export",
            "--quiet",
            "--locked",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            str(requirements),
            cwd=repo,
            env=environment,
        )
        if dependencies == "latest":
            # Keep test tooling locked; replace only declared runtime requirements.
            import tomllib

            runtime = tomllib.loads((repo / "pyproject.toml").read_text())["project"][
                "dependencies"
            ]
        else:
            runtime = []
        for artifact in wheels + sdists:
            venv = root / ("wheel" if artifact.suffix == ".whl" else "sdist")
            run("uv", "venv", str(venv), "--python", python, cwd=root, env=environment)
            executable = str(
                venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            )
            run(
                "uv",
                "pip",
                "install",
                "--python",
                executable,
                "--require-hashes",
                "--requirements",
                str(requirements),
                cwd=root,
                env=environment,
            )
            run(
                "uv",
                "pip",
                "install",
                "--python",
                executable,
                "--no-deps",
                str(artifact.resolve()),
                cwd=root,
                env=environment,
            )
            if runtime:
                run(
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    executable,
                    "--upgrade",
                    "--refresh",
                    *runtime,
                    cwd=root,
                    env=environment,
                )
            run("uv", "pip", "check", "--python", executable, cwd=root, env=environment)
            environment.update(PYTHONPATH=str(repo), ARTIFACT_ENV=str(venv))
            run(
                executable,
                str(repo / "scripts/installed_smoke.py"),
                cwd=root,
                env=environment,
            )
            run(
                executable,
                "-m",
                "pytest",
                *(str(repo / "tests" / name) for name in WINDOWS_DISK_TESTS)
                if scope == "windows-disk"
                else (str(repo / "tests"),),
                "-q",
                cwd=root,
                env=environment,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--python", default="3.14")
    parser.add_argument("--scope", choices=("all", "windows-disk"), default="all")
    parser.add_argument(
        "--dependencies", choices=("locked", "latest"), default="locked"
    )
    args = parser.parse_args()
    qualify(args.directory.resolve(), args.python, args.dependencies, scope=args.scope)
