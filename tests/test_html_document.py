"""Every libxml2 that lxml wheels bundle reads a Synergia page alike (#121).

lxml's Windows wheels bundle libxml2 2.11.9, Linux and macOS ones 2.14 or
later. 2.14 parses HTML as HTML5 does; 2.11 reports each repair it makes and
keeps "&nbsp" without ";" as text. These cases hold on both; the Windows CI
jobs run them on 2.11.
"""

import pytest
from lxml import etree

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


OLD_LIBXML2 = etree.LIBXML_VERSION < (2, 14)


def test_escaped_text_is_never_decoded_as_a_bare_reference() -> None:
    # Escaped references alone parse alike everywhere.
    document = parse_html_document(b"<p>?a=1&amp;para=2 &amp;not</p>")
    assert markup.text(next(document.iter("p"))) == "?a=1&para=2 &not"
    # Next to a bare one, 2.11 cannot tell them apart once parsed, so it fails.
    body = b"<p>?a=1&amp;para=2 Fixture&nbspText</p>"
    if OLD_LIBXML2:
        with pytest.raises(LibrusError) as caught:
            parse_html_document(body)
        assert caught.value.kind is ErrorKind.PARSE
    else:
        document = parse_html_document(body)
        assert next(document.iter("p")).text == "?a=1&para=2 Fixture\xa0Text"


def test_a_misplaced_body_tag_fails_where_libxml2_reports_it() -> None:
    # libxml2 2.14 reports it, as before #121; only 2.11 accepts its repair.
    body = b"<p>Fixture</p><body>Fixture second</body>"
    if OLD_LIBXML2:
        parse_html_document(body)
    else:
        with pytest.raises(LibrusError) as caught:
            parse_html_document(body)
        assert caught.value.kind is ErrorKind.PARSE
