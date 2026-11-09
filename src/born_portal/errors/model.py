from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ErrorRecord(SQLModel, table=True):
    """A captured error plus the request context needed to reproduce it.

    The request body and query string are stored redacted and truncated (see
    ``errors.report``); secrets such as OAuth codes, Spotify tokens, passwords
    and session cookies are never persisted.
    """

    __tablename__ = "error_log"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    created_at: str = Field(default_factory=_now_iso, index=True)
    method: str = ""
    path: str = ""
    user: str | None = None
    exception_type: str = ""
    message: str = ""
    traceback: str = ""
    query: str = ""
    input: str = ""
    user_agent: str | None = None
    context: str = ""
