"""The CLI fails loudly on missing configuration and prints nothing sensitive."""

import json
import logging
import sys
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

import scripts.live_check.__main__ as cli
import scripts.live_check.runner as runner
from librus_python_api import ConnectionSettings
from scripts.live_check.credentials import (
    MissingSecrets,
    from_environment,
    from_file,
)
from tests.http_support import serve
from tests.live_check_support import WeeklyFixture

CANARY = "canary-password-value-7f3a"


@pytest.fixture(autouse=True)
def process_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """main() silences logging and warnings process-wide; undo that per test."""
    monkeypatch.setattr(sys, "unraisablehook", sys.unraisablehook)
    level = logging.root.manager.disable
    with warnings.catch_warnings():
        yield
    logging.disable(level)


def env(**values: str) -> dict[str, str]:
    return {f"LIBRUS_LIVE_{key}": value for key, value in values.items()}


def test_two_complete_slots_are_loaded() -> None:
    accounts, identities = from_environment(
        env(
            LOGIN_0="a",
            PASSWORD_0=CANARY,
            IDENTITY_0="1:2",
            LOGIN_1="b",
            PASSWORD_1=CANARY,
            IDENTITY_1="3:4",
        )
    )
    assert list(accounts) == ["slot-0", "slot-1"]
    assert identities == {"slot-0": "1:2", "slot-1": "3:4"}


@pytest.mark.parametrize(
    "values,missing",
    [
        (
            {},
            (
                "LIBRUS_LIVE_LOGIN_0",
                "LIBRUS_LIVE_PASSWORD_0",
                "LIBRUS_LIVE_IDENTITY_0",
            ),
        ),
        # GitHub passes an unset secret as an empty string.
        (
            env(LOGIN_0="a", PASSWORD_0="", IDENTITY_0="1:2"),
            ("LIBRUS_LIVE_PASSWORD_0",),
        ),
        (
            env(LOGIN_0="a", PASSWORD_0=CANARY, IDENTITY_0="1:2", LOGIN_1="b"),
            ("LIBRUS_LIVE_PASSWORD_1", "LIBRUS_LIVE_IDENTITY_1"),
        ),
        (
            env(LOGIN_1="b", PASSWORD_1=CANARY, IDENTITY_1="3:4"),
            (
                "LIBRUS_LIVE_LOGIN_0",
                "LIBRUS_LIVE_PASSWORD_0",
                "LIBRUS_LIVE_IDENTITY_0",
            ),
        ),
    ],
)
def test_missing_or_partial_slots_name_only_the_missing_secrets(
    values: dict[str, str], missing: tuple[str, ...]
) -> None:
    with pytest.raises(MissingSecrets) as error:
        from_environment(values)
    assert error.value.names == missing


def test_missing_secrets_fail_the_cli_without_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(
        ["run", "--profile", "weekly", "--from-env", "--record"],
        env(LOGIN_0="canary-login", PASSWORD_0=CANARY),
    )
    out, err = capsys.readouterr()
    assert code == 1
    assert json.loads(out) == {
        "passed": False,
        "missing_secrets": ["LIBRUS_LIVE_IDENTITY_0"],
    }
    assert CANARY not in out + err and "canary-login" not in out + err


def test_an_unexpected_crash_prints_only_its_class_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def explode(*_: object, **__: object) -> None:
        raise RuntimeError(f"connect failed for canary-login:{CANARY} Fixture Student")

    monkeypatch.setattr(cli, "run_profile", explode)
    code = cli.main(
        ["run", "--profile", "weekly", "--from-env", "--record"],
        env(LOGIN_0="canary-login", PASSWORD_0=CANARY, IDENTITY_0="1:2"),
    )
    out, err = capsys.readouterr()
    assert code == 1
    assert json.loads(out) == {"passed": False, "crash": "RuntimeError"}
    for canary in (CANARY, "canary-login", "Fixture"):
        assert canary not in out + err


