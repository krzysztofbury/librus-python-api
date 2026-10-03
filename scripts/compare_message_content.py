"""Inert apix content replay; print only field mismatch counts, never values."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from librus_python_api.config import ENDPOINTS
from librus_python_api.message_content import parse_message_content
from librus_python_api.models import MessageFolder, MessageReference
from scripts.compare_messages import load_reference, normalized


class CapturedContentClient:
    MESSAGE_URL = ENDPOINTS["message_content_received"].path.removesuffix("/{id}")

    def __init__(
        self,
        body: bytes,
        identifier: str,
        folder: MessageFolder = MessageFolder.RECEIVED,
    ) -> None:
        self.body, self.identifier = body, identifier
        self.MESSAGE_URL = ENDPOINTS[
            "message_content_" + folder.value
        ].path.removesuffix("/{id}")

    def get(self, url: str) -> SimpleNamespace:
        assert url == self.MESSAGE_URL + "/" + self.identifier
        return SimpleNamespace(text=self.body.decode())


def compare(directory: Path, reference: Any) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for entry in json.loads((directory / "index.json").read_text())["captured"]:
        if entry["endpoint"] not in {
            "message_content_received",
            "message_content_sent",
        }:
            continue
        body = (directory / entry["file"]).read_bytes()
        identifier = entry["reference"]
        folder = MessageFolder(entry["endpoint"].removeprefix("message_content_"))
        native = parse_message_content(
            body, MessageReference(folder, identifier, "offline")
        )
        try:
            other = reference.message_content(
                CapturedContentClient(body, identifier, folder), identifier
            )
        except Exception as error:
            results.append(
                {
                    "operation": entry["endpoint"],
                    "native_recipient_receipts": len(native.recipient_receipts),
                    "apix_error_type": type(error).__name__,
                    "same_bytes": True,
                }
            )
            continue
        fields = {
            "correspondent": (native.correspondent, other.author),
            "subject": (native.subject, other.title),
            "timestamp": (native.timestamp.raw, other.date),
            "text": (native.text, other.content),
        }
        results.append(
            {
                "fields": len(fields),
                "mismatches": {
                    k: int(normalized(a or "") != normalized(b))
                    for k, (a, b) in fields.items()
                },
                "attachments": len(native.attachments),
                "read_timestamp_present": native.read_timestamp is not None,
                "apix_attachment_and_receipt_support": False,
            }
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    try:
        reference, _ = load_reference(args.reference)
        result = compare(args.directory, reference)
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))
