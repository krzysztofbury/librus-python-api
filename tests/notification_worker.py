"""Original process-level native notification claim/checkpoint/delivery faults."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from librus_python_api import (
    AccountCredentials,
    ConnectionSettings,
    LibrusService,
    NotificationCategory,
    RequestBudget,
    SchedulerLimits,
)
from librus_python_api.exceptions import LibrusError
from librus_python_api.persistence import NotificationStore, NotificationWorkflow
from tests.http_support import FIXTURE_SECRET

PHASE = "normal"


class InterruptedStore(NotificationStore):
    def _checkpoint(self, *args: Any) -> None:
        super()._checkpoint(*args)
        if PHASE == "checkpoint":
            os._exit(73)

    def _stage(self, *args: Any) -> None:
        super()._stage(*args)
        if PHASE == "delivery":
            os._exit(74)

    def _ack(self, *args: Any) -> None:
        super()._ack(*args)
        if PHASE == "acknowledgement":
            os._exit(75)


async def main() -> None:
    global PHASE
    directory, origin, PHASE = sys.argv[1:]
    async with LibrusService(
        {"student": AccountCredentials(login="student", password=FIXTURE_SECRET)},
        connection=ConnectionSettings(synergia_origin=origin, api_origin=origin),
        scheduler_limits=SchedulerLimits(requests_per_second=1000, burst=16),
    ) as service:
        async with InterruptedStore(Path(directory)) as store:
            workflow = NotificationWorkflow(service.account("student"), store)
            print("ready", flush=True)
            await asyncio.to_thread(sys.stdin.readline)
            try:
                batch = await workflow.poll(
                    categories=(NotificationCategory.AGENDA,),
                    allow_consume_events=True,
                    budget=RequestBudget(max_requests=6),
                )
                print(
                    json.dumps({"receipt": batch.receipt, "items": len(batch.items)}),
                    flush=True,
                )
                if PHASE == "acknowledgement":
                    await asyncio.to_thread(sys.stdin.readline)
                    await workflow.acknowledge(batch.receipt)
            except LibrusError as error:
                print(json.dumps({"error": error.kind.value}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
