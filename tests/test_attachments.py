"""Owning public stream wire, isolation, bounds and joined-lifecycle contracts."""

import asyncio
import gzip
from dataclasses import replace
from typing import Any

import pytest

from librus_python_api import (
    ConnectionSettings,
    OperationLimits,
    RequestBudget,
    SchedulerLimits,
)
from librus_python_api.attachment_routes import signed_attachment_key
from librus_python_api.exceptions import (
    AccessDeniedError,
    ClosedError,
    ConnectionError,
    InvalidInputError,
    LibrusError,
    LimitError,
    OperationTimeoutError,
    ParseError,
    SessionExpiredError,
    UnsupportedCapabilityError,
)
from librus_python_api.transport import AiohttpTransport
from tests.attachments_support import queued, reference, rig


def test_unservable_controls_and_ambiguous_encoding_fail_before_url_normalization() -> (
    None
):
    for suffix in (
        "\nkey",
        "\tkey",
        "key\x7f",
        "key\\extra",
        "key\u00e9",
        "key%2fextra",
    ):
        with pytest.raises(AccessDeniedError):
            signed_attachment_key(
                "https://sandbox.librus.pl/GetFile/" + suffix, ConnectionSettings()
            )
    assert (
        signed_attachment_key(
            "https://sandbox.librus.pl:443/GetFile/Fixture-Key_123",
            ConnectionSettings(),
        )
        == "Fixture-Key_123"
    )
    for location in (
        "http://sandbox.librus.pl/GetFile/key",
        "https://sandbox.librus.pl:444/GetFile/key",
    ):
        with pytest.raises(AccessDeniedError):
            signed_attachment_key(location, ConnectionSettings())


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Encoding", "identity"), ("Content-Encoding", "gzip")],
        [("Content-Encoding", "identity"), ("Content-Encoding", "identity")],
        [("Transfer-Encoding", "gzip")],
        [("Transfer-Encoding", "gzip, chunked")],
        [("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")],
        [("Transfer-Encoding", "chunked")],
    ],
)
def test_unsupported_or_ambiguous_wire_encodings_never_deliver_file_bytes(
    headers: list[tuple[str, str]],
) -> None:
    async def scenario() -> None:
        workers: set[asyncio.Task[Any]] = set()
        payload = gzip.compress(b"independently authored plaintext")

        async def raw_download(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            task = asyncio.current_task()
            assert task is not None
            workers.add(task)
            try:
                await reader.readuntil(b"\r\n\r\n")
                values = list(headers)
                is_chunked = any(
                    "chunked" in value
                    for key, value in headers
                    if key == "Transfer-Encoding"
                )
                if not any(key == "Transfer-Encoding" for key, _ in headers):
                    values.append(("Content-Length", str(len(payload))))
                encoded = b"".join(f"{k}: {v}\r\n".encode() for k, v in values)
                body = (
                    f"{len(payload):x}\r\n".encode() + payload + b"\r\n0\r\n\r\n"
                    if is_chunked
                    else payload
                )
                writer.write(
                    b"HTTP/1.1 200 OK\r\n"
                    + encoded
                    + b"Connection: close\r\n\r\n"
                    + body
                )
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                workers.discard(task)

        server = await asyncio.start_server(raw_download, "127.0.0.1", 0)
        assert server.sockets is not None
        origin = f"http://localhost:{server.sockets[0].getsockname()[1]}"
        try:
            async with rig(download_origin_override=origin) as (_, service):
                stream = service.account("student").stream_attachment(reference())
                delivered = 0
                if headers == [("Transfer-Encoding", "chunked")]:
                    async with stream:
                        assert b"".join([chunk async for chunk in stream]) == payload
                        assert stream.complete
                else:
                    with pytest.raises(UnsupportedCapabilityError) as failure:
                        async with stream:
                            async for chunk in stream:
                                delivered += len(chunk)
                    assert failure.value.__context__ is failure.value.__cause__ is None
                    assert delivered == 0 and not stream.complete
                assert service.snapshot().active == service.snapshot().queued == 0
        finally:
            server.close()
            await server.wait_closed()
            await asyncio.gather(*workers)

    asyncio.run(scenario())


def test_actual_maximum_file_streams_in_bounded_chunks() -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            fixture.body = b"x" * 65536
            fixture.repetitions = 800
            fixture.declared = 50 * 1024 * 1024
            budget = RequestBudget(max_requests=7, max_response_bytes=54 * 1024 * 1024)
            total = 0
            async with service.account("student").stream_attachment(
                reference(), budget=budget
            ) as stream:
                async for chunk in stream:
                    assert 1 <= len(chunk) <= 65536
                    assert chunk == b"x" * len(chunk)
                    total += len(chunk)
                assert stream.complete
            assert total == 50 * 1024 * 1024
            assert budget.requests_dispatched == 7
            assert budget.response_bytes >= total

    asyncio.run(scenario())


def test_mixed_four_account_downloads_and_reads_share_global_saturation() -> None:
    async def scenario() -> None:
        aliases = ("student", "parent", "other-student", "other-parent")
        limits = SchedulerLimits(requests_per_second=1000, burst=40, active_requests=2)
        async with rig(aliases, scheduler_limits=limits) as (fixture, service):
            for alias in aliases:
                await service.account(alias).identity()
            fixture.body = b"x" * 262144
            # Open the first two streams without consuming them: these keep both
            # scheduler slots. Other account downloads and ordinary reads queue.
            first = service.account(aliases[0]).stream_attachment(reference(aliases[0]))
            second = service.account(aliases[1]).stream_attachment(
                reference(aliases[1])
            )
            await first.__aenter__()
            await second.__aenter__()
            budget = RequestBudget(max_requests=6, max_response_bytes=2 * 1024 * 1024)

            async def consume(alias: str) -> int:
                size = 0
                async with service.account(alias).stream_attachment(
                    reference(alias), budget=budget
                ) as stream:
                    async for chunk in stream:
                        size += len(chunk)
                    assert stream.complete
                return size

            tasks = [asyncio.create_task(consume(alias)) for alias in aliases[2:]]
            reads = [
                asyncio.create_task(
                    service.account(alias).student_information(budget=budget)
                )
                for alias in aliases[2:]
            ]
            await queued(service, 2)
            assert service.snapshot().active == 2
            assert len(fixture.downloads) == 2
            await first.aclose()
            await second.aclose()
            assert await asyncio.gather(*tasks) == [262144, 262144]
            await asyncio.gather(*reads)
            assert budget.requests_dispatched == 6
            assert len(fixture.resolutions) == len(fixture.downloads) == 4
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_repeated_cancellation_waits_for_transport_cleanup_before_releasing_slots() -> (
    None
):
    async def scenario() -> None:
        cleanup_started, cleanup_release = asyncio.Event(), asyncio.Event()

        class DelayedCleanupTransport(AiohttpTransport):
            async def _download_exchange(self, *args: Any, **kwargs: Any) -> None:
                try:
                    await super()._download_exchange(*args, **kwargs)
                finally:
                    cleanup_started.set()
                    await cleanup_release.wait()

        async with rig(transport_factory=DelayedCleanupTransport) as (fixture, service):
            fixture.body_hold = asyncio.Event()

            async def consume() -> None:
                async with service.account("student").stream_attachment(
                    reference()
                ) as stream:
                    async for _ in stream:
                        pass

            task = asyncio.create_task(consume())
            await asyncio.wait_for(fixture.body_started.wait(), 2)
            task.cancel()
            await asyncio.wait_for(cleanup_started.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and service.snapshot().active == 1
            cleanup_release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert service.snapshot().active == service.snapshot().queued == 0
            await service.account("student").student_information()

    asyncio.run(scenario())


def test_shared_budget_includes_resolution_and_download_bytes_and_requests() -> None:
    async def scenario() -> None:
        async with rig(("student", "parent")) as (fixture, service):
            for alias in ("student", "parent"):
                await service.account(alias).identity()
            budget = RequestBudget(
                max_requests=4, max_response_bytes=len(fixture.body) * 2
            )
            for alias in ("student", "parent"):
                async with service.account(alias).stream_attachment(
                    reference(alias), budget=budget
                ) as stream:
                    assert b"".join([chunk async for chunk in stream]) == fixture.body
            assert budget.requests_dispatched == 4
            assert budget.response_bytes == len(fixture.body) * 2
            with pytest.raises(LimitError):
                async with service.account("student").stream_attachment(
                    reference(), budget=budget
                ):
                    pytest.fail(
                        "Exhausted shared budget admitted another source request"
                    )
            assert len(fixture.resolutions) == len(fixture.downloads) == 2

    asyncio.run(scenario())


def test_lazy_non_reentrant_context_shares_operation_ceiling() -> None:
    async def scenario() -> None:
        limits = SchedulerLimits(operations=1, operations_per_account=1)
        async with rig(scheduler_limits=limits) as (fixture, service):
            client = service.account("student")
            stream = client.stream_attachment(reference())
            assert fixture.calls == []
            with pytest.raises(InvalidInputError):
                _ = stream.metadata
            async with stream:
                with pytest.raises(InvalidInputError):
                    await stream.__aenter__()
                with pytest.raises(LimitError):
                    await client.student_information()
            await client.student_information()
            assert not stream.complete
            with pytest.raises(InvalidInputError):
                await stream.__aenter__()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,error",
    [(200, ParseError), (401, SessionExpiredError), (403, AccessDeniedError)],
)
def test_resolver_status_is_not_replayed_or_misclassified_as_login_expiry(
    status: int, error: type[LibrusError]
) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            fixture.resolve_status = status
            fixture.location = fixture.origin + "/loguj"
            with pytest.raises(error):
                async with service.account("student").stream_attachment(reference()):
                    pytest.fail("Bad resolver status succeeded")
            assert fixture.logins == {"student": 1}
            assert len(fixture.resolutions) == 1 and fixture.downloads == []

    asyncio.run(scenario())


def test_signed_server_denial_does_not_invalidate_authenticated_source_session() -> (
    None
):
    async def scenario() -> None:
        async with rig() as (fixture, service):
            fixture.download_status = 401
            client = service.account("student")
            with pytest.raises(AccessDeniedError):
                async with client.stream_attachment(reference()):
                    pytest.fail("Anonymous denial was accepted")
            await client.student_information()
            assert fixture.logins == {"student": 1}

    asyncio.run(scenario())


def test_account_isolation_two_hops_no_cookie_forwarding_and_no_stream_cache() -> None:
    async def scenario() -> None:
        async with rig(("student", "parent")) as (fixture, service):
            for alias in ("student", "parent", "student"):
                client = service.account(alias)
                stream = client.stream_attachment(reference(alias))
                assert not stream.complete
                async with stream:
                    assert stream.metadata.identity.owner.id == alias
                    assert stream.metadata.reference == reference(alias)
                    assert stream.metadata.headers.content_length == len(fixture.body)
                    assert "Fixture" not in repr(stream.metadata)
                    result = b"".join([chunk async for chunk in stream])
                    assert result == b"original invented attachment bytes\n"
                    assert stream.complete
                await stream.aclose()
            assert fixture.logins == {"student": 1, "parent": 1}
            assert fixture.resolutions == ["student", "parent", "student"]
            assert len(fixture.downloads) == 3
            for headers in fixture.downloads:
                assert not {k.lower() for k in headers} & {
                    "cookie",
                    "authorization",
                    "origin",
                    "referer",
                }
                assert headers["Accept-Encoding"] == "identity"
            assert service.snapshot().requests_dispatched == 16
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("value", [0, -1, True, 52428801, "1"])
def test_invalid_reference_and_limits_fail_before_any_login(value: Any) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            client = service.account("student")
            with pytest.raises(InvalidInputError):
                client.stream_attachment(reference(), max_bytes=value)
            ref = reference()
            for invalid in (
                "301",
                replace(ref, identifier="../301"),
                replace(ref, identifier=True),  # type: ignore[arg-type]
                replace(ref, message=replace(ref.message, account="parent")),
                replace(ref, message=replace(ref.message, identifier="101?x=1")),
                replace(ref, message=replace(ref.message, folder="received")),  # type: ignore[arg-type]
            ):
                with pytest.raises(InvalidInputError):
                    client.stream_attachment(invalid)  # type: ignore[arg-type]
            assert fixture.calls == []
            assert fixture.downloads == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "location",
    [
        "https://example.invalid/GetFile/key",
        "https://sandbox.librus.pl.evil.invalid/GetFile/key",
        "https://user:secret@sandbox.librus.pl/GetFile/key",
        "https://sandbox.librus.pl:444/GetFile/key",
        "http://sandbox.librus.pl/GetFile/key",
        "/GetFile/key",
        "//sandbox.librus.pl/GetFile/key",
        "https://sandbox.librus.pl/GetFile/..",
        "https://sandbox.librus.pl/GetFile/%2e%2e",
        "https://sandbox.librus.pl/GetFile/key/get",
        "https://sandbox.librus.pl/GetFile/key?",
        "https://sandbox.librus.pl/GetFile/key#",
        "https://sandbox.librus.pl/GetFile/",
        "",
        "https://sandbox.librus.pl/GetFile/" + "x" * 513,
    ],
)
def test_malicious_destination_never_dispatches_a_download(location: str) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            fixture.location = location.replace(
                "https://sandbox.librus.pl/", fixture.download_origin + "/"
            )
            with pytest.raises(AccessDeniedError) as error:
                async with service.account("student").stream_attachment(reference()):
                    pytest.fail("Untrusted redirect was accepted")
            assert error.value.__cause__ is error.value.__context__ is None
            assert len(fixture.resolutions) == 1 and fixture.downloads == []
            assert fixture.logins == {"student": 1}
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_download_origin_override_cannot_expand_official_scope() -> None:
    for value in (
        "https://example.invalid",
        "http://sandbox.librus.pl",
        "https://sandbox.librus.pl:444",
        "https://sandbox.librus.pl/path",
    ):
        with pytest.raises(InvalidInputError):
            ConnectionSettings(download_origin=value)


