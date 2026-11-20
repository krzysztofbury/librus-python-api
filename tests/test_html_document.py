"""Every libxml2 that lxml wheels bundle reads a Synergia page alike (#121).

lxml's Windows wheels bundle libxml2 2.11.9, Linux and macOS ones 2.14 or
later. 2.14 parses HTML as HTML5 does; 2.11 reports each repair it makes and
keeps "&nbsp" without ";" as text. These cases hold on both; the Windows CI
jobs run them on 2.11.
"""

import pytest

from librus_python_api import markup
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.parsers import parse_html_document

# The repairs live pages need (#121), all in one fixture page: a repeated
# attribute, a stray quote in a start tag, a tag HTML 4 does not list, a stray
# end tag and named references without ";", in text and in a query string.
REPAIRED = (
    '<html><body><table class="decorated" class="other">'
    '<tr " class="line0"><td nowrap nowrap>Fixture&nbspTeacher&nbsp&nbsp;s.&nbsp12'
    "</td><td><nobr>Fixture&nbsp;cell</nobr></span></td>"
    '<td><a href="/fixture?a=1&copy=2&lang=pl">Fixture link</a></td></tr></table>'
    "<script>var fixture = '&nbsp';</script>"
    "<p>Fixture &amp;nbsp; R&amp;D</p></body></html>"
)


def test_a_page_with_browser_repairs_reads_the_same_on_every_libxml2() -> None:
    document = parse_html_document(REPAIRED.encode())
    table = next(document.iter("table"))
    assert table.get("class") == "decorated"
    row = next(document.iter("tr"))
    assert row.get("class") == "line0"
    cells = markup.cells(row)
    assert cells[0].text == "Fixture\xa0Teacher\xa0\xa0s.\xa012"
    assert markup.text(cells[0]) == "Fixture Teacher s. 12"
    assert markup.text(cells[1]) == "Fixture cell"
    assert next(document.iter("a")).get("href") == "/fixture?a=1&copy=2&lang=pl"
    # Script text and escaped ampersands are not references.
    assert next(document.iter("script")).text == "var fixture = '&nbsp';"
    assert markup.text(next(document.iter("p"))) == "Fixture &nbsp; R&D"


def test_a_control_character_in_a_message_body_is_no_failure() -> None:
    # 2.11 drops each one with an error; 2.14 keeps them.
    document = parse_html_document(b"<p>Fixture\x0b text\x1f</p>")
    assert markup.text(next(document.iter("p"))).removesuffix("\x1f") == "Fixture text"


def test_a_duplicate_id_that_is_no_repair_still_fails() -> None:
    with pytest.raises(LibrusError) as caught:
        parse_html_document(b'<p id="fixture"></p><p id="fixture"></p>')
    assert caught.value.kind is ErrorKind.PARSE
