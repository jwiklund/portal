from __future__ import annotations

from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

from born_portal.notifications.model import Notification, now_iso


class NotificationStore:
    """SQLite storage for admin notifications."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def save(self, notification: Notification) -> int:
        """Insert or update a notification. Returns the row id."""
        with Session(self._engine) as session:
            if notification.id:
                existing = session.get(Notification, notification.id)
                if existing is not None:
                    existing.title = notification.title
                    existing.text = notification.text
                    existing.read = notification.read
                    existing.created_at = notification.created_at or now_iso()
                    session.add(existing)
                    session.commit()
                    return notification.id
            row = Notification(
                title=notification.title,
                text=notification.text,
                created_at=notification.created_at or now_iso(),
                read=notification.read,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            assert row.id is not None
            return row.id

    def add_if_new(
        self,
        title: str,
        text: str,
        date: str | None = None,
    ) -> tuple[int, bool]:
        """Insert a notification unless one with the same (date, title) exists.

        The title match is case-insensitive; the date is compared by its
        ``YYYY-MM-DD`` prefix. Returns ``(row_id, created)``.
        """
        title = title.strip()
        created_at = (date or "").strip() or now_iso()
        with Session(self._engine) as session:
            existing = self._find_by_date_title(session, created_at, title)
            if existing is not None:
                assert existing.id is not None
                return existing.id, False
            row = Notification(title=title, text=text, created_at=created_at)
            session.add(row)
            session.commit()
            session.refresh(row)
            assert row.id is not None
            return row.id, True

    def find_by_date_title(self, date: str, title: str) -> Notification | None:
        """Look up a notification by (date, title), case-insensitively."""
        with Session(self._engine) as session:
            return self._find_by_date_title(session, date, title)

    @staticmethod
    def _find_by_date_title(
        session: Session,
        date: str,
        title: str,
    ) -> Notification | None:
        day = (date or "")[:10]
        rows = session.exec(
            select(Notification).where(
                func.lower(Notification.title) == title.strip().lower()
            )
        )
        for row in rows:
            if (row.created_at or "")[:10] == day:
                return row
        return None

    def get_by_id(self, id: int) -> Notification | None:
        with Session(self._engine) as session:
            return session.get(Notification, id)

    def list_all(self, limit: int = 200) -> list[Notification]:
        """All notifications, newest first."""
        with Session(self._engine) as session:
            rows = list(session.exec(select(Notification)))
        rows.sort(key=lambda row: (row.created_at, row.id or 0), reverse=True)
        return rows[:limit]

    def unread_count(self) -> int:
        with Session(self._engine) as session:
            return session.exec(
                select(func.count())
                .select_from(Notification)
                .where(Notification.read == False)
            ).one()

    def mark_read_many(self, ids: list[int]) -> int:
        """Mark the given notifications read. Returns how many changed."""
        if not ids:
            return 0
        with Session(self._engine) as session:
            rows = session.exec(
                select(Notification).where(col(Notification.id).in_(ids))
            ).all()
            changed = 0
            for row in rows:
                if not row.read:
                    row.read = True
                    session.add(row)
                    changed += 1
            session.commit()
            return changed

    def set_read(self, id: int, read: bool = True) -> bool:
        with Session(self._engine) as session:
            row = session.get(Notification, id)
            if row is None:
                return False
            row.read = read
            session.add(row)
            session.commit()
            return True

    def delete(self, id: int) -> bool:
        with Session(self._engine) as session:
            row = session.get(Notification, id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
