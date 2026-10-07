"""Named live checks: each declares its upstream reads and reports coverage."""

import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from librus_python_api import RequestBudget
from scripts.live_check.report import IDENTIFIER, Coverage


@dataclass(frozen=True, slots=True)
class Observed:
    coverage: Coverage
    facts: tuple[tuple[str, int | bool], ...] = ()


def coverage_of(size: int, **facts: int | bool) -> Observed:
    coverage = Coverage.POPULATED if size > 0 else Coverage.EMPTY
    return Observed(coverage, tuple(facts.items()))


class CheckFailed(Exception):
    """A bounded property did not hold. Carries a fixed code, never data."""

    def __init__(self, code: str) -> None:
        if not IDENTIFIER.fullmatch(code):
            raise ValueError("check codes are fixed identifiers")
        super().__init__(code)
        self.code = code


@dataclass(slots=True)
class Context:
    client: Any
    budget: RequestBudget
    today: date
    expected_identity: str | None = None
    state: dict[str, Any] = field(default_factory=dict)


type Probe = Callable[[Context], Awaitable[Observed]]


def _always(_: Any) -> bool:
    return True


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    probe: Probe
    reads: frozenset[str]
    references: frozenset[str]
    requires: Callable[[Any], bool] = _always
    after: str | None = None


def check(
    name: str,
    *,
    reads: Iterable[str] = (),
    references: Iterable[str] = (),
    requires: Callable[[Any], bool] | None = None,
    after: str | None = None,
) -> Callable[[Probe], Check]:
    def wrap(probe: Probe) -> Check:
        return Check(
            name,
            probe,
            frozenset(reads),
            frozenset(references),
            requires or _always,
            after,
        )

    return wrap


def has(method: str) -> Callable[[Any], bool]:
    return lambda client: hasattr(client, method)


def accepts(method: str, parameter: str) -> Callable[[Any], bool]:
    def supported(client: Any) -> bool:
        target = getattr(client, method, None)
        return target is not None and parameter in inspect.signature(target).parameters

    return supported


def identity_key(identity: Any) -> str:
    return f"{identity.owner.id}:{identity.student.id}"
