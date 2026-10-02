"""Announcement data integrity and login-owned service/wire behavior."""

import re
from datetime import date

import pytest

from librus_python_api.announcements import parse_announcements
from librus_python_api.exceptions import (
    LimitError,
    ParseError,
    UnsupportedCapabilityError,
)
from tests.announcements_support import (
    announcement_table,
    empty_page,
    page,
)


def test_full_content_line_boundaries_inline_text_and_typed_date() -> None:
    content = (
        "<p>Fixture <span>Bio</span><em>logy</em>&nbsp;note.</p>"
        "<ul><li>First</li><li>Second<br>line</li></ul><p>" + "x" * 2048 + "</p>"
    )
    items = parse_announcements(
        page(announcement_table(content=content)).encode(), "fixture"
    )
    assert len(items) == 1
    item = items[0]
    assert item.title == "Fixture notice"
    assert item.author == "Fixture Editor"
    assert item.published_on == date(2026, 10, 1)
    assert item.date_text == "2026-10-01"
    assert item.content == "Fixture Biology note.\nFirst\nSecond\nline\n" + "x" * 2048
    assert re.fullmatch(r"content-sha256:[0-9a-f]{64}", item.reference)
    assert "Fixture" not in repr(item) and "sha256" not in repr(item)


def test_content_references_survive_reordering_but_change_with_scope_or_fields() -> (
    None
):
    first, second = announcement_table(), announcement_table(title="Fixture second")
    original = parse_announcements(page(first, second).encode(), "fixture")
    reordered = parse_announcements(page(second, first).encode(), "fixture")
    assert original == tuple(reversed(reordered))
    repeated = parse_announcements(page(first, first).encode(), "fixture")
    assert len(repeated) == 2 and repeated[0].reference == repeated[1].reference
    for kwargs in (
        {"title": "Fixture edited"},
        {"author": "Fixture other"},
        {"day": "2026-10-02"},
        {"content": "Fixture changed text"},
    ):
        assert (
            parse_announcements(page(announcement_table(**kwargs)).encode(), "fixture")[
                0
            ].reference
            != original[0].reference
        )
    assert (
        parse_announcements(page(first).encode(), "other-login")[0].reference
        != original[0].reference
    )


def test_semantic_field_order_and_source_whitespace_do_not_change_references() -> None:
    table = announcement_table()
    start = table.index('<tr class="line0">')
    end = table.index('<tr><td colspan="2">', start)
    rows = re.findall(r"<tr.*?</tr>", table[start:end])
    reordered = table[:start] + "".join(reversed(rows)) + table[end:]
    normalized = table.replace("Fixture Editor", "  Fixture\n Editor  ")
    expected = parse_announcements(page(table).encode(), "fixture")
    assert parse_announcements(page(reordered).encode(), "fixture") == expected
    assert parse_announcements(page(normalized).encode(), "fixture") == expected
    aliases = table.replace("Dodał:", "Autor:").replace("Data publikacji:", "Data:")
    assert parse_announcements(page(aliases).encode(), "fixture") == expected


def test_empty_collection_and_empty_content_are_distinct_from_missing_markup() -> None:
    assert parse_announcements(empty_page().encode(), "fixture") == ()
    assert (
        parse_announcements(page(announcement_table(content="")).encode(), "fixture")[
            0
        ].content
        == ""
    )
    for body in (
        page(),
        page("<p>Brak ogłoszeń.</p>"),
        empty_page().replace("Brak ogłoszeń.", "Fixture unrelated warning"),
        empty_page().replace("border-red", "unknown"),
    ):
        with pytest.raises(ParseError):
            parse_announcements(body.encode(), "fixture")
    contradictory = empty_page().replace("</body>", announcement_table() + "</body>")
    with pytest.raises(ParseError):
        parse_announcements(contradictory.encode(), "fixture")


@pytest.mark.parametrize(
    "before,after,expected",
    [
        ("Fixture Editor", "", ParseError),
        ("Fixture notice", "", ParseError),
        ("2026-10-01", "2026-02-30", ParseError),
        ("2026-10-01", "01.10.2026", UnsupportedCapabilityError),
        ("Dodał:", "Fixture Unknown:", UnsupportedCapabilityError),
        ("Data publikacji:", "Dodał:", ParseError),
        ("<th>Treść:</th>", '<th colspan="2">Treść:</th>', ParseError),
        ("<td>Fixture Editor</td>", '<td rowspan="2">Fixture Editor</td>', ParseError),
        ("printable big", "big", UnsupportedCapabilityError),
        (
            '<tr><td colspan="2"></td></tr>',
            '<tr><td colspan="2">Fixture unparsed</td></tr>',
            UnsupportedCapabilityError,
        ),
        ("Fixture notice", "x" * 1025, LimitError),
    ],
)
def test_malformed_or_unsupported_items_fail_whole_collection(
    before: str,
    after: str,
    expected: type[Exception],
) -> None:
    body = page(announcement_table(), announcement_table().replace(before, after))
    with pytest.raises(expected):
        parse_announcements(body.encode(), "fixture")


@pytest.mark.parametrize(
    "content",
    [
        "<table><tr><td>Fixture nested</td></tr></table>",
        "<script>Fixture unsupported()</script>",
        '<iframe src="https://example.invalid/"></iframe>',
        "<form>Fixture form</form>",
    ],
)
def test_active_or_nested_content_is_not_silently_dropped(content: str) -> None:
    with pytest.raises(UnsupportedCapabilityError):
        parse_announcements(
            page(announcement_table(content=content)).encode(), "fixture"
        )


@pytest.mark.parametrize(
    "bound,value,body",
    [
        (
            "ANNOUNCEMENT_MAX_ITEMS",
            1,
            page(announcement_table(), announcement_table(title="Second")),
        ),
        ("ANNOUNCEMENT_MAX_CONTENT_LENGTH", 10, page(announcement_table())),
        (
            "ANNOUNCEMENT_MAX_TOTAL_TEXT_LENGTH",
            130,
            page(announcement_table(), announcement_table(title="Second")),
        ),
    ],
)
def test_limits_reject_instead_of_truncating(
    bound: str,
    value: int,
    body: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("librus_python_api.announcements." + bound, value)
    with pytest.raises(LimitError):
        parse_announcements(body.encode(), "fixture")
