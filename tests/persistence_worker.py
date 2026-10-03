"""Independent process for original public durable-send fault/claim proofs."""

import asyncio
import json
import sys
from pathlib import Path

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    RecipientReference,
    RequestBudget,
    SchedulerLimits,
)
from librus_python_api.exceptions import LibrusError
from librus_python_api.persistence import PersistenceStore
from tests.http_support import FIXTURE_SECRET


async def main() -> None:
    directory, origin, token = sys.argv[1:]
    async with LibrusService(
        {"student": AccountCredentials(login="student", password=FIXTURE_SECRET)},
        connection=ConnectionSettings(synergia_origin=origin, api_origin=origin),
        scheduler_limits=SchedulerLimits(requests_per_second=1000, burst=16),
    ) as service:
        async with PersistenceStore(Path(directory)) as store:
            print("ready", flush=True)
            await asyncio.to_thread(sys.stdin.readline)
            try:
                result = await store.execute_send(
                    token,
                    service.account("student").prepare_send(
                        recipients=(
                            RecipientReference("101", "student", "nauczyciel"),
                        ),
                        subject="Original fixture subject",
                        body="Original fixture body",
                    ),
                    budget=RequestBudget(max_requests=6),
                )
                print(json.dumps({"status": result.status.value}), flush=True)
            except LibrusError as error:
                print(json.dumps({"error": error.kind.value}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
