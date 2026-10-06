"""Read-only live check of an installed release before it is published.

Live use requires the owner's authorization. Run it with the interpreter of an
environment that has the exact candidate wheel installed. Each login submits
its credentials once and is limited to an allowlist of ordinary reads: the
counter menu, identity, and modern mailbox lists, counters and directories.
No message is opened, nothing is sent and no read-once route is used.
Features missing from older versions are reported as skipped.

The report holds versions, statuses and counts only, never names, subjects or
other school data. It exits non-zero if any step failed.

    python scripts/live_release_check.py --secrets FILE
"""

import argparse
import asyncio
import inspect
import json
import secrets
from collections.abc import Awaitable, Callable, Mapping
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

import librus_python_api
from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    MessageFolder,
    RequestBudget,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import RequestForm, TransportResponse
from librus_python_api.transport import AiohttpTransport

ALLOWED = frozenset(
    {
        "identity",
        "student_information",
        "modern_identity",
        "modern_unread_counts",
        "modern_messages_received",
        "modern_messages_sent",
        "modern_archive_messages_received",
        "modern_archive_messages_sent",
        "modern_senders",
        "modern_receivers",
        "modern_teacher_subjects",
    }
)
MAX_REQUESTS_PER_LOGIN = 48


class ReleaseCheckTransport(AiohttpTransport):
    """Allowlisted reads plus login and modern handoff; nothing else."""

    async def request(
        self,
        endpoint_id: str,
        budget: RequestBudget,
        *,
        form: RequestForm = None,
        reference_id: str | None = None,
        query: Mapping[str, str] | None = None,
    ) -> TransportResponse:
        if not endpoint_id.startswith("login_") and (
            endpoint_id not in ALLOWED or reference_id is not None
        ):
            raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
        if query is None:
            return await super().request(
                endpoint_id, budget, form=form, reference_id=reference_id
            )
        return await super().request(
            endpoint_id, budget, form=form, reference_id=reference_id, query=query
        )

    async def send_message(self, *args: object, **kwargs: object) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    async def send_modern_message(self, *args: object, **kwargs: object) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    async def consume_schedule_events(
        self, *args: object, **kwargs: object
    ) -> NoReturn:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)


def _accepts(method: Callable[..., Any], name: str) -> bool:
    return name in inspect.signature(method).parameters


async def check_account(client: Any, budget: RequestBudget) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    await _check_reads(client, budget, steps)
    # A fresh identity read proves the session survived every step, including
    # the counter read that once logged parent accounts out.
    await _step(steps, "session_alive", lambda: client.identity(budget=budget))
    return steps


async def _step(
    steps: list[dict[str, Any]],
    name: str,
    read: Callable[[], Awaitable[Any]],
    facts: Callable[[Any], dict[str, Any]] = lambda _: {},
) -> Any:
    try:
        result = await read()
        record = {"step": name, "status": "ok"} | facts(result)
    except LibrusError as error:
        steps.append({"step": name, "status": "error", "kind": error.kind.value})
        return None
    except AssertionError as error:
        steps.append({"step": name, "status": "failed", "check": str(error)})
        return None
    steps.append(record)
    return result


