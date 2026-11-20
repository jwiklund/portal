from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def now_iso() -> str:
    """Current UTC time as a seconds-precision ISO string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class Notification(SQLModel, table=True):
    """An admin notification/announcement.

    ``created_at`` doubles as the notification's date. The API accepts an
    optional ``date`` so that repeated submissions can be de-duplicated by
    (date, title) instead of racing the clock.
    """

    __tablename__ = "notifications"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(default="", index=True)
    text: str = ""
    created_at: str = Field(default_factory=now_iso, index=True)
    read: bool = Field(default=False)
