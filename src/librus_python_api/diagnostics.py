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
_REPORT_BYTES = 32 * 1024
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}")
_ATTRIBUTE = re.compile(r"[a-z][a-z0-9_:-]{0,39}")
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
            or any(pattern.fullmatch(normalized) for pattern in self.patterns)
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
        for pattern, name in ((self.patterns[0], "GRADE_POINT_ROW_NODE"),):
            if pattern.fullmatch(value):
                return f"<{name}>"
        shaped = re.sub(r"[0-9]+", lambda m: f"<digits {len(m.group())}>", value)
        if len(value) <= 64 and re.fullmatch(r"[A-Za-z_<>0-9 -]+", shaped):
            return shaped
        return f"<len {len(value)}>"

    def attribute(self, name: str, value: str) -> str | None:
        if not _ATTRIBUTE.fullmatch(name):
            return None
        if name == "class":
            tokens = [
                token
                if _TOKEN.fullmatch(token) and not re.search(r"[0-9]{3}", token)
                else "?"
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
        token = node.tag + (
            "." + str(redactor.attribute("class", " ".join(classes)))[6:]
            if classes
            else ""
        )
        steps.append(f"{token}[{index}]" if parent is not None else token)
        if node.tag == "table" and "decorated" in node.get("class", "").split():
            break
        node = parent
    return " > ".join(reversed(steps))


def describe_failure(error: BaseException) -> str | None:
    """The page structure around a failure, for a bug report.

    Shows the HTML elements held by the innermost library frame that holds
    any: tags, safe class tokens, known tooltip labels, known link families
    and lengths. Text and attribute values are masked unless they equal a
    parser constant. Returns None when there is nothing to show; never raises.
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
            for name, value in elements:
                redactor.nodes = 0
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
