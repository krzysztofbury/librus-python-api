"""Original loopback writes with invented payloads and acknowledgements."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from tests.reads_support import ReadsFixture


def acknowledgement(message: str = "Wiadomość została wysłana.") -> str:
    return (
        f'<html><body><div class="container-background"><p>{message}</p>'
        "</div></body></html>"
    )


class SendFixture(ReadsFixture):
    def __init__(self) -> None:
        super().__init__()
        self.send_calls: list[tuple[str, list[tuple[str, str]], bytes]] = []
        self.send_started = asyncio.Event()
        self.send_hold: asyncio.Event | None = None
        self.send_status = 200
        self.send_body = acknowledgement()
        self.send_content_type = "text/html"
        self.send_headers: dict[str, str] = {}
        self.disconnect = False
        self.partial_response = False

    def handler(self, operation: str) -> Callable[[web.Request], Awaitable[Any]]:
        normal = super().handler(operation)
        if operation != "messages_sent":
            return normal

        async def handle(request: web.Request) -> web.StreamResponse:
            raw = await request.read()
            form = await request.post()
            if "wyslij" not in form:
                response = await normal(request)
                assert isinstance(response, web.Response)
                return response
            login = self.record(request)
            self.send_calls.append(
                (login, [(str(k), str(v)) for k, v in form.items()], raw)
            )
            self.send_started.set()
            if self.send_hold is not None:
                await self.send_hold.wait()
            if self.disconnect:
                assert request.transport is not None
                request.transport.close()
            if self.partial_response:
                response = web.StreamResponse(
                    headers={"Content-Type": "text/html", "Content-Length": "1000"}
                )
                await response.prepare(request)
                await response.write(b"<html><body><div")
                assert request.transport is not None
                request.transport.close()
                return response
            return web.Response(
                text=self.send_body,
                status=self.send_status,
                headers=self.send_headers,
                content_type=self.send_content_type,
            )

        return handle
