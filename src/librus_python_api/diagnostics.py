"""Opt-in allowlisted structured diagnostics; no global logging configuration.

`failure_frames` and `describe_failure` read where a failure happened from the
exception's own traceback. Their output holds code locations and page
structure built from allowlists, never page text, attribute values or
exception messages.
"""

import logging
import re
import traceback
from collections.abc import Iterator
from types import FrameType
from typing import Protocol

from lxml import html

from librus_python_api.models import DiagnosticEvent

_PACKAGE = "librus_python_api"
# `-> NoReturn` helpers that only raise; their caller is the failure site.
RAISE_HELPERS = frozenset(
    {
        ("librus_python_api.formative_grades", "_fail"),
        ("librus_python_api.school_year_archive", "_fail"),
    }
)
_CHAIN_LIMIT = 8
_ELEMENT_LOCALS = 4
_DEPTH = 6
_NODES = 120
_ELEMENT_BYTES = 8 * 1024
_PAGE_TABLES = 12
_PAGE_ROWS = 40
_PAGE_CELLS = 8
_PAGE_NOTICES = 4
# Input types a login, search or settings form uses; others are shown as "?".
_INPUT_TYPES = frozenset(
    {"button", "checkbox", "hidden", "password", "radio", "submit", "text"}
)
# Element IDs whose presence tells a Synergia page from a login or error page.
_PAGE_MARKERS = ("graphic-menu", "user-section")
_REPORT_BYTES = 32 * 1024
# Markup observed on Synergia pages. Other class tokens, tags and attribute
# names are shown only as lengths, since they could carry data.
_CLASSES = frozenset(
    {
        "big",
        "black",
        "bolded",
        "center",
        "colspan",
        "container-background",
        "container-icon",
        "decorated",
        "detail-grades",
        "double",
        "form",
        "gradesCell",
        "grade-box",
        "grade-box-mapping",
        "helper-icon",
        "left",
        "legend",
        "line0",
        "line1",
        "luckyNumber",
        "micro",
        "newSchemaGradesByStudentTable",
        "no-border-left",
        "no-border-top",
        "ocena",
        "right",
        "screen-only",
        "sort_box",
        "spacing",
        "stretch",
        "studentRow",
        "tooltip",
        "warning-content",
    }
)
_TAGS = frozenset(
    {
        "a",
        "b",
        "body",
        "br",
        "center",
        "div",
        "em",
        "font",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "head",
        "hr",
        "html",
        "i",
        "img",
        "input",
        "label",
        "li",
        "nobr",
        "ol",
        "option",
        "p",
        "select",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    }
)
_ATTRIBUTES = frozenset(
    {
        "align",
        "alt",
        "border",
        "class",
        "colspan",
        "data-semester",
        "data-subject_id",
        "data-user_id",
        "height",
        "href",
        "id",
        "name",
        "onclick",
        "rowspan",
        "selected",
        "src",
        "style",
        "title",
        "type",
        "valign",
        "value",
        "width",
    }
)
# Element IDs shown, with digit runs masked, only in these observed shapes.
_ID_SHAPES = re.compile(
    r"(?:przedmioty(?:_OP|_oo)?_(?:<digits [0-9]+>|all|zachowanie)(?:_node)?"
    r"|tabSource|przedmioty(?:_OP)?_all)"
)
_ONCLICK = re.compile(r"\s*([A-Za-z_][\w.]{0,63})\s*\(")
_ONCLICK_NAMES = frozenset(
    {"otworz_w_nowym_oknie", "showHideOP.ShowHide", "showHideOO.ShowHide"}
)


class DiagnosticSink(Protocol):
    def __call__(self, event: DiagnosticEvent, /) -> None: ...


def logging_sink(event: DiagnosticEvent) -> None:
    """Emit allowlisted fields via stdlib logging; the application owns handlers."""
    logging.getLogger("librus_python_api").info(
        "Librus operation completed",
        extra={
            "component": "librus_python_api",
            "operation": event.operation,
            "outcome": event.outcome,
            "elapsed_seconds": event.elapsed_seconds,
            "budget_requests_dispatched": event.budget_requests_dispatched,
            "budget_response_bytes": event.budget_response_bytes,
            "frames": event.frames,
            "http_status": event.http_status,
        },
    )


