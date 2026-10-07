"""The live-check transport can only make declared, side-effect-free reads."""

import asyncio

import pytest

from librus_python_api import RequestBudget
from librus_python_api.config import ENDPOINTS
from librus_python_api.exceptions import ErrorKind, LibrusError
from scripts.live_check.guard import EXCLUDED, SAFE, guarded

UNSAFE = sorted(
    name
    for name, endpoint in ENDPOINTS.items()
    if not name.startswith("login_")
    and (endpoint.side_effect not in SAFE or name in EXCLUDED)
)


def test_unsafe_routes_exist_in_the_contract() -> None:
    # Guards against a vacuous parametrization below.
    assert {
        "modern_content_received",
        "message_content_received",
        "consume_schedule_events",
        "modern_send_message",
        "attachment_download",
    } <= set(UNSAFE)


@pytest.mark.parametrize("name", UNSAFE)
def test_an_unsafe_or_excluded_route_cannot_be_declared(name: str) -> None:
    with pytest.raises(ValueError):
        guarded({name}, ())


def test_unknown_routes_and_unlisted_references_are_rejected() -> None:
    with pytest.raises(KeyError):
        guarded({"no_such_route"}, ())
    with pytest.raises(ValueError):
        guarded({"identity"}, {"agenda_detail"})


def refused(transport: object, call: str, *args: object, **kwargs: object) -> None:
    with pytest.raises(LibrusError) as error:
        asyncio.run(getattr(transport, call)(*args, **kwargs))
    assert error.value.kind is ErrorKind.UNSUPPORTED_CAPABILITY


def test_undeclared_reads_and_unlisted_references_are_refused_and_recorded() -> None:
    cls = guarded({"identity", "agenda_detail"}, ())
    transport = cls.__new__(cls)
    refused(
        transport,
        "request",
        "modern_content_received",
        RequestBudget(),
        reference_id="19001",
    )
    refused(transport, "request", "agenda_detail", RequestBudget(), reference_id="123")
    assert cls.violations == ["modern_content_received", "agenda_detail"]


@pytest.mark.parametrize(
    "call",
    [
        "send_message",
        "send_modern_message",
        "consume_schedule_events",
        "resolve_attachment",
        "resolve_modern_attachment",
        "stream_download",
    ],
)
def test_side_effect_and_file_methods_are_always_refused(call: str) -> None:
    cls = guarded({"identity"}, ())
    refused(cls.__new__(cls), call)
    assert len(cls.violations) == 1


def test_each_profile_transport_keeps_its_own_violations() -> None:
    first, second = guarded({"identity"}, ()), guarded({"identity"}, ())
    refused(first.__new__(first), "send_message")
    assert first.violations and not second.violations
