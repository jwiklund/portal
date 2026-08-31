from __future__ import annotations

from sqlmodel import Session, select

from born_portal.event.model import EventData


class EventStore:
    """SQLite storage for parsed event data."""

    def __init__(self, engine):
        self._engine = engine

    def save(self, event: EventData) -> int:
        """Save an event to the database. Returns the row id."""
        with Session(self._engine) as session:
            if event.id is not None:
                existing = session.get(EventData, event.id)
                if existing is not None:
                    existing.url = event.url
                    existing.name = event.name
                    existing.description = event.description
                    existing.location = event.location
                    existing.price = event.price
                    existing.date = event.date
                    existing.ticket = event.ticket
                    session.add(existing)
                    session.commit()
                    session.refresh(existing)
                    assert existing.id is not None
                    return existing.id

            # Insert new event, or update the row with the same URL.
            existing = session.exec(
                select(EventData).where(EventData.url == event.url)
            ).first()
            if existing is None:
                existing = EventData(
                    url=event.url,
                    name=event.name,
                    description=event.description,
                    location=event.location,
                    price=event.price,
                    date=event.date,
                    ticket=event.ticket,
                )
                session.add(existing)
            else:
                existing.name = event.name
                existing.description = event.description
                existing.location = event.location
                existing.price = event.price
                existing.date = event.date
                existing.ticket = event.ticket
                session.add(existing)
            session.commit()
            session.refresh(existing)
            assert existing.id is not None
            return existing.id

    def get(self, url: str) -> EventData | None:
        """Retrieve an event by URL."""
        with Session(self._engine) as session:
            return session.exec(select(EventData).where(EventData.url == url)).first()

    def get_by_id(self, id: int) -> EventData | None:
        """Retrieve an event by id."""
        with Session(self._engine) as session:
            return session.get(EventData, id)

    def exists(self, url: str) -> bool:
        """Check if an event exists in the database."""
        with Session(self._engine) as session:
            return (
                session.exec(select(EventData.id).where(EventData.url == url)).first()
                is not None
            )

    def exists_by_id(self, id: int) -> bool:
        """Check if an event exists by id."""
        with Session(self._engine) as session:
            return session.get(EventData, id) is not None

    def get_url_by_id(self, id: int) -> str | None:
        """Get the URL for an event by id."""
        with Session(self._engine) as session:
            return session.exec(select(EventData.url).where(EventData.id == id)).first()

    def list_all(self) -> list[EventData]:
        """List all events in the database."""
        with Session(self._engine) as session:
            events = list(session.exec(select(EventData)))
        events.sort(key=lambda e: e.date or "", reverse=True)
        return events

    def delete(self, url: str) -> bool:
        """Delete an event by URL. Returns True if deleted."""
        with Session(self._engine) as session:
            result = session.exec(select(EventData).where(EventData.url == url)).first()
            if result is None:
                return False
            session.delete(result)
            session.commit()
            return True

    def delete_by_id(self, id: int) -> bool:
        """Delete an event by id. Returns True if deleted."""
        with Session(self._engine) as session:
            result = session.get(EventData, id)
            if result is None:
                return False
            session.delete(result)
            session.commit()
            return True
