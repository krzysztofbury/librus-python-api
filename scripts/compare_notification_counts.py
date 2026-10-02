"""Inert apix count comparison over identical bytes; no live reference client."""

import argparse
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from librus_python_api.config import ENDPOINTS, NOTIFICATION_DESTINATIONS
from librus_python_api.notifications import parse_notification_counts
from scripts.compare_messages import load_reference, normalized


def compare(body: bytes, reference: Any) -> dict[str, object]:
    route = ENDPOINTS["notification_counts"].path

    class InertClient:
        INDEX_URL = route

        def get(self, url: str) -> SimpleNamespace:
            assert url == route
            return SimpleNamespace(text=body.decode())

    external = reference.get_new_token_notification_amounts(InertClient())
    native = parse_notification_counts(body)
    other = [
        (NOTIFICATION_DESTINATIONS[r.destination], normalized(r.name), r.amount)
        for r in external
    ]
    actual = [(r.category.value, normalized(r.label), r.count) for r in native]
    return {
        "categories": len(actual),
        "mismatches": int(actual != other),
        "same_bytes": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    load_reference(args.reference)
    try:
        result = compare(
            args.file.read_bytes(), importlib.import_module("librus_apix.notifications")
        )
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["mismatches"] == 0 else 1)
