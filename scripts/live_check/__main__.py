"""Read-only live check of an installed build. See RELEASE.md before any use.

    python -m scripts.live_check run --profile release --secrets FILE
    python -m scripts.live_check run --profile weekly --from-env --expectations FILE
    python -m scripts.live_check run --profile weekly --from-env --record
    python -m scripts.live_check identity --secrets FILE   (local only)

Run it from the repository root with the interpreter of an environment that
has the build under test installed. Output holds versions, statuses, coverage
and counts only. Any unexpected failure prints its exception class name only.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
import sys
import warnings
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, date, datetime
from pathlib import Path

from librus_python_api import AccountCredentials, LibrusService, RequestBudget
from scripts.live_check.checks import identity_key
from scripts.live_check.credentials import MissingSecrets, from_environment, from_file
from scripts.live_check.expectations import compare, load, record, record_problems
from scripts.live_check.guard import guarded
from scripts.live_check.profiles import PROFILES, RELEASE
from scripts.live_check.report import render_json, render_summary
from scripts.live_check.runner import release_problems, run_profile

COMMIT = re.compile(r"[0-9a-f]{40}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.live_check")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--profile", choices=sorted(PROFILES), required=True)
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--secrets", type=Path)
    source.add_argument("--from-env", action="store_true")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--expectations", type=Path)
    mode.add_argument("--record", action="store_true")
    run.add_argument("--summary", type=Path)
    identity = commands.add_parser("identity")
    identity.add_argument("--secrets", type=Path, required=True)
    return parser


async def _identities(accounts: Mapping[str, AccountCredentials]) -> list[str]:
    async with LibrusService(
        accounts,
        context_key=secrets.token_bytes(32),
        transport_factory=guarded({"identity"}, ()),
    ) as service:
        return [
            identity_key(
                await service.account(alias).identity(
                    budget=RequestBudget(max_requests=12, timeout_seconds=60)
                )
            )
            for alias in accounts
        ]


def _early_summary(args: argparse.Namespace, line: str) -> None:
    """A failed run's summary when no report exists; `line` is fixed text."""
    path: Path | None = getattr(args, "summary", None)
    if path is None:
        return
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    with suppress(OSError), path.open("a") as summary:
        summary.write(f"## Live check: {args.profile} failed\n\n{stamp} UTC: {line}\n")


def _run(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    environ: Mapping[str, str],
) -> int:
    if args.command == "identity":
        if environ.get("CI") or environ.get("GITHUB_ACTIONS"):
            print(json.dumps({"refused": "identity printing is local only"}))
            return 1
        keys = asyncio.run(_identities(from_file(args.secrets)))
        for slot, key in enumerate(keys):
            print(f"LIBRUS_LIVE_IDENTITY_{slot}={key}")
        return 0
    profile = PROFILES[args.profile]
    if profile is not RELEASE and not (args.record or args.expectations):
        parser.error("weekly runs need --expectations or --record")
    if args.from_env:
        accounts, identities = from_environment(environ)
    else:
        accounts, identities = from_file(args.secrets), {}
    commit = environ.get("GITHUB_SHA", "")
    report = asyncio.run(
        run_profile(
            profile,
            accounts,
            today=date.today(),
            identities=identities,
            commit=commit if COMMIT.fullmatch(commit) else "unknown",
        )
    )
    if profile is RELEASE:
        report.problems = release_problems(report)
    elif args.record:
        report.problems = record_problems(report)
    else:
        report.problems = compare(report, load(args.expectations.read_text()))
    print(render_json(report))
    if args.record:
        print(json.dumps(record(report), indent=2, sort_keys=True))
    if args.summary:
        with args.summary.open("a") as summary:
            summary.write(render_summary(report))
    return 0 if report.passed else 1


def main(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> int:
    # Library, asyncio and warning output could carry upstream text.
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    sys.unraisablehook = lambda _: None
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _run(parser, args, os.environ if environ is None else environ)
    except SystemExit:
        raise
    except MissingSecrets as missing:
        print(json.dumps({"passed": False, "missing_secrets": list(missing.names)}))
        _early_summary(args, "missing secrets " + ", ".join(missing.names) + ".")
        return 1
    except BaseException as error:  # noqa: BLE001 - only the class name may leave
        print(json.dumps({"passed": False, "crash": type(error).__name__}))
        _early_summary(args, "crashed with " + type(error).__name__ + ".")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
