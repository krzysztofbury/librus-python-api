"""Single-use write attempts and independently authored acknowledgement parsing."""

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING, Literal

from librus_python_api.budget import RequestBudget
from librus_python_api.config import SEND_ACCEPTED_TEXT, SEND_REJECTED_TEXT
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.markup import text
from librus_python_api.models import (
    AccountContext,
    Identity,
    MessagingBackend,
    ModernSendSubmission,
    Observation,
    SendResult,
    SendStatus,
    SendSubmission,
)
from librus_python_api.parsers import page_notices, parse_page

if TYPE_CHECKING:
    from librus_python_api.service import AccountClient


def parse_send_acknowledgement(body: bytes) -> SendStatus:
    """Only one designated, exact result paragraph can establish acceptance."""
    document = parse_page(body)
    if page_notices(document):
        raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
    if document.xpath(
        '//*[contains(concat(" ",normalize-space(@class)," "),'
        '" container-message-content ")]'
    ):
        # A returned message body can quote the exact acknowledgement markup.
        # It is not a send acknowledgement, even inside a matching status div.
        raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
    results = document.xpath(
        '//div[contains(concat(" ",normalize-space(@class)," "),'
        '" container-background ")]/p'
    )
    if len(results) != 1:
        raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)
    result = text(results[0], 4096)
    if result == SEND_ACCEPTED_TEXT:
        return SendStatus.ACCEPTED
    if result == SEND_REJECTED_TEXT:
        return SendStatus.REJECTED
    raise LibrusError(ErrorKind.UNKNOWN_DELIVERY)


class SendAttempt:
    """One process-local attempt, not consent, durable storage or idempotency."""

    def __init__(
        self, client: "AccountClient", submission: SendSubmission | ModernSendSubmission
    ) -> None:
        self._client, self._submission = client, submission
        self._used = False
        self._outcome = SendResult(
            SendStatus.NOT_DISPATCHED,
            backend=MessagingBackend.MODERN
            if isinstance(submission, ModernSendSubmission)
            else MessagingBackend.LEGACY,
        )

    @property
    def submission(self) -> SendSubmission | ModernSendSubmission:
        return self._submission

    @property
    def used(self) -> bool:
        return self._used

    @property
    def account_context(self) -> AccountContext:
        return self._client.context

    @property
    def outcome(self) -> SendResult:
        return self._outcome

    async def execute(self, *, budget: RequestBudget | None = None) -> SendResult:
        if self._used:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        # Consume synchronously before the first await, including pre-I/O failure.
        self._used = True
        try:
            return await self._client._execute_send(self, budget)
        except asyncio.CancelledError:
            self._failure("cancelled")
            raise
        except LibrusError as error:
            self._failure(error.kind)
            if self.outcome.status is SendStatus.NOT_DISPATCHED:
                raise
            return self.outcome

    def _dispatch(self, identity: Identity, observation: Observation) -> None:
        if self._outcome.status is not SendStatus.NOT_DISPATCHED:
            raise LibrusError(ErrorKind.INVALID_INPUT)
        self._outcome = replace(
            self._outcome,
            status=SendStatus.UNKNOWN,
            identity=identity,
            observation=observation,
        )

    def _acknowledge(self, status: SendStatus) -> SendResult:
        assert self._outcome.status is SendStatus.UNKNOWN
        assert status in (SendStatus.ACCEPTED, SendStatus.REJECTED)
        self._outcome = replace(self._outcome, status=status)
        return self._outcome

    def _failure(self, reason: ErrorKind | Literal["cancelled"]) -> None:
        if self._outcome.status not in (SendStatus.ACCEPTED, SendStatus.REJECTED):
            assert isinstance(reason, ErrorKind) or reason == "cancelled"
            self._outcome = replace(self._outcome, reason=reason)
