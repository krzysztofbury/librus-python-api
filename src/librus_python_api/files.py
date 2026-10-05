"""Optional local attachment publication; no implicit destination or network client."""

import asyncio
import hashlib
import os
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from librus_python_api.attachment_routes import validate_max_bytes
from librus_python_api.attachments import AttachmentStream
from librus_python_api.config import ATTACHMENT_MAX_BYTES
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.lifecycle import join_owned

MAX_FILENAME_BYTES = 180
MAX_FILENAME_ATTEMPTS = 100
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
}


@dataclass(frozen=True, slots=True)
class PublishedAttachment:
    path: Path = field(repr=False)
    size_bytes: int
    sha256: str = field(repr=False)
    content_type: str | None = field(repr=False)


def safe_attachment_filename(filename: str) -> str:
    """Treat upstream names as untrusted display data, never as a relative path."""
    if type(filename) is not str or len(filename) > 4096:
        raise LibrusError(ErrorKind.INVALID_INPUT)
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(
        "_" if unicodedata.category(c).startswith("C") or c in '<>:"|?*' else c
        for c in name
    ).strip(" .")
    if name.split(".", 1)[0].upper() in _RESERVED:
        name = "_" + name
    # Truncate on UTF-8 codepoint boundaries, leaving room for collision suffixes.
    name = name.encode()[:MAX_FILENAME_BYTES].decode("utf-8", errors="ignore")
    return name.rstrip(" .") or "attachment"


async def _disk[T](function: Callable[[], T]) -> T:
    task = asyncio.create_task(asyncio.to_thread(function))
    interrupted = await join_owned(task)
    if interrupted:
        raise asyncio.CancelledError
    return task.result()


def _write_all(descriptor: int, chunk: bytes) -> None:
    view = memoryview(chunk)
    while view:
        count = os.write(descriptor, view)
        if count <= 0:
            raise OSError("Local write made no progress")
        view = view[count:]


def _publish(directory: int, descriptor: int, temporary: str, name: str) -> str:
    os.fsync(descriptor)
    path = Path(name)
    for index in range(MAX_FILENAME_ATTEMPTS):
        candidate = name if index == 0 else f"{path.stem} ({index}){path.suffix}"
        try:
            # A same-directory hard link is atomic and fails if any target exists,
            # including a dangling symlink. There is no check-then-replace race.
            os.link(
                temporary,
                candidate,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
        except FileExistsError:
            continue
        os.fsync(directory)
        return candidate
    raise LibrusError(ErrorKind.LIMIT)


async def publish_attachment(
    stream: AttachmentStream,
    directory: Path,
    *,
    filename: str,
    max_bytes: int = ATTACHMENT_MAX_BYTES,
) -> PublishedAttachment:
    """Publish only a complete bounded stream to an existing caller-selected directory.

    Files are owner-only. Failed/cancelled reads remove only this call's temporary
    file. Cancellation during the atomic commit may leave a complete final file;
    it never overwrites or removes an existing final path. All disk workers are
    joined before closing descriptors or removing their temporary file.
    """
    if not isinstance(stream, AttachmentStream) or not isinstance(directory, Path):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    validate_max_bytes(max_bytes)
    # Directory-relative, no-follow opens are the safety boundary (POSIX only).
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise LibrusError(ErrorKind.UNSUPPORTED_CAPABILITY)
    name = safe_attachment_filename(filename)
    directory_fd = descriptor = None
    temporary = ".librus-attachment-" + secrets.token_hex(16)
    size = 0
    digest = hashlib.sha256()
    failed = False
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        async with stream:
            async for chunk in stream:
                size += len(chunk)
                if size > max_bytes:
                    raise LibrusError(ErrorKind.LIMIT)
                await _disk(partial(_write_all, descriptor, chunk))
                digest.update(chunk)
            if not stream.complete:
                raise LibrusError(ErrorKind.PARSE)
            content_type = stream.metadata.headers.content_type
        final = await _disk(lambda: _publish(directory_fd, descriptor, temporary, name))
        return PublishedAttachment(
            directory / final, size, digest.hexdigest(), content_type
        )
    except OSError:
        failed = True
    finally:
        # Local cleanup has no outstanding worker and targets only our random name.
        try:
            if descriptor is not None:
                os.close(descriptor)
                assert directory_fd is not None
                os.unlink(temporary, dir_fd=directory_fd)
        except OSError:
            failed = True
        finally:
            if directory_fd is not None:
                try:
                    os.close(directory_fd)
                except OSError:
                    failed = True
        if failed:
            raise LibrusError(ErrorKind.STORAGE) from None
    raise LibrusError(ErrorKind.STORAGE)
