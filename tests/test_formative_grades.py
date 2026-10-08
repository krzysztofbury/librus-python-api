"""Formative grades on the grades page: identity safety, recognition, parsing."""

from dataclasses import asdict, fields
from datetime import date

import pytest

from librus_python_api._notification_codec import canonical_notification_id, typed
from librus_python_api.models import (
    DescriptiveGrade,
    GradeKind,
    NotificationCategory,
    NumericGrade,
)

FORMATIVE_PATH = "/przegladaj_oceny/szczegoly/ksztaltujace/987"


def pinned_grade(href: str | None = FORMATIVE_PATH) -> NumericGrade:
    return NumericGrade(
        "Fixture Language",
        "4+",
        date(2041, 9, 30),
        1,
        True,
        2,
        "Fixture quiz",
        "Fixture Teacher",
        "Synthetic note",
        href,
        (("Data", "2041-09-30"),),
        GradeKind.CURRENT,
    )


def test_stored_grade_identities_do_not_change() -> None:
    # Computed on 1.3.0. Grades have no native ID, so the canonical ID hashes
    # every dataclass field; a new field would make every stored grade "new".
    assert canonical_notification_id(NotificationCategory.GRADES, pinned_grade()) == (
        "2384843cf4cd40edb863b9d28fc18b22d12a865587676a7ad77ce3ebba2bd6bf"
    )


def test_a_grade_saved_by_1_3_0_still_decodes() -> None:
    saved = {
        "subject": "Fixture Language",
        "raw": "4+",
        "day": "2041-09-30",
        "semester": 1,
        "counts_toward_average": True,
        "weight": 2,
        "category": "Fixture quiz",
        "teacher": "Fixture Teacher",
        "comment": "Synthetic note",
        "href": FORMATIVE_PATH,
        "metadata": [["Data", "2041-09-30"]],
        "kind": "current",
    }
    assert {f.name for f in fields(NumericGrade)} == set(saved)
    assert typed(NumericGrade, saved) == pinned_grade()
    assert "formative_id" not in asdict(pinned_grade())


@pytest.mark.parametrize(
    "href,expected",
    [
        (FORMATIVE_PATH, "987"),
        ("https://synergia.librus.pl" + FORMATIVE_PATH, "987"),
        ("https://example.invalid" + FORMATIVE_PATH, None),
        ("/przegladaj_oceny/szczegoly/ksztaltujace/98x", None),
        ("/przegladaj_oceny/szczegoly/987", None),
        (FORMATIVE_PATH + "?x=1", None),
        ("javascript:void(0)", None),
        (None, None),
    ],
)
def test_formative_id_recognises_only_the_formative_detail_link(
    href: str | None, expected: str | None
) -> None:
    assert pinned_grade(href).formative_id == expected
    descriptive = DescriptiveGrade(
        "Fixture", "A", date(2041, 9, 30), 1, None, None, (), href=href
    )
    assert descriptive.formative_id == expected
