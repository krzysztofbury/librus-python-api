"""Credential sources for live checks. Values are never printed or logged."""

import json
from collections.abc import Mapping
from pathlib import Path

from librus_python_api import AccountCredentials

MAX_SLOTS = 2
FIELDS = ("LOGIN", "PASSWORD", "IDENTITY")


class MissingSecrets(Exception):
    """Configuration is incomplete. Carries secret names, never values."""

    def __init__(self, names: tuple[str, ...]) -> None:
        super().__init__("missing secrets")
        self.names = names


def from_environment(
    environ: Mapping[str, str],
) -> tuple[dict[str, AccountCredentials], dict[str, str]]:
    accounts: dict[str, AccountCredentials] = {}
    identities: dict[str, str] = {}
    missing: list[str] = []
    for slot in range(MAX_SLOTS):
        names = [f"LIBRUS_LIVE_{field}_{slot}" for field in FIELDS]
        values = [environ.get(name, "") for name in names]
        if slot > 0 and not any(values):
            continue
        missing += [
            name for name, value in zip(names, values, strict=True) if not value
        ]
        if all(values):
            alias = f"slot-{slot}"
            accounts[alias] = AccountCredentials(login=values[0], password=values[1])
            identities[alias] = values[2]
    if missing:
        raise MissingSecrets(tuple(missing))
    return accounts, identities


def from_file(path: Path) -> dict[str, AccountCredentials]:
    status = path.stat()
    if status.st_mode & 0o077 or status.st_size > 1048576:
        raise SystemExit("Private credentials rejected")
    records = json.loads(path.read_text())["accounts"]
    return {
        f"slot-{index}": AccountCredentials(
            login=record["username"], password=record["password"]
        )
        for index, record in enumerate(records)
    }
