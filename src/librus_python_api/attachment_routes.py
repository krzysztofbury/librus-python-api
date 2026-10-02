"""Fail-closed reference and signed-destination validation, never network I/O."""

import re
from urllib.parse import urlsplit

from librus_python_api.config import (
    ATTACHMENT_KEY_PATTERN,
    ATTACHMENT_MAX_BYTES,
    ATTACHMENT_MAX_LOCATION_LENGTH,
    ATTACHMENT_REDIRECT_PATH,
    ConnectionSettings,
)
from librus_python_api.exceptions import ErrorKind, LibrusError
from librus_python_api.message_content import validate_reference
from librus_python_api.models import MessageAttachmentReference


def validate_attachment_reference(
    reference: MessageAttachmentReference, account: str
) -> None:
    if not isinstance(reference, MessageAttachmentReference):
        raise LibrusError(ErrorKind.INVALID_INPUT)
    validate_reference(reference.message, account)
    if (
        type(reference.identifier) is not str
        or re.fullmatch(r"[0-9]{1,64}", reference.identifier) is None
    ):
        raise LibrusError(ErrorKind.INVALID_INPUT)


def validate_key(key: str) -> None:
    if (
        type(key) is not str
        or ATTACHMENT_KEY_PATTERN.fullmatch(key) is None
        or key in {".", ".."}
    ):
        raise LibrusError(ErrorKind.ACCESS_DENIED)


def validate_max_bytes(max_bytes: int) -> None:
    if type(max_bytes) is not int or not 1 <= max_bytes <= ATTACHMENT_MAX_BYTES:
        raise LibrusError(ErrorKind.INVALID_INPUT)


def signed_attachment_key(location: str, connection: ConnectionSettings) -> str:
    """Only an exact absolute official destination or explicitly configured loopback."""
    if (
        type(location) is not str
        or not 1 <= len(location) <= ATTACHMENT_MAX_LOCATION_LENGTH
        or any(ord(c) <= 32 or ord(c) >= 127 for c in location)
        or any(c in location for c in ("%", "\\", "?", "#"))
    ):
        raise LibrusError(ErrorKind.ACCESS_DENIED)
    invalid = False
    key = ""
    try:
        target = urlsplit(location)
        expected = urlsplit(connection.download_origin)
        authorities = {expected.netloc}
        if expected.hostname == "sandbox.librus.pl":
            authorities = {"sandbox.librus.pl", "sandbox.librus.pl:443"}
        prefix, _, suffix = ATTACHMENT_REDIRECT_PATH.partition("{key}")
        if (
            target.scheme != expected.scheme
            or target.netloc not in authorities
            or target.username is not None
            or target.password is not None
            or not target.path.startswith(prefix)
            or suffix
        ):
            invalid = True
        else:
            key = target.path[len(prefix) :]
    except ValueError:
        invalid = True
    if invalid:
        raise LibrusError(ErrorKind.ACCESS_DENIED)
    validate_key(key)
    return key
