"""Joined resource ownership even when callers cancel repeatedly."""

import asyncio


async def join_owned[T](future: asyncio.Future[T]) -> bool:
    """Join without forwarding cancellation; return whether joining was canceled.

    Cleanup must finish before resource/admission slots can be reused. This helper
    is only for already-owned work, never for ordinary uncancelable operations.
    """
    interrupted = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            interrupted = True
        except Exception:
            break
    if not future.cancelled():
        future.exception()
    return interrupted
