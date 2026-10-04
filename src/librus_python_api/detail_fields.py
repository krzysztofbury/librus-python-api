"""Normalize bounded detail records using only established per-family labels."""

from typing import Literal

from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import DetailField, DetailFieldKey

# School labels are recorded in contracts/school-reads.md. Attendance labels
# are the narrowly established date/topic fields, not inferred tooltip fields.
_KEYS: dict[str, dict[str, DetailFieldKey]] = {
    "agenda": {
        "data": "date",
        "nr lekcji": "lesson_number",
        "nauczyciel": "teacher",
        "rodzaj": "category",
        "przedmiot": "subject",
        "sala": "room",
        "opis": "description",
        "data dodania": "published_at",
    },
    "homework": {
        "zajęcia edukacyjne": "subject",
        "temat": "topic",
        "kategoria": "category",
        "data udostępnienia": "published_at",
        "termin wykonania": "due_at",
        "treść": "content",
    },
    "attendance": {"data": "date", "temat zajęć": "topic"},
}


def normalize_detail_fields(
    fields: tuple[tuple[str, str], ...],
    kind: Literal["agenda", "homework", "attendance"],
) -> tuple[DetailField, ...]:
    """Run after bounded HTML parsing, before publishing or caching a result."""
    labels: set[str] = set()
    keys: set[DetailFieldKey] = set()
    result = []
    for label, value in fields:
        canonical = " ".join(label.split()).rstrip(":").strip().casefold()
        key = _KEYS[kind].get(canonical)
        if not canonical or canonical in labels or (key is not None and key in keys):
            raise LibrusError(ErrorKind.PARSE)
        labels.add(canonical)
        if key is not None:
            keys.add(key)
        result.append(DetailField(key, label, value))
    return tuple(result)
