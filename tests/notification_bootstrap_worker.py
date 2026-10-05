"""Fresh-process public recovery of imported, provenance-free historical work."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from librus_python_api import NotificationCategory
from librus_python_api.persistence import (
    NotificationProvenance,
    NotificationStore,
    NotificationWorkflow,
)
from tests.test_notification_persistence import offline_service


async def main() -> None:
    async with offline_service("http://127.0.0.1:9") as service:
        async with NotificationStore(Path(sys.argv[1])) as store:
            workflow = NotificationWorkflow(service.account("student"), store)
            batch = await workflow.poll(categories=(NotificationCategory.AGENDA,))
            assert not batch.first_run and len(batch.items) == 1
            item = batch.items[0]
            assert item.provenance is NotificationProvenance.IMPORTED_HISTORY
            assert item.identity is None and item.observation is None
            await workflow.acknowledge(batch.receipt)
            print(
                json.dumps(
                    {
                        "receipt": batch.receipt,
                        "identifier": item.identifier,
                        "event": asdict(item.value),
                        "requests": service.snapshot().requests_dispatched,
                    }
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
