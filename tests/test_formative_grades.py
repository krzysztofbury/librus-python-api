"""Formative grades on the grades page: identity safety, recognition, parsing."""

from dataclasses import asdict, fields
from datetime import date

import pytest

from librus_python_api._notification_codec import canonical_notification_id, typed
from librus_python_api.config import GRADE_MAX_RECORDS
from librus_python_api.exceptions import (
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from librus_python_api.grade_records import parse_grade_records
from librus_python_api.models import (
    DescriptiveGrade,
    GradeKind,
    NotificationCategory,
    NumericGrade,
)
from tests.grade_records_support import (
    FORMATIVE_LINK,
    formative_cells,
    formative_row,
    formative_table,
    grade_box,
    grades_html,
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


def page(extra: str | None = None, first: str | None = None) -> bytes:
    """A grades page whose pseudo-subject grid box mirrors the formative table."""
    if first is None:
        first = grade_box("T", "2041-09-15", href=FORMATIVE_LINK.format("901"))
    return grades_html(
        first,
        subject="KARTA SPOSTRZEŻEŃ",
        extra=formative_table() if extra is None else extra,
    ).encode()


def test_formative_table_is_read_and_grid_boxes_are_flagged() -> None:
    records = parse_grade_records(page())
    assert [
        (
            f.subject,
            f.text,
            f.category,
            f.semester,
            f.day,
            f.assessment_type,
            f.detail_id,
        )
        for f in records.formative
    ] == [
        (
            "KARTA SPOSTRZEŻEŃ",
            "Fixture observation one.",
            "FIXTURE AREA (synthetic)",
            1,
            date(2041, 9, 15),
            "Fixture current",
            "901",
        ),
        (
            "Fixture Language",
            "Fixture quiz - 80%",
            "FIXTURE SKILL (synthetic)",
            2,
            date(2042, 2, 3),
            "Fixture current",
            "902",
        ),
    ]
    # The grid record is unchanged apart from the computed recognition.
    [grid] = records.numeric
    assert (grid.subject, grid.raw, grid.formative_id) == (
        "KARTA SPOSTRZEŻEŃ",
        "T",
        "901",
    )
    assert "Fixture" not in repr(records) + repr(records.formative[0])


def test_a_page_without_the_section_has_no_formative_grades() -> None:
    # WEEK or LAST_LOGIN views may not render the section at all.
    records = parse_grade_records(grades_html().encode())
    assert records.formative == ()
    assert records.numeric[0].formative_id is None


def test_a_grouped_subject_spans_its_rows() -> None:
    # Synthetic coverage of an unobserved grouping (for example category sort).
    rows = (
        formative_row("Fixture Science", rowspan="3", detail="911")
        + '<tr class="line1">'
        + formative_cells(detail="912")
        + "</tr>"
        + '<tr class="line0">'
        + formative_cells(detail="913")
        + "</tr>"
        + formative_row("Fixture Art", line=1, detail="914")
    )
    records = parse_grade_records(page(formative_table(rows)))
    assert [(f.subject, f.detail_id) for f in records.formative] == [
        ("Fixture Science", "911"),
        ("Fixture Science", "912"),
        ("Fixture Science", "913"),
        ("Fixture Art", "914"),
    ]


def test_the_hidden_template_row_is_skipped() -> None:
    rows = formative_row(detail="000000", attributes=' style="display: none"', text="")
    rows += formative_row("Fixture Language", line=1, detail="902")
    records = parse_grade_records(page(formative_table(rows)))
    assert [f.detail_id for f in records.formative] == ["902"]


def test_long_assessment_text_within_the_bound_is_kept() -> None:
    text = "x" * 4096
    records = parse_grade_records(page(formative_table(formative_row(text=text))))
    assert records.formative[0].text == text


def test_formative_rows_count_toward_the_record_limit() -> None:
    rows = "".join(
        formative_row(f"Fixture {n}", detail=str(1000 + n))
        for n in range(GRADE_MAX_RECORDS)
    )
    with pytest.raises(LimitError):
        parse_grade_records(page(formative_table(rows)))


def bad(rows: str) -> bytes:
    return page(formative_table(rows))


MALFORMED = [
    ("two tables", page(formative_table() + formative_table()), ParseError),
    (
        "group ends early",
        bad(formative_row(rowspan="2") + formative_row("Fixture Art", detail="902")),
        ParseError,
    ),
    ("unterminated group", bad(formative_row(rowspan="2")), ParseError),
    ("bad rowspan", bad(formative_row(rowspan="x")), UnsupportedCapabilityError),
    (
        "extra cell",
        bad(formative_row().replace("</tr>", "<td></td></tr>")),
        UnsupportedCapabilityError,
    ),
    (
        "unexpected markup in assessment",
        bad(
            formative_row(
                assessment=f'<a href="{FORMATIVE_LINK.format(1)}"><b>x</b></a>'
            )
        ),
        UnsupportedCapabilityError,
    ),
    (
        "foreign link",
        bad(
            formative_row(
                assessment='<a href="https://example.invalid/x/1">Fixture</a>'
            )
        ),
        UnsupportedCapabilityError,
    ),
    ("empty text", bad(formative_row(text="")), ParseError),
    ("bad period", bad(formative_row(period="3")), ParseError),
    ("bad date", bad(formative_row(day="2041-13-01")), ParseError),
    (
        "duplicate id",
        bad(formative_row() + formative_row("Fixture Art", detail="901")),
        ParseError,
    ),
    (
        "nonempty footer",
        page(formative_table(footer='<tr><td colspan="6">Fixture</td></tr>')),
        ParseError,
    ),
    (
        "stray formative link elsewhere",
        grades_html(
            extra='<p><a href="/przegladaj_oceny/szczegoly/ksztaltujace/7">x</a></p>'
        ).encode(),
        UnsupportedCapabilityError,
    ),
]


@pytest.mark.parametrize(
    "body,error", [c[1:] for c in MALFORMED], ids=[c[0] for c in MALFORMED]
)
def test_malformed_formative_markup_fails_with_a_typed_error(
    body: bytes, error: type[Exception]
) -> None:
    with pytest.raises(error):
        parse_grade_records(body)