def test_identity_printing_is_refused_in_ci(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(
        json.dumps({"accounts": [{"username": "a", "password": CANARY}]})
    )
    secrets_file.chmod(0o600)
    code = cli.main(
        ["identity", "--secrets", str(secrets_file)], {"GITHUB_ACTIONS": "true"}
    )
    out, _ = capsys.readouterr()
    assert code == 1 and CANARY not in out


def test_weekly_needs_expectations_or_record_mode() -> None:
    with pytest.raises(SystemExit):
        cli.main(["run", "--profile", "weekly", "--from-env"], {})


def test_a_world_readable_secrets_file_is_rejected(tmp_path: Path) -> None:
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(json.dumps({"accounts": []}))
    secrets_file.chmod(0o644)
    with pytest.raises(SystemExit):
        from_file(secrets_file)


def loopback(fixture: WeeklyFixture, logins: tuple[str, ...]) -> object:
    """The real runner, pointed at the loopback fixture instead of Librus."""

    async def run(*args: Any, **kwargs: Any) -> Any:
        fixture.aliases = logins
        async with (
            serve(fixture.app()) as native,
            serve(fixture.modern_app()) as modern,
        ):
            fixture.origin, fixture.modern_origin = native, modern
            kwargs["connection"] = ConnectionSettings(
                synergia_origin=native,
                api_origin=native,
                messages_origin=modern,
                download_origin=fixture.download_origin,
            )
            return await runner.run_profile(*args, **kwargs)

    return run


def broken_grades(fixture: WeeklyFixture) -> None:
    fixture.bodies["grades"] = (b"<html>Fixture broken page</html>", "text/html")


OUTCOMES: list[tuple[str, str, Callable[[WeeklyFixture], None], str]] = [
    ("success", "canary-login-a", lambda _: None, ""),
    ("rejected", "rejected", lambda _: None, "credentials_rejected"),
    (
        "throttled",
        "canary-login-a",
        lambda f: f.failures.update(student_information=[429]),
        "throttled",
    ),
    (
        "maintenance",
        "canary-login-a",
        lambda f: f.failures.update(student_information=[503]),
        "maintenance",
    ),
    ("parse", "canary-login-a", broken_grades, "parse"),
]


@pytest.mark.parametrize(
    "login,arrange,kind",
    [case[1:] for case in OUTCOMES],
    ids=[case[0] for case in OUTCOMES],
)
def test_every_outcome_is_classified_without_leaking(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    login: str,
    arrange: Callable[[WeeklyFixture], None],
    kind: str,
) -> None:
    fixture = WeeklyFixture()
    arrange(fixture)
    monkeypatch.setattr(cli, "run_profile", loopback(fixture, (login,)))
    summary = tmp_path / "summary.md"
    code = cli.main(
        ["run", "--profile", "weekly", "--from-env", "--record"]
        + ["--summary", str(summary)],
        env(LOGIN_0=login, PASSWORD_0=CANARY, IDENTITY_0="301:student-shared"),
    )
    out, err = capsys.readouterr()
    written = summary.read_text()
    assert code == (1 if kind else 0)
    assert written.startswith("## Live check: weekly")
    if kind:
        assert f'"kind": "{kind}"' in out
    for canary in (CANARY, "canary-login", "Fixture", "Synthetic", "student-shared"):
        assert canary not in out + err + written


def test_recorded_expectations_pass_and_drift_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    secrets = env(
        LOGIN_0="canary-login-a", PASSWORD_0=CANARY, IDENTITY_0="301:student-shared"
    )
    weekly = ["run", "--profile", "weekly", "--from-env"]
    monkeypatch.setattr(
        cli, "run_profile", loopback(WeeklyFixture(), ("canary-login-a",))
    )
    assert cli.main([*weekly, "--record"], secrets) == 0
    recorded = json.loads(capsys.readouterr().out.split("\n}\n", 1)[1])
    recorded["slots"]["0"]["role"] = "student"
    expectations = tmp_path / "expectations.json"
    expectations.write_text(json.dumps(recorded))
    compare = [*weekly, "--expectations", str(expectations)]

    monkeypatch.setattr(
        cli, "run_profile", loopback(WeeklyFixture(), ("canary-login-a",))
    )
    assert cli.main(compare, secrets) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True

    drifted = WeeklyFixture()
    broken_grades(drifted)
    monkeypatch.setattr(cli, "run_profile", loopback(drifted, ("canary-login-a",)))
    assert cli.main(compare, secrets) == 1
    assert "slot 0 grades: parse" in json.loads(capsys.readouterr().out)["problems"]
