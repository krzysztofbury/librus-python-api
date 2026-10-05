"""Test the sealed archives in disposable environments, without rebuilding them."""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def run(*args: str, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def qualify(directory: Path, python: str, dependencies: str) -> None:
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
            executable = str(venv / "bin/python")
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
                str(repo / "tests"),
                "-q",
                cwd=root,
                env=environment,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--python", default="3.14")
    parser.add_argument(
        "--dependencies", choices=("locked", "latest"), default="locked"
    )
    args = parser.parse_args()
    qualify(args.directory.resolve(), args.python, args.dependencies)
