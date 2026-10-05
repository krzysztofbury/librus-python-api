"""Public account pseudonym binding and platform refusal, without upstream access."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from librus_python_api import AccountCredentials, ConnectionSettings, LibrusService
from librus_python_api.exceptions import InvalidInputError, UnsupportedCapabilityError
from librus_python_api.notification_persistence import NotificationStore
from librus_python_api.persistence import PersistenceStore
from tests.http_support import FIXTURE_SECRET


def test_account_identifiers_require_the_application_secret_and_bind_every_origin() -> (
    None
):
    async def scenario() -> None:
        accounts = {
            "fixture": AccountCredentials(login="10001", password=FIXTURE_SECRET)
        }
        key = bytes(range(32))
        async with LibrusService(accounts, context_key=key) as service:
            original = service.account("fixture").context
        # Independent OpenSSL HMAC-SHA256 vector for the documented v2 message.
        assert original.identifier == (
            "c18c8a32e73caa3dd0d033e76c647522a0fdd41e19697c7e2ba2a11eec24a93b"
        )
        async with LibrusService(accounts, context_key=key) as restarted:
            assert restarted.account("fixture").context == original
        async with LibrusService(accounts, context_key=bytes(reversed(key))) as other:
            assert other.account("fixture").context.identifier != original.identifier
        settings = ConnectionSettings()
        # The former login-only dictionary attack cannot reproduce this identifier.
        former = hashlib.sha256(
            json.dumps(
                [
                    1,
                    "fixture",
                    "10001",
                    settings.synergia_origin,
                    settings.api_origin,
                    settings.messages_origin,
                ],
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert original.identifier != former
        assert len(original.identifier) == 64
        for changed in (
            ConnectionSettings(synergia_origin="http://localhost:8080"),
            ConnectionSettings(api_origin="http://localhost:8080"),
            ConnectionSettings(messages_origin="http://localhost:8080"),
        ):
            async with LibrusService(
                accounts, context_key=key, connection=changed
            ) as other:
                assert (
                    other.account("fixture").context.identifier != original.identifier
                )
        assert "10001" not in repr(original)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "key", [None, "x" * 32, b"", b"x" * 31, b"x" * 33, bytearray(32)]
)
def test_invalid_context_key_is_rejected_before_any_transport(key: Any) -> None:
    with pytest.raises(InvalidInputError) as error:
        LibrusService({}, context_key=key)
    assert error.value.__context__ is None
    assert str(error.value) == "invalid_input"


@pytest.mark.parametrize("kind", [PersistenceStore, NotificationStore])
def test_non_posix_storage_refuses_before_creating_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: type
) -> None:
    async def scenario() -> None:
        directory = tmp_path / "uncreated"
        store = kind(directory)
        with monkeypatch.context() as patch:
            patch.setattr("librus_python_api._storage.os.name", "nt")
            with pytest.raises(UnsupportedCapabilityError):
                await store.open()
        assert not directory.exists()

    asyncio.run(scenario())
