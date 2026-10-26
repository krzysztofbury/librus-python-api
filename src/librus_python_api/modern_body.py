"""Bounded inert Base64 reader layouts, without XML entity or network access."""

import base64
import binascii
import re

from lxml import etree

from librus_python_api.config import MESSAGE_MAX_CONTENT_LENGTH
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.markup import text
from librus_python_api.parsers import parse_html_document

_XML_START = re.compile(r"<\?xml\b|<Message(?=[\s/>])")
_XML_DECLARATION = re.compile(r"<\?xml\b")


def render_body(encoded: str) -> str:
    if type(encoded) is not str:
        raise LibrusError(ErrorKind.PARSE)
    if len(encoded) > 4 * MESSAGE_MAX_CONTENT_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8", "strict")
    except (ValueError, UnicodeError, binascii.Error):
        raise LibrusError(ErrorKind.PARSE) from None
    if len(decoded.encode()) > MESSAGE_MAX_CONTENT_LENGTH:
        raise LibrusError(ErrorKind.LIMIT)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", decoded, re.IGNORECASE):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    decoded = decoded.removeprefix("\ufeff")
    # XML comments/PIs and a UTF-8 BOM must not route a Message wrapper through
    # the permissive HTML renderer, losing CDATA or bypassing Content checks.
    if _xml_prefixed(decoded):
        decoded = _xml_content(decoded)
    if not decoded:
        return ""
    # The official reader preserves physical line endings before HTML rendering.
    decoded = re.sub(r"\r\n|\r|\n", "<br>", decoded)
    return text(
        parse_html_document(decoded.encode()),
        MESSAGE_MAX_CONTENT_LENGTH,
        multiline=True,
    )


def _xml_prefixed(decoded: str) -> bool:
    """Whether whitespace, comments and non-declaration PIs precede an XML start.

    A comment or PI may end at any later terminator, as the lazy pattern this
    replaces allowed, but one left-to-right pass decides it: once an item has
    opened, every later terminator closes it. A regex backtracks exponentially
    over a run of items with no XML start after it.
    """
    starts = bytearray(len(decoded) + 1)
    starts[0] = 1
    comment_from = pi_from = len(decoded) + 1
    for index, char in enumerate(decoded):
        if starts[index]:
            if char.isspace():
                starts[index + 1] = 1
            elif _XML_START.match(decoded, index):
                return True
            elif decoded.startswith("<!--", index):
                comment_from = min(comment_from, index + 4)
            elif decoded.startswith("<?", index) and not _XML_DECLARATION.match(
                decoded, index
            ):
                pi_from = min(pi_from, index + 2)
        if index >= comment_from and decoded.startswith("-->", index):
            starts[index + 3] = 1
        if index >= pi_from and decoded.startswith("?>", index):
            starts[index + 2] = 1
    return False


def _xml_content(decoded: str) -> str:
    parser = etree.XMLParser(
        no_network=True,
        resolve_entities=False,
        load_dtd=False,
        recover=False,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(decoded.encode(), parser=parser)
    except (ValueError, etree.LxmlError):
        raise LibrusError(ErrorKind.PARSE) from None
    if root.tag != "Message" or root.getroottree().docinfo.encoding.upper() not in {
        "UTF-8",
        "UTF8",
    }:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    nodes = list(root.iter())
    if len(nodes) > 8192 or any(
        len(tuple(node.iterancestors())) > 32 for node in nodes
    ):
        raise LibrusError(ErrorKind.LIMIT)
    contents = list(root.iter("Content"))
    if len(contents) != 1 or len(contents[0]) or contents[0].attrib:
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    return contents[0].text or ""
