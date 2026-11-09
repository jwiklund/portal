"""Capture errors and their request context for later review.

The preferred way to handle an unexpected exception in a request handler is:

1. catch it,
2. call ``await record_error(request, exc, context=...)``,
3. return a user-level message on the error page
   (``render("error.html", request, message=...)``).

Unhandled exceptions are captured globally as well (see ``errors.routes``), so a
handler that forgets to catch still gets recorded -- it just cannot attach its
own context or choose a friendlier message.
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any
from urllib.parse import parse_qsl, urlencode

from born_portal.errors.model import ErrorRecord
from born_portal.errors.store import ErrorStore

logger = logging.getLogger(__name__)

# Truncate stored input so a huge form/JSON body cannot bloat the table.
_MAX_INPUT = 10_000

# Form/JSON keys whose values are secrets and must never be persisted. Matched
# as substrings, case-insensitively ("access_token" matches "token").
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "session",
    "api_key",
    "apikey",
    "code",
    "state",
)

_store: ErrorStore | None = None


def configure(engine) -> None:
    """Point ``record_error`` at the database it should write to."""
    global _store
    _store = ErrorStore(engine)


def _is_sensitive(key: Any) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _redact_query(raw: bytes) -> str:
    """Return the query string with sensitive values masked out."""
    if not raw:
        return ""
    try:
        pairs = parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True)
    except Exception:  # noqa: BLE001
        return "[unparseable]"
    redacted = [
        (key, "[redacted]" if _is_sensitive(key) else value) for key, value in pairs
    ]
    return urlencode(redacted)


def _redact(value: Any) -> Any:
    """Recursively replace sensitive values with ``[redacted]``."""
    if isinstance(value, dict):
        return {
            key: "[redacted]" if _is_sensitive(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Multipart uploads arrive as FileBuffer-like objects; keep the filename
    # only, never the file contents.
    filename = getattr(value, "filename", None)
    if filename:
        return f"[file: {filename}]"
    return "[unserializable]"


async def _capture_input(request) -> str:
    """Best-effort capture of a form or JSON body, redacted and truncated."""
    try:
        content_type = (request.content_type() or b"").decode("latin-1").lower()
    except Exception:  # noqa: BLE001
        return ""

    if "json" not in content_type and "form" not in content_type:
        return ""

    try:
        if "json" in content_type:
            data: Any = await request.json()
        else:
            form = await request.form()
            if form is None:
                return ""
            data = dict(form)
        return json.dumps(_redact(data), ensure_ascii=False)[:_MAX_INPUT]
    except Exception:  # noqa: BLE001
        # Never let input capture mask the original error.
        return ""


async def record_error(
    request,
    exc: BaseException,
    *,
    context: dict | None = None,
) -> int | None:
    """Persist ``exc`` and its request context. Never raises.

    ``request`` may be ``None`` for errors outside a request/response cycle
    (for example a background conversion task); ``context`` can carry any
    extra details worth keeping. Returns the new row id, or ``None`` if the
    error could not be stored (in which case it is logged instead).
    """
    if _store is None:
        logger.exception("Unhandled error (no error store configured)", exc_info=exc)
        return None

    try:
        method = ""
        path = ""
        query = ""
        user_value = None
        user_agent = None
        input_text = ""

        if request is not None:
            method = getattr(request, "method", "") or ""
            try:
                path = request.path
            except Exception:  # noqa: BLE001
                path = ""
            try:
                query = _redact_query(request.url.query or b"")
            except Exception:  # noqa: BLE001
                query = ""
            try:
                user_value = request.session.get("user")
            except Exception:  # noqa: BLE001
                user_value = None
            try:
                header = request.get_first_header(b"user-agent")
                user_agent = header.decode("utf-8", "replace") if header else None
            except Exception:  # noqa: BLE001
                user_agent = None
            input_text = await _capture_input(request)

        record = ErrorRecord(
            method=method,
            path=path,
            user=user_value,
            exception_type=type(exc).__name__,
            message=str(exc),
            traceback="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
            query=query,
            input=input_text,
            user_agent=user_agent,
            context=json.dumps(_redact(context or {}), ensure_ascii=False, default=str),
        )
        return _store.save(record)
    except Exception:
        logger.exception("Failed to record error")
        return None
