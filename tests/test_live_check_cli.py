"""The CLI fails loudly on missing configuration and prints nothing sensitive."""

import json
import logging
import sys
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

import scripts.live_check.__main__ as cli
from scripts.live_check.credentials import (
    MissingSecrets,
    from_environment,
    from_file,
)

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
