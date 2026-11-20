from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PushSubscription(SQLModel, table=True):
    """A browser push subscription (one row per endpoint, per browser install)."""

    __tablename__ = "push_subscriptions"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    endpoint: str = Field(unique=True, index=True)
    p256dh: str = ""
    auth: str = ""
    user: str | None = None
    user_agent: str | None = None
    created_at: str = Field(default_factory=_now_iso)
