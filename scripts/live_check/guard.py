"""A transport that can only make a profile's declared, side-effect-free reads.

Authentication (`login_*`) and the modern session handoff are allowed, as the
library performs them itself. Everything else must be declared by a check and
be marked `none` or `select_view` in config.py, which mirrors the OpenAPI
contract. Refusals are recorded so a run can never pass after a refusal.
"""

from collections.abc import Iterable, Mapping
from typing import ClassVar, NoReturn

from librus_python_api import RequestBudget
from librus_python_api.config import ENDPOINTS, SideEffect
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.models import RequestForm, TransportResponse
from librus_python_api.transport import AiohttpTransport

SAFE = frozenset({SideEffect.NONE, SideEffect.SELECT_VIEW})
# Marked `none` upstream, but files are out of scope for live checks.
EXCLUDED = frozenset(
    {
        "attachment_resolve",
        "attachment_download",
        "modern_attachment_resolve",
        "modern_archive_attachment_resolve",
    }
)


class GuardedTransport(AiohttpTransport):
    allowed: ClassVar[frozenset[str]] = frozenset()
    with_reference: ClassVar[frozenset[str]] = frozenset()
    violations: ClassVar[list[str]] = []

    def _refuse(self, name: str) -> NoReturn:
        self.violations.append(name)
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)

    async def request(
        self,
        endpoint_id: str,
        budget: RequestBudget,
        *,
        form: RequestForm = None,
        reference_id: str | None = None,
        query: Mapping[str, str] | None = None,
    ) -> TransportResponse:
        if not endpoint_id.startswith("login_") and (
            endpoint_id not in self.allowed
            or (reference_id is not None and endpoint_id not in self.with_reference)
        ):
            self._refuse(endpoint_id)
        if query is None:
            # Older installed builds have no `query` parameter.
            return await super().request(
                endpoint_id, budget, form=form, reference_id=reference_id
            )
        return await super().request(
            endpoint_id, budget, form=form, reference_id=reference_id, query=query
        )

    async def send_message(self, *args: object, **kwargs: object) -> NoReturn:
        self._refuse("send_message")

    async def send_modern_message(self, *args: object, **kwargs: object) -> NoReturn:
        self._refuse("modern_send_message")

    async def consume_schedule_events(
        self, *args: object, **kwargs: object
    ) -> NoReturn:
        self._refuse("consume_schedule_events")

    async def resolve_attachment(self, *args: object, **kwargs: object) -> NoReturn:
        self._refuse("attachment_resolve")

    async def resolve_modern_attachment(
        self, *args: object, **kwargs: object
    ) -> NoReturn:
        self._refuse("modern_attachment_resolve")

    async def stream_download(self, *args: object, **kwargs: object) -> NoReturn:
        self._refuse("attachment_download")


def guarded(
    allowed: Iterable[str], with_reference: Iterable[str]
) -> type[GuardedTransport]:
    reads, references = frozenset(allowed), frozenset(with_reference)
    for name in reads:
        if ENDPOINTS[name].side_effect not in SAFE or name in EXCLUDED:
            raise ValueError("unsafe endpoint declared: " + name)
    if not references <= reads:
        raise ValueError("references must be declared reads")
    return type(
        "ProfileTransport",
        (GuardedTransport,),
        {"allowed": reads, "with_reference": references, "violations": []},
    )
