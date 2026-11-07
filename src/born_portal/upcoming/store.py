from __future__ import annotations

from sqlmodel import Session, select

from born_portal.upcoming.model import UpcomingData


class UpcomingStore:
    """SQLite storage for parsed upcoming data."""

    def __init__(self, engine):
        self._engine = engine

    def save(self, upcoming: UpcomingData) -> int:
        """Save an upcoming item to the database. Returns the row id."""
        with Session(self._engine) as session:
            if upcoming.id is not None:
                existing = session.get(UpcomingData, upcoming.id)
                if existing is not None:
                    existing.url = upcoming.url
                    existing.name = upcoming.name
                    existing.description = upcoming.description
                    existing.location = upcoming.location
                    existing.price = upcoming.price
                    existing.date = upcoming.date
                    existing.ticket = upcoming.ticket
                    session.add(existing)
                    session.commit()
                    session.refresh(existing)
                    assert existing.id is not None
                    return existing.id

            # Insert new upcoming item, or update the row with the same URL.
            existing = session.exec(
                select(UpcomingData).where(UpcomingData.url == upcoming.url)
            ).first()
            if existing is None:
                existing = UpcomingData(
                    url=upcoming.url,
                    name=upcoming.name,
                    description=upcoming.description,
                    location=upcoming.location,
                    price=upcoming.price,
                    date=upcoming.date,
                    ticket=upcoming.ticket,
                )
                session.add(existing)
            else:
                existing.name = upcoming.name
                existing.description = upcoming.description
                existing.location = upcoming.location
                existing.price = upcoming.price
                existing.date = upcoming.date
                existing.ticket = upcoming.ticket
                session.add(existing)
            session.commit()
            session.refresh(existing)
            assert existing.id is not None
            return existing.id

    def get(self, url: str) -> UpcomingData | None:
        """Retrieve an upcoming item by URL."""
        with Session(self._engine) as session:
            return session.exec(
                select(UpcomingData).where(UpcomingData.url == url)
            ).first()

    def get_by_id(self, id: int) -> UpcomingData | None:
        """Retrieve an upcoming item by id."""
        with Session(self._engine) as session:
            return session.get(UpcomingData, id)

    def exists(self, url: str) -> bool:
        """Check if an upcoming item exists in the database."""
        with Session(self._engine) as session:
            return (
                session.exec(
                    select(UpcomingData.id).where(UpcomingData.url == url)
                ).first()
                is not None
            )

    def exists_by_id(self, id: int) -> bool:
        """Check if an upcoming item exists by id."""
        with Session(self._engine) as session:
            return session.get(UpcomingData, id) is not None

    def get_url_by_id(self, id: int) -> str | None:
        """Get the URL for an upcoming item by id."""
        with Session(self._engine) as session:
            return session.exec(
                select(UpcomingData.url).where(UpcomingData.id == id)
            ).first()

    def list_all(self) -> list[UpcomingData]:
        """List all upcoming items in the database."""
        with Session(self._engine) as session:
            items = list(session.exec(select(UpcomingData)))
        items.sort(key=lambda e: e.date or "", reverse=True)
        return items

    def delete(self, url: str) -> bool:
        """Delete an upcoming item by URL. Returns True if deleted."""
        with Session(self._engine) as session:
            result = session.exec(
                select(UpcomingData).where(UpcomingData.url == url)
            ).first()
            if result is None:
                return False
            session.delete(result)
            session.commit()
            return True

    def delete_by_id(self, id: int) -> bool:
        """Delete an upcoming item by id. Returns True if deleted."""
        with Session(self._engine) as session:
            result = session.get(UpcomingData, id)
            if result is None:
                return False
            session.delete(result)
            session.commit()
            return True
