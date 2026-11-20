"""Load the VAPID key pair used to sign web-push messages.

The key pair is read from the ``VAPID_PUBLIC_KEY``/``VAPID_PRIVATE_KEY`` env
vars, or from ``VAPID_KEY_FILE`` when that exists. Nothing is generated or
written here: when no keys are configured, push is simply unavailable and
:func:`load_vapid` raises :class:`VapidNotConfigured`. Create a pair with the
``vapid-keys`` CLI command and configure it.
"""

from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid

from born_portal.core import (
    VAPID_KEY_FILE,
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
)


class VapidNotConfigured(Exception):
    """Raised when no VAPID key pair is configured."""


def _public_key_b64(vapid: Vapid) -> str:
    """The application-server key the browser needs (base64url, unpadded)."""
    public_key = vapid.public_key
    assert public_key is not None
    raw = public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate() -> tuple[str, str]:
    """Return a fresh ``(public_key, private_key_pem)`` pair."""
    vapid = Vapid()
    vapid.generate_keys()
    return _public_key_b64(vapid), vapid.private_pem().decode("ascii")


def _configured_keys() -> tuple[str, str] | None:
    """The configured pair, or ``None`` when push has not been set up."""
    if VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY:
        return VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY
    if VAPID_KEY_FILE.exists():
        data = json.loads(VAPID_KEY_FILE.read_text())
        return data["public_key"], data["private_key"]
    return None


def vapid_configured() -> bool:
    """Whether a VAPID key pair is available (env vars or key file)."""
    try:
        return _configured_keys() is not None
    except Exception:  # noqa: BLE001 - a bad key file means "not usable"
        return False


def load_vapid() -> tuple[str, str]:
    """Return the ``(application_server_key, private_key_pem)`` pair.

    Raises :class:`VapidNotConfigured` when neither the env vars nor the key
    file are present; it never generates keys or touches the filesystem.
    """
    keys = _configured_keys()
    if keys is None:
        raise VapidNotConfigured(
            "No VAPID key pair configured. Run "
            "`python -m born_portal.main vapid-keys` and set "
            "VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY."
        )
    return keys


def load_vapid_instance() -> Vapid:
    """Return the VAPID private key as a :class:`py_vapid.Vapid` instance.

    ``pywebpush`` accepts a ``Vapid`` instance, a key-file path, or a
    base64url raw/DER string -- but *not* a PEM string (its fallback is
    ``Vapid.from_string``, which cannot parse PEM). So the configured key,
    which is PEM, must be converted here before it reaches ``webpush``.

    Raises :class:`VapidNotConfigured` when push has not been set up.
    """
    _, private_key = load_vapid()
    if "-----BEGIN" in private_key:
        return Vapid.from_pem(private_key.encode("ascii"))
    return Vapid.from_string(private_key)
