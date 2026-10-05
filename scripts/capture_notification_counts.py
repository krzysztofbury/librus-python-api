"""One explicitly approved count-only login, never a read-once event request."""

import argparse
import asyncio
import json
import secrets
from collections import Counter
from pathlib import Path
from typing import NoReturn

from librus_python_api import AccountCredentials, LibrusService, RequestBudget
from librus_python_api.config import (
    ConnectionSettings,
    Endpoint,
    SideEffect,
    TransportLimits,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import RequestForm, TransportResponse
from librus_python_api.scheduler import RequestScheduler
from scripts.capture_messages import write_private
from scripts.live_capture import ReadOnlyCaptureTransport, private_directory


class CountScope:
    def __init__(self) -> None:
        self.attempts = self.logins = 0
        self.failed = False
        self.counts: Counter[str] = Counter()

    def admit(self, endpoint: Endpoint, form: RequestForm) -> None:
        name = endpoint.operation_id
        if self.failed or self.attempts >= 24:
            raise LibrusError(ErrorKind.LIMIT)
        if name in {"notification_counts", "identity"}:
            if self.counts[name] or form is not None:
                raise LibrusError(ErrorKind.INVALID_INPUT)
        elif endpoint.side_effect is not SideEffect.AUTHENTICATION:
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if name == "login_submit":
            if self.logins:
                raise LibrusError(ErrorKind.LIMIT)
            self.logins += 1
        self.attempts += 1
        self.counts[name] += 1


class CountCaptureTransport(ReadOnlyCaptureTransport):
    def _get_download_session(self) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    def __init__(
        self,
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
        scope: CountScope,
        out: Path,
    ) -> None:
        super().__init__(account, scheduler, connection, limits)
        self.scope, self.out = scope, out

    async def _exchange(
        self, endpoint: Endpoint, url: str, budget: RequestBudget, form: RequestForm
    ) -> TransportResponse:
        self.scope.admit(endpoint, form)
        try:
            response = await super()._exchange(endpoint, url, budget, form)
            if endpoint.operation_id == "notification_counts":
                write_private(self.out / "notification-counts.html", response.body)
            return response
        except BaseException:
            self.scope.failed = True
            raise


async def capture(
    credentials: AccountCredentials,
    out: Path,
    connection: ConnectionSettings | None = None,
) -> dict[str, object]:
    scope = CountScope()

    def factory(
        account: str,
        scheduler: RequestScheduler,
        connection: ConnectionSettings,
        limits: TransportLimits,
    ) -> CountCaptureTransport:
        return CountCaptureTransport(account, scheduler, connection, limits, scope, out)

    report: dict[str, object] = {"status": "started"}
    try:
        async with LibrusService(
            {"capture": credentials},
            context_key=secrets.token_bytes(32),
            connection=connection,
            transport_factory=factory,
        ) as service:
            budget = RequestBudget(max_requests=24, timeout_seconds=120)
            client = service.account("capture")
            result = await client.notification_counts(budget=budget)
            before = budget.requests_dispatched
            assert (
                await client.notification_counts(budget=budget, max_age_seconds=60)
                is result
            )
            assert budget.requests_dispatched == before
            report.update(
                status="completed", categories=len(result.items), warm_cache_requests=0
            )
    except Exception as error:
        report.update(status="stopped", error_type=type(error).__name__)
    report.update(
        requests=scope.attempts,
        logins=scope.logins,
        operations=dict(scope.counts),
        read_once_requests=0,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.secrets.stat().st_mode & 0o077 or args.secrets.stat().st_size > 1048576:
        raise SystemExit("Private credentials rejected")
    record = json.loads(args.secrets.read_text())["accounts"][0]
    credentials = AccountCredentials(
        login=record["username"], password=record["password"]
    )
    report = asyncio.run(capture(credentials, private_directory(args.out)))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
