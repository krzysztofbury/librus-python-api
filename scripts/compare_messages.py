"""Replay installed apix parsers against identical private captures, offline.

No upstream code or data is vendored. The external reference directory must
contain a separately acquired librus-apix 1.5.3 installation. Only field mismatch
counts escape this process; never print private values or raw diffs. Agreement
is a coverage signal, not a semantic oracle. Run crosscheck.py as well.
"""

import argparse
import importlib
import importlib.metadata
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from librus_python_api.messages import parse_messages
from librus_python_api.models import MessageFolder


def normalized(value: str) -> str:
    return " ".join(value.split())


def compare_directory(
    directory: Path, reference: Any, soup_type: Any
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for entry in json.loads((directory / "index.json").read_text())["captured"]:
        if entry["endpoint"] not in {"messages_received", "messages_sent"}:
            continue
        body = (directory / entry["file"]).read_bytes()
        folder = MessageFolder(entry["endpoint"].removeprefix("messages_"))
        items, _, _ = parse_messages(
            body, folder, int(entry["form"]["numer_strony105"]), "offline"
        )
        parser = (
            reference.parse
            if folder is MessageFolder.RECEIVED
            else reference.parse_sent
        )
        try:
            external = parser(soup_type(body.decode(), "lxml"))
        except Exception as error:
            results.append(
                {"folder": folder.value, "external_error": type(error).__name__}
            )
            continue
        mismatches: Counter[str] = Counter()
        if len(items) != len(external):
            mismatches["row_count"] += 1
        for item, other in zip(items, external, strict=False):
            fields = {
                "correspondent": (
                    normalized(item.correspondent),
                    normalized(other.author),
                ),
                "subject": (normalized(item.subject), normalized(other.title)),
                "timestamp": (normalized(item.timestamp.raw), normalized(other.date)),
                "reference": (item.reference.identifier, other.href),
                "attachment": (item.has_attachment, other.has_attachment),
            }
            if folder is MessageFolder.RECEIVED:
                fields["unread"] = (item.unread, other.unread)
            for name, (native, apix) in fields.items():
                if native != apix:
                    mismatches[name] += 1
        results.append(
            {"folder": folder.value, "rows": len(items), "mismatches": dict(mismatches)}
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    distributions = list(
        importlib.metadata.distributions(path=[str(args.reference.resolve())])
    )
    if not any(
        d.metadata["Name"].replace("_", "-").casefold() == "librus-apix"
        and d.version == "1.5.3"
        for d in distributions
    ):
        raise SystemExit("Expected an external librus-apix 1.5.3 installation")
    sys.path.insert(0, str(args.reference.resolve()))
    reference = importlib.import_module("librus_apix.messages")
    soup_type = importlib.import_module("bs4").BeautifulSoup
    print(json.dumps(compare_directory(args.directory, reference, soup_type), indent=2))


if __name__ == "__main__":
    main()
