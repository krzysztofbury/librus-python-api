"""Small named guard mutations, isolated copies, passing baselines required.

Run with the development Python and an owned TMPDIR. No live endpoints are used.
Only pytest test failures count as kills; errors and timeouts are failures
of this harness. Source changes never touch the checkout.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mutation:
    name: str
    file: str
    before: str
    after: str
    test: str


MUTATIONS = (
    Mutation(
        "account-isolation",
        "messages.py",
        "cursor.account != account",
        "False",
        "tests/test_messages.py::test_foreign_folder_account_and_invalid_history_fail_before_any_login",
    ),
    Mutation(
        "bounded-account-queue",
        "scheduler.py",
        "len(state.queue) >= self._limits.queued_requests_per_account",
        "False",
        "tests/test_scheduler.py::test_global_and_account_queue_limits_reject_without_dispatch",
    ),
    Mutation(
        "bounded-global-queue",
        "scheduler.py",
        "self._queued >= self._limits.queued_requests",
        "False",
        "tests/test_scheduler.py::test_global_and_account_queue_limits_reject_without_dispatch",
    ),
    Mutation(
        "bounded-bodies",
        "transport.py",
        "if len(body) + len(chunk) > self._limits.response_max_bytes:\n"
        "                raise LibrusError(ErrorKind.LIMIT)\n"
        "            body.extend(chunk)\n        if inflater",
        "if False:\n                raise LibrusError(ErrorKind.LIMIT)\n"
        "            body.extend(chunk)\n        if inflater",
        "tests/test_transport.py::test_body_limits_apply_before_decoding_or_parsing[compressed]",
    ),
    Mutation(
        "bounded-pages",
        "messages.py",
        "if count > MESSAGE_MAX_PAGE_COUNT:",
        "if False:",
        "tests/test_messages.py::test_page_and_row_actual_maximum_boundaries",
    ),
    Mutation(
        "send-non-retry",
        "service.py",
        "if not retry_safe:\n                raise",
        "if False:\n                raise",
        "tests/test_sending.py::test_dispatched_failure_or_response_has_one_attempt_and_explicit_outcome[401]",
    ),
    Mutation(
        "checkpoint-ordering",
        "service.py",
        "                    await checkpoint(accepted)",
        "                    await self._decode_schedule(accepted, budget)\n"
        "                    await checkpoint(accepted)",
        "tests/test_notification_checkpoints.py::test_encoded_payload_is_durable_before_decoding_or_parser_failure[markup]",
    ),
    Mutation(
        "redirect-rejection",
        "service.py",
        "            raise LibrusError(ErrorKind.ACCESS_DENIED)\n"
        "        if response.status != 200 or _media_type(response) != content_type:",
        "            return\n"
        "        if response.status != 200 or _media_type(response) != content_type:",
        "tests/test_account_reads.py::test_module_redirect_is_typed_without_following_or_reauthenticating",
    ),
)


def run_test(root: Path, test: str, report: Path) -> tuple[int, list[str]]:
    environment = os.environ | {
        "PYTHONPATH": str(root / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-x",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            f"--junitxml={report}",
            test,
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )
    tree = ET.parse(report)
    if tree.findall(".//error") or result.returncode not in (0, 1):
        raise RuntimeError(f"pytest harness error for {test}: {result.stdout[-3000:]}")
    failures = [node.get("message", "") for node in tree.findall(".//failure")]
    if any("TimeoutError" in failure for failure in failures):
        raise RuntimeError(f"timeout is not mutation evidence: {test}")
    return result.returncode, failures


def main() -> None:
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="guard-mutations-") as directory:
        root = Path(directory)
        for name in ("src", "tests", "scripts", "contracts"):
            shutil.copytree(
                source / name,
                root / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        shutil.copy2(source / "pyproject.toml", root)
        results = []
        for mutation in MUTATIONS:
            path = root / "src/librus_python_api" / mutation.file
            original = path.read_text()
            if original.count(mutation.before) != 1:
                raise RuntimeError(f"mutation anchor drift: {mutation.name}")
            baseline, failures = run_test(root, mutation.test, root / "baseline.xml")
            if baseline or failures:
                raise RuntimeError(f"failing baseline: {mutation.name}: {failures}")
            try:
                path.write_text(original.replace(mutation.before, mutation.after, 1))
                code, failures = run_test(root, mutation.test, root / "mutant.xml")
            finally:
                path.write_text(original)
            killed = code == 1 and bool(failures)
            results.append(
                {
                    "guard": mutation.name,
                    "killed": killed,
                    "test": mutation.test,
                    "failures": failures,
                }
            )
            print(json.dumps(results[-1]), flush=True)
        if not all(row["killed"] for row in results):
            raise SystemExit("Survivors require investigation; no score target applies")


if __name__ == "__main__":
    main()