def _chain(error: BaseException) -> Iterator[BaseException]:
    """The error, then the failures it replaced: an explicit cause or a
    context suppressed with `from None`. Only their frames are read."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(seen) < _CHAIN_LIMIT:
        seen.add(id(current))
        yield current
        current = current.__cause__ or (
            current.__context__ if current.__suppress_context__ else None
        )


def _owned(module: str, packages: tuple[str, ...]) -> bool:
    return any(module == name or module.startswith(name + ".") for name in packages)


def _frames(
    error: BaseException, packages: tuple[str, ...]
) -> list[tuple[FrameType, int]]:
    """Owned frames, outer call first; the original failure site is last."""
    found: list[tuple[FrameType, int]] = []
    for failure in _chain(error):
        for frame, line in traceback.walk_tb(failure.__traceback__):
            module = str(frame.f_globals.get("__name__", ""))
            if not _owned(module, packages):
                continue
            if (module, frame.f_code.co_name) in RAISE_HELPERS:
                continue
            found.append((frame, line))
    return found


def _site(frame: FrameType, line: int) -> str:
    module = str(frame.f_globals.get("__name__", ""))
    if module.startswith(_PACKAGE + "."):
        module = module[len(_PACKAGE) + 1 :]
    return f"{module}:{frame.f_code.co_qualname}:{line}"


def failure_frames(
    error: BaseException,
    limit: int = 6,
    packages: tuple[str, ...] = (_PACKAGE,),
) -> tuple[str, ...]:
    """Where `error` happened, as `module:function:line`, innermost last.

    Code locations only, opaque and specific to a release. Never raises.
    """
    try:
        return tuple(_site(frame, line) for frame, line in _frames(error, packages))[
            -limit:
        ]
    except Exception:
        return ()


def _redaction_vocabulary() -> tuple[
    frozenset[str], frozenset[str], tuple[str, ...], tuple[re.Pattern[str], ...]
]:
    # Lazy: config imports models, which this module also imports.
    from librus_python_api import config

    texts = set(config.GRADE_EMPTY_MARKERS) | {
        config.GRADE_CURRENT_HEADER,
        config.GRADE_INLINE_DETAIL_LABEL,
        config.GRADE_PREDICTED_ANNUAL_HEADER,
        *config.GRADE_MERGED_SUBJECTS,
        *config.GRADE_SUMMARY_HEADERS,
        *config.GRADE_PERIOD_HEADERS,
        *config.GRADE_PREDICTED_PERIOD_HEADERS,
        *config.GRADE_AVERAGE_HEADERS,
    }
    texts |= {label.casefold() for label in config.FORMATIVE_HEADERS}
    profile = (*config.PROFILE_LABELS, *config.PROFILE_OWNER_LABELS)
    texts |= set(profile) | {f"{label}:" for label in profile}
    texts |= set(config.PAGE_NOTICES) | {config.LOGGED_OUT_HEADING}
    prefixes = tuple(
        sorted(
            (
                value
                for name, value in vars(config).items()
                if name.endswith("_PATH_PREFIX") and isinstance(value, str)
            ),
            key=len,
            reverse=True,
        )
    )
    patterns = (config.GRADE_POINT_ROW_NODE, config.GRADE_POINT_RESULT_HEADER)
    return frozenset(texts), config.TOOLTIP_LABELS, prefixes, patterns


class _Redactor:
    def __init__(self) -> None:
        self.texts, self.labels, self.prefixes, self.patterns = _redaction_vocabulary()
        self.nodes = 0

    def text(self, value: str) -> str | None:
        normalized = " ".join(value.split())
        if not normalized:
            return None
        if (
            normalized in self.texts
            or normalized.casefold() in self.texts
            or self.patterns[1].fullmatch(normalized)
        ):
            return repr(normalized)
        return f"TEXT(len={len(normalized)})"

    def title(self, value: str) -> str:
        from librus_python_api.grade_parsers import title_label

        for points in (False, True):
            if title_label(value, points=points) in self.texts:
                return repr(title_label(value, points=points))
        parts: list[str] = []
        for chunk in re.split(r"<br\s*/?>|\n", value, flags=re.I):
            rendered = " ".join(re.sub(r"<[^>]*>", " ", chunk).split())
            if not rendered:
                parts.append("EMPTY")
                continue
            key, separator, _ = rendered.partition(":")
            key = key.strip()
            if not separator:
                parts.append(f"NO-COLON(len={len(rendered)})")
            elif key in self.labels:
                parts.append(f"[{key}]")
            else:
                parts.append(f"LABEL?(len={len(key)})")
        return "[" + ", ".join(parts) + "]"

    def href(self, value: str) -> str:
        path = value.split("?", 1)[0].split("#", 1)[0]
        for prefix in self.prefixes:
            if path.startswith(prefix):
                rest = path[len(prefix) :]
                if re.fullmatch(r"[0-9]{1,64}", rest):
                    return f"{prefix}<digits {len(rest)}>"
                return f"{prefix}<other len {len(rest)}>"
        if path.lower().startswith("javascript:"):
            return f"javascript:<len {len(path) - 11}>"
        return f"<other len {len(value)}>"

    def identifier(self, value: str) -> str:
        if self.patterns[0].fullmatch(value):
            return "<GRADE_POINT_ROW_NODE>"
        shaped = re.sub(r"[0-9]+", lambda m: f"<digits {len(m.group())}>", value)
        if len(value) <= 64 and _ID_SHAPES.fullmatch(shaped):
            return shaped
        return f"<len {len(value)}>"

    def attribute(self, name: str, value: str) -> str | None:
        if name not in _ATTRIBUTES:
            return f"attr?{len(name)}=<len {len(value)}>"
        if name == "class":
            tokens = [
                token if token in _CLASSES else f"?{len(token)}"
                for token in value.split()
            ]
            return f"class={'.'.join(tokens)}"
        if name in ("colspan", "rowspan"):
            shown = (
                value if re.fullmatch(r"[0-9]{1,3}", value) else f"<len {len(value)}>"
            )
            return f"{name}={shown}"
        if name in ("id", "name"):
            return f"{name}={self.identifier(value)}"
        if name == "href":
            return f"href={self.href(value)}"
        if name == "title":
            return f"title={self.title(value)}"
        if name == "style":
            hidden = "display:none" in value.replace(" ", "").casefold()
            return "style=display:none" if hidden else "style"
        if name == "onclick":
            call = _ONCLICK.match(value)
            if call is not None and call.group(1) in _ONCLICK_NAMES:
                return f"onclick={call.group(1)}(...)"
            return f"onclick=<len {len(value)}>"
        return f"{name}=<len {len(value)}>"

    def element(self, element: html.HtmlElement, depth: int = 0) -> str:
        self.nodes += 1
        tag = element.tag if isinstance(element.tag, str) else "#comment"
        if tag == "#comment" or tag in ("script", "style"):
            return f"<{tag} len={len(element.text or '')}>"
        tag = _tag(tag)
        attributes = [
            shown
            for name, value in element.attrib.items()
            if (shown := self.attribute(str(name), str(value))) is not None
        ]
        opening = " ".join([tag, *attributes])
        parts: list[str] = []
        if (shown := self.text(element.text or "")) is not None:
            parts.append(shown)
        for child in element:
            if depth + 1 >= _DEPTH or self.nodes >= _NODES:
                parts.append("...")
                break
            parts.append(self.element(child, depth + 1))
            if (shown := self.text(child.tail or "")) is not None:
                parts.append(shown)
        return f"<{opening}>{''.join(parts)}</{tag}>"


def _tag(name: str) -> str:
    return name if name in _TAGS else f"?tag{len(name)}"


def _path(element: html.HtmlElement, redactor: _Redactor) -> str:
    steps: list[str] = []
    node: html.HtmlElement | None = element
    while node is not None and isinstance(node.tag, str) and len(steps) < 12:
        parent = node.getparent()
        index = (
            [sibling for sibling in parent if sibling.tag == node.tag].index(node) + 1
            if parent is not None
            else 1
        )
        classes = node.get("class", "").split()
        token = _tag(node.tag) + (
            "." + str(redactor.attribute("class", " ".join(classes)))[6:]
            if classes
            else ""
        )
        steps.append(f"{token}[{index}]" if parent is not None else token)
        if node.tag == "table" and "decorated" in node.get("class", "").split():
            break
        node = parent
    return " > ".join(reversed(steps))


def _cell(cell: html.HtmlElement, redactor: _Redactor) -> str:
    spans = "".join(
        f" {redactor.attribute(name, str(cell.get(name)))}"
        for name in ("colspan", "rowspan")
        if cell.get(name, "1") != "1"
    )
    text = redactor.text(cell.text_content()) or "EMPTY"
    return f"{_tag(str(cell.tag))}{spans}[{text}]"


def _shown(label: str, texts: list[str]) -> str:
    return " ".join([f"  {label}: {len(texts)}", *texts[:_PAGE_NOTICES]])


def _page_summary(document: html.HtmlElement, redactor: _Redactor) -> list[str]:
    """A whole page as its markers, forms, notices and tables, row by row.

    A page that fails as a whole (no expected table, an unknown notice, a
    login or error page) is told apart by these, not by its first elements.
    Only the first tables, rows and cells are shown.
    """
    body = document.find("body")
    text = " ".join((body if body is not None else document).text_content().split())
    present = {
        marker: document.get_element_by_id(marker, None) is not None
        for marker in _PAGE_MARKERS
    }
    markers = " ".join(
        f"{marker}={'yes' if found else 'no'}" for marker, found in present.items()
    )
    lines = [f"  body text len={len(text)} {markers}"]
    title = document.find(".//title")
    titles = [] if title is None else [redactor.text(title.text_content()) or "EMPTY"]
    lines.append(_shown("title", titles))
    headings = [
        redactor.text(heading.text_content()) or "EMPTY"
        for heading in document.iter("h1", "h2", "h3")
    ]
    lines.append(_shown("headings", headings))
    notices = document.xpath(
        '//div[contains(concat(" ",normalize-space(@class)," ")," warning-content ")]'
    )
    shown = [redactor.text(notice.text_content()) or "EMPTY" for notice in notices]
    lines.append(_shown("notices", shown))
    forms = [redactor.href(form.get("action", "")) for form in document.iter("form")]
    inputs: dict[str, int] = {}
    for field in document.iter("input"):
        kind = field.get("type", "text").casefold()
        kind = kind if kind in _INPUT_TYPES else "?"
        inputs[kind] = inputs.get(kind, 0) + 1
    counted = " ".join(f"{kind}={count}" for kind, count in sorted(inputs.items()))
    lines.append(_shown("forms", forms) + (f"; inputs {counted}" if counted else ""))
    tables = list(document.iter("table"))
    lines.append(f"  tables: {len(tables)}")
    for table in tables[:_PAGE_TABLES]:
        rows = [
            row
            for row in table.iter("tr")
            if next(row.iterancestors("table"), None) is table
        ]
        lines.append(f"  {_path(table, redactor)}: {len(rows)} rows")
        for row in rows[:_PAGE_ROWS]:
            cells = [cell for cell in row if cell.tag in ("td", "th")]
            more = " ..." if len(cells) > _PAGE_CELLS else ""
            rendered = " ".join(_cell(cell, redactor) for cell in cells[:_PAGE_CELLS])
            lines.append(f"    {rendered}{more}")
        if len(rows) > _PAGE_ROWS:
            lines.append("    ...")
    if len(tables) > _PAGE_TABLES:
        lines.append("  ...")
    return lines


def _is_page(element: html.HtmlElement) -> bool:
    return element.getparent() is None and element.tag == "html"


def describe_failure(error: BaseException) -> str | None:
    """The page structure around a failure, for a bug report.

    Shows the HTML elements held by the innermost library frame that holds
    any: tags, safe class tokens, known tooltip labels, known link families
    and lengths. A whole page is summarized last (see _page_summary). Text
    and attribute values are masked unless they equal a parser constant.
    Returns None when there is nothing to show; never raises.
    """
    try:
        redactor = _Redactor()
        for frame, line in reversed(_frames(error, (_PACKAGE,))):
            local_items = list(frame.f_locals.items())
            elements = [
                (name, value)
                for name, value in local_items
                if isinstance(value, html.HtmlElement)
            ][:_ELEMENT_LOCALS]
            sequences = [
                (name, value)
                for name, value in local_items
                if isinstance(value, (list, tuple))
                and value
                and all(isinstance(item, html.HtmlElement) for item in value)
            ][:_ELEMENT_LOCALS]
            if not elements and not sequences:
                continue
            lines = [f"at {_site(frame, line)}"]
            # The elements nearest the failure first; a page summary last.
            for name, value in sorted(elements, key=lambda item: _is_page(item[1])):
                redactor.nodes = 0
                if _is_page(value):
                    summary = "\n".join(_page_summary(value, redactor))
                    if len(summary) > _ELEMENT_BYTES:
                        summary = summary[:_ELEMENT_BYTES] + "...(truncated)"
                    lines += [f"{name}: page", summary]
                    continue
                lines.append(f"{name}: {_path(value, redactor)}")
                rendered = redactor.element(value)
                if len(rendered) > _ELEMENT_BYTES:
                    rendered = rendered[:_ELEMENT_BYTES] + "...(truncated)"
                lines.append("  " + rendered)
            for name, items in sequences:
                tags = ",".join(str(item.tag) for item in items[:20])
                lines.append(f"{name}: {len(items)} elements: {tags}")
            report = "\n".join(lines)
            if len(report) > _REPORT_BYTES:
                report = report[:_REPORT_BYTES] + "...(truncated)"
            return report
        return None
    except Exception:
        return None
