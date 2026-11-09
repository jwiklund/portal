from __future__ import annotations

from sqlalchemy import Engine, func
from sqlalchemy import delete as sql_delete
from sqlmodel import Session, select

from born_portal.errors.model import ErrorRecord


class ErrorStore:
    """SQLite storage for captured errors."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def save(self, record: ErrorRecord) -> int:
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            assert record.id is not None
            return record.id

    def list_recent(self, limit: int = 100) -> list[ErrorRecord]:
        with Session(self._engine) as session:
            records = list(session.exec(select(ErrorRecord)))
        records.sort(
            key=lambda record: (record.created_at, record.id or 0),
            reverse=True,
        )
        return records[:limit]

    def get_by_id(self, id: int) -> ErrorRecord | None:
        with Session(self._engine) as session:
            return session.get(ErrorRecord, id)

    def count(self) -> int:
        with Session(self._engine) as session:
            return session.exec(select(func.count()).select_from(ErrorRecord)).one()

    def clear(self) -> int:
        with Session(self._engine) as session:
            count = session.exec(select(func.count()).select_from(ErrorRecord)).one()
            session.execute(sql_delete(ErrorRecord))
            session.commit()
            return count
