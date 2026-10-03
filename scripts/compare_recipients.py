"""Offline apix recipient replay; outputs classifications, never names or IDs."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from librus_python_api.config import ENDPOINTS
from librus_python_api.exceptions import UnsupportedCapabilityError
from librus_python_api.models import RecipientGroupReference
from librus_python_api.recipients import (
    parse_recipient_group_choices,
    parse_recipient_groups,
    parse_recipients,
)
from scripts.compare_messages import load_reference, normalized


class CapturedRecipientClient:
    RECIPIENT_GROUPS_URL = ENDPOINTS["recipient_groups"].path
    RECIPIENTS_URL = ENDPOINTS["recipients"].path

    def __init__(self, body: bytes, operation: str, group_type: str | None) -> None:
        self.body, self.operation, self.group_type = body, operation, group_type

    def get(self, url: str) -> SimpleNamespace:
        assert self.operation == "recipient_groups" and url == self.RECIPIENT_GROUPS_URL
        return SimpleNamespace(text=self.body.decode())

    def post(self, url: str, *, data: dict[str, Any]) -> SimpleNamespace:
        assert self.operation == "recipients" and url == self.RECIPIENTS_URL
        assert data["typAdresata"] == self.group_type
        assert set(data) == {
            "typAdresata",
            "poprzednia",
            "tabZaznaczonych",
            "czyWirtualneKlasy",
            "idGrupy",
        }
        return SimpleNamespace(text=self.body.decode())


def compare(directory: Path, reference: Any) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for entry in json.loads((directory / "index.json").read_text())["captured"]:
        operation = entry["endpoint"]
        if operation not in {"recipient_groups", "recipients"}:
            continue
        body = (directory / entry["file"]).read_bytes()
        token = (entry["form"] or {}).get("typAdresata")
        client = CapturedRecipientClient(body, operation, token)
        try:
            if operation == "recipient_groups":
                native = [
                    g.reference.identifier
                    for g in parse_recipient_groups(body, "offline")
                ]
                external = reference.recipient_groups(client)
                result: dict[str, object] = {
                    "operation": operation,
                    "groups": len(native),
                    "group_mismatches": int(native != external),
                }
            else:
                assert isinstance(token, str)
                external = reference.get_recipients(client, token)
                group = RecipientGroupReference(
                    token, "offline", entry["form"]["idGrupy"]
                )
                if token == "grupa" and group.selection_id == "0":
                    choices = parse_recipient_group_choices(body, group)
                    results.append(
                        {
                            "operation": operation,
                            "kind": "group_choices",
                            "choices": len(choices),
                            "apix_recipient_rows": len(external),
                            "same_bytes": True,
                            "equivalent_api": False,
                        }
                    )
                    continue
                try:
                    items = parse_recipients(body, group)
                except UnsupportedCapabilityError:
                    results.append(
                        {
                            "operation": operation,
                            "kind": "unavailable",
                            "apix_recipient_rows": len(external),
                            "same_bytes": True,
                            "equivalent_api": False,
                        }
                    )
                    continue
                native_pairs = {
                    (i.reference.identifier, normalized(i.label or "")) for i in items
                }
                external_pairs = {
                    (identifier, normalized(label))
                    for label, identifier in external.items()
                }
                result = {
                    "operation": operation,
                    "group_type": token,
                    "rows": len(items),
                    "missing_pairs": len(native_pairs - external_pairs),
                    "extra_pairs": len(external_pairs - native_pairs),
                }
        except Exception as error:
            result = {"operation": operation, "error_type": type(error).__name__}
        results.append(result)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    reference, _ = load_reference(args.reference)
    print(json.dumps(compare(args.directory, reference), indent=2))


if __name__ == "__main__":
    main()