async def _check_reads(
    client: Any, budget: RequestBudget, steps: list[dict[str, Any]]
) -> None:

    step = partial(_step, steps)

    def skip(name: str) -> None:
        steps.append({"step": name, "status": "skipped"})

    await step("identity", lambda: client.identity(budget=budget))

    def counts(result: Any) -> dict[str, Any]:
        categories = [item.category.value for item in result.items]
        assert categories, "no counter categories"
        return {"categories": len(categories), "messages": "messages" in categories}

    await step(
        "notification_counts",
        lambda: client.notification_counts(budget=budget),
        counts,
    )
    modern = await step(
        "modern_identity",
        lambda: client.modern_identity(budget=budget),
        lambda r: {"group": r.account.group_id},
    )
    if modern is None:
        return

    if hasattr(client, "modern_unread_counts"):
        await step(
            "modern_unread_counts",
            lambda: client.modern_unread_counts(budget=budget),
            lambda r: {"inbox": r.current.inbox, "archive_inbox": r.archive.inbox},
        )
    else:
        skip("modern_unread_counts")

    totals: dict[MessageFolder, int] = {}
    for folder in MessageFolder:
        page = await step(
            f"modern_page {folder.value}",
            partial_page(client, budget, folder),
            lambda r: {"total": r.total_count, "items": len(r.items)},
        )
        if page is not None:
            totals[folder] = page.total_count
        if _accepts(client.modern_messages_page, "archived"):

            def archived(r: Any) -> dict[str, Any]:
                assert all(i.reference.archived for i in r.items), "unflagged item"
                return {"total": r.total_count, "items": len(r.items)}

            await step(
                f"modern_archive_page {folder.value}",
                partial_page(client, budget, folder, archived=True),
                archived,
            )
        else:
            skip(f"modern_archive_page {folder.value}")

    if not hasattr(client, "modern_correspondents"):
        for name in ("modern_correspondents", "filters", "modern_teacher_subjects"):
            skip(name)
        return
    for folder in MessageFolder:
        people = await step(
            f"modern_correspondents {folder.value}",
            partial(client.modern_correspondents, folder, budget=budget),
            lambda r: {"count": len(r.items)},
        )
        if people is None or not people.items or folder not in totals:
            skip(f"filtered_page {folder.value}")
            continue
        reference = people.items[0].reference
        await step(
            f"filtered_page {folder.value}",
            partial_page(client, budget, folder, correspondent=reference),
            partial(_narrowed, totals[folder], reference),
        )

    def unread(r: Any) -> dict[str, Any]:
        assert all(i.unread for i in r.items), "read item in unread-only list"
        return {"total": r.total_count}

    await step(
        "unread_only_page",
        partial_page(client, budget, MessageFolder.RECEIVED, unread_only=True),
        unread,
    )
    await step(
        "modern_teacher_subjects",
        lambda: client.modern_teacher_subjects(budget=budget),
        lambda r: {"count": len(r.items)},
    )


def _narrowed(whole: int, reference: Any, result: Any) -> dict[str, Any]:
    assert 1 <= result.total_count <= whole, "filter did not narrow"
    assert result.correspondent == reference, "filter not recorded"
    return {"total": result.total_count}


def partial_page(
    client: Any, budget: RequestBudget, folder: MessageFolder, **options: Any
) -> Callable[[], Awaitable[Any]]:
    return lambda: client.modern_messages_page(folder, budget=budget, **options)


async def check(
    accounts: Mapping[str, AccountCredentials],
    connection: ConnectionSettings | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "version": librus_python_api.__version__,
        "location": "installed"
        if "site-packages" in (librus_python_api.__file__ or "")
        else "source",
        "accounts": [],
    }
    async with LibrusService(
        accounts,
        context_key=secrets.token_bytes(32),
        connection=connection,
        transport_factory=ReleaseCheckTransport,
    ) as service:
        for index, alias in enumerate(accounts):
            budget = RequestBudget(
                max_requests=MAX_REQUESTS_PER_LOGIN, timeout_seconds=180
            )
            steps = await check_account(service.account(alias), budget)
            report["accounts"].append(
                {
                    "account": index,
                    "requests": budget.requests_dispatched,
                    "steps": steps,
                }
            )
    report["passed"] = all(
        step["status"] in ("ok", "skipped")
        for account in report["accounts"]
        for step in account["steps"]
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secrets", type=Path, required=True)
    args = parser.parse_args()
    if args.secrets.stat().st_mode & 0o077 or args.secrets.stat().st_size > 1048576:
        raise SystemExit("Private credentials rejected")
    records = json.loads(args.secrets.read_text())["accounts"]
    accounts = {
        f"account-{index}": AccountCredentials(
            login=record["username"], password=record["password"]
        )
        for index, record in enumerate(records)
    }
    report = asyncio.run(check(accounts))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