@pytest.mark.parametrize(
    "mode", ["declared", "chunked", "budget", "encoding", "truncate"]
)
def test_body_bounds_encoding_and_framing_fail_without_complete_or_raw_causes(
    mode: str,
) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            client = service.account("student")
            await client.identity()
            fixture.body = b"x" * 65
            budget = RequestBudget(
                max_response_bytes=64 if mode == "budget" else 1048576
            )
            if mode in {"chunked", "budget"}:
                fixture.body_hold = asyncio.Event()
            if mode == "encoding":
                fixture.encoding = "gzip"
            if mode == "truncate":
                fixture.truncate = True
                fixture.declared = 100
            stream = client.stream_attachment(
                reference(),
                max_bytes=64 if mode in {"declared", "chunked"} else 100,
                budget=budget,
            )
            expected = (
                UnsupportedCapabilityError
                if mode == "encoding"
                else ParseError
                if mode == "truncate"
                else LimitError
            )
            with pytest.raises(expected) as failure:
                async with stream:
                    async for _ in stream:
                        pass
            assert not stream.complete
            assert failure.value.__cause__ is failure.value.__context__ is None
            assert "Fixture-Key" not in repr(failure.value)
            assert len(fixture.resolutions) == len(fixture.downloads) == 1
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [0, 64, 262144])
def test_exact_byte_limit_and_bounded_chunks_finish_only_after_eof(size: int) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            fixture.body = (
                bytes(range(256)) * (size // 256) if size > 64 else b"x" * size
            )
            stream = service.account("student").stream_attachment(
                reference(), max_bytes=max(1, size)
            )
            async with stream:
                chunks = [chunk async for chunk in stream]
                assert b"".join(chunks) == fixture.body
                assert all(1 <= len(chunk) <= 65536 for chunk in chunks)
                assert stream.complete
                assert service.snapshot().active == 0

    asyncio.run(scenario())


def test_streaming_backpressure_early_break_and_single_consumer_keep_shared_slot() -> (
    None
):
    async def scenario() -> None:
        limits = SchedulerLimits(requests_per_second=1000, burst=40, active_requests=1)
        async with rig(("student", "parent"), scheduler_limits=limits) as (
            fixture,
            service,
        ):
            await service.account("parent").identity()
            fixture.body_hold = asyncio.Event()
            stream = service.account("student").stream_attachment(reference())
            async with stream:
                chunk = await anext(stream)
                assert chunk == fixture.body and not stream.complete
                with pytest.raises(InvalidInputError):
                    await asyncio.create_task(anext(stream))
                other = asyncio.create_task(
                    service.account("parent").student_information()
                )
                await queued(service)
                assert service.snapshot().active == 1 and not other.done()
            await other
            assert not stream.complete
            assert service.snapshot().active == service.snapshot().queued == 0

    asyncio.run(scenario())


def test_deadline_expires_when_consumer_is_paused_and_frees_operation_capacity() -> (
    None
):
    async def scenario() -> None:
        async with rig(
            operation_limits=OperationLimits(max_requests=32, timeout_seconds=0.15)
        ) as (fixture, service):
            client = service.account("student")
            await client.identity()
            stream = client.stream_attachment(reference())
            async with stream:
                assert stream.metadata.headers.content_length is not None
                await asyncio.sleep(0.2)
                assert service.snapshot().active == service.snapshot().queued == 0
                with pytest.raises(OperationTimeoutError):
                    await anext(stream)
                assert not stream.complete
            await client.student_information()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "stage", ["resolve", "headers", "body", "queue", "service_close"]
)
def test_cancellation_or_service_close_joins_every_owned_stage(stage: str) -> None:
    async def scenario() -> None:
        async with rig(
            ("student", "parent"),
            scheduler_limits=SchedulerLimits(
                requests_per_second=1000, burst=40, active_requests=1
            ),
        ) as (fixture, service):
            client = service.account("student")
            await client.identity()
            await service.account("parent").identity()
            blocker = None
            if stage == "queue":
                fixture.body_hold = asyncio.Event()
                blocker = client.stream_attachment(reference())
                await blocker.__aenter__()
                client = service.account("parent")
            if stage == "resolve":
                fixture.resolve_hold = asyncio.Event()
            if stage == "headers":
                fixture.headers_hold = asyncio.Event()
            if stage in {"body", "service_close"}:
                fixture.body_hold = asyncio.Event()
            stream = client.stream_attachment(
                reference("parent" if stage == "queue" else "student")
            )

            async def consume() -> None:
                async with stream:
                    async for _ in stream:
                        pass

            task = asyncio.create_task(consume())
            if stage == "queue":
                await queued(service)
            elif stage == "resolve":
                await asyncio.wait_for(fixture.resolve_started.wait(), 2)
            else:
                for _ in range(200):
                    if fixture.downloads:
                        break
                    await asyncio.sleep(0.001)
                assert fixture.downloads
            if stage == "service_close":
                await service.aclose()
                with pytest.raises(ClosedError):
                    await task
            else:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            if blocker is not None:
                await blocker.aclose()
            assert not stream.complete
            assert service.snapshot().active == service.snapshot().queued == 0
            if stage != "service_close":
                await client.student_information()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode", ["expiry", "foreign_redirect", "download_redirect", "download_disconnect"]
)
def test_expiry_and_unknown_delivery_never_reauthenticate_or_replay(mode: str) -> None:
    async def scenario() -> None:
        async with rig() as (fixture, service):
            if mode == "expiry":
                fixture.location = fixture.origin + "/loguj"
            elif mode == "foreign_redirect":
                fixture.location = "https://example.invalid/private-signed-key"
            elif mode == "download_redirect":
                fixture.download_status = 302
            else:
                fixture.disconnect = True
            expected = (
                SessionExpiredError
                if mode == "expiry"
                else ConnectionError
                if mode == "download_disconnect"
                else AccessDeniedError
            )
            with pytest.raises(expected):
                async with service.account("student").stream_attachment(
                    reference()
                ) as stream:
                    async for _ in stream:
                        pass
            assert fixture.logins == {"student": 1}
            assert len(fixture.resolutions) == 1
            assert len(fixture.downloads) == int(mode.startswith("download_"))

    asyncio.run(scenario())
