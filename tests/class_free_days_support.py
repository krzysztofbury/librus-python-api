"""Original synthetic values with the independently observed gateway shape."""

import json


def free_day(identifier: int = 101) -> dict[str, object]:
    return {
        "Id": identifier,
        "Class": {"Id": 201, "Url": "https://example.invalid/class"},
        "Type": {"Id": 301, "Url": "https://example.invalid/type"},
        "DateFrom": "2026-12-21",
        "DateTo": "2026-12-22",
    }


def free_days_body() -> bytes:
    partial = free_day(102)
    partial.update(LessonNoFrom=2, LessonNoTo=4)
    return json.dumps({"ClassFreeDays": [free_day(), partial]}).encode()
