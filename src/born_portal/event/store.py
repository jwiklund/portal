from __future__ import annotations

import sqlite3
from dataclasses import asdict
from typing import Optional

from born_portal.event.model import EventData


class EventStore:
    """SQLite storage for parsed event data."""

    def __init__(self, db_path: str = "events.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._create_table()
        return self._conn

    def _create_table(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT,
                price TEXT,
                date TEXT,
                ticket INTEGER DEFAULT 0
            )
        """
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def save(self, event: EventData) -> int:
        """Save an event to the database. Returns the row id."""
        conn = self._get_connection()
        cursor = conn.cursor()
        if event.id:
            # Update existing event by id
            cursor.execute(
                """
                UPDATE events SET
                    url = :url,
                    name = :name,
                    description = :description,
                    location = :location,
                    price = :price,
                    date = :date,
                    ticket = :ticket
                WHERE id = :id
            """,
                asdict(event),
            )
            conn.commit()
            # If update affected rows, return the id; otherwise insert new
            if cursor.rowcount > 0:
                return event.id
        # Insert new event (or update by URL if id was not valid)
        cursor.execute(
            """
            INSERT INTO events (url, name, description, location, price, date, ticket)
            VALUES (:url, :name, :description, :location, :price, :date, :ticket)
            ON CONFLICT(url) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                location = excluded.location,
                price = excluded.price,
                date = excluded.date,
                ticket = excluded.ticket
            """,
            asdict(event),
        )
        conn.commit()
        return cursor.lastrowid

    def get(self, url: str) -> Optional[EventData]:
        """Retrieve an event by URL."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE url = ?", (url,))
        row = cursor.fetchone()
        if row:
            return EventData(
                id=row["id"],
                url=row["url"],
                name=row["name"],
                description=row["description"],
                location=row["location"],
                price=row["price"],
                date=row["date"],
                ticket=bool(row["ticket"]),
            )
        return None

    def get_by_id(self, id: int) -> Optional[EventData]:
        """Retrieve an event by id."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?", (id,))
        row = cursor.fetchone()
        if row:
            return EventData(
                id=row["id"],
                url=row["url"],
                name=row["name"],
                description=row["description"],
                location=row["location"],
                price=row["price"],
                date=row["date"],
                ticket=bool(row["ticket"]),
            )
        return None

    def exists(self, url: str) -> bool:
        """Check if an event exists in the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM events WHERE url = ?", (url,))
        return cursor.fetchone() is not None

    def exists_by_id(self, id: int) -> bool:
        """Check if an event exists by id."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM events WHERE id = ?", (id,))
        return cursor.fetchone() is not None

    def get_url_by_id(self, id: int) -> Optional[str]:
        """Get the URL for an event by id."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM events WHERE id = ?", (id,))
        row = cursor.fetchone()
        return row["url"] if row else None

    def list_all(self) -> list[EventData]:
        """List all events in the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events ORDER BY date DESC")
        rows = cursor.fetchall()
        return [
            EventData(
                id=row["id"],
                url=row["url"],
                name=row["name"],
                description=row["description"],
                location=row["location"],
                price=row["price"],
                date=row["date"],
                ticket=bool(row["ticket"]),
            )
            for row in rows
        ]

    def delete(self, url: str) -> bool:
        """Delete an event by URL. Returns True if deleted."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events WHERE url = ?", (url,))
        conn.commit()
        return cursor.rowcount > 0

    def delete_by_id(self, id: int) -> bool:
        """Delete an event by id. Returns True if deleted."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events WHERE id = ?", (id,))
        conn.commit()
        return cursor.rowcount > 0
