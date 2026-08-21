from __future__ import annotations

import sqlite3
from typing import Optional

from born_portal.festival.model import ArtistData, FestivalData


class FestivalStore:
    """SQLite storage for festivals and their artists."""

    def __init__(self, db_path: str = "events.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        conn = self._conn
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            self._conn = conn
        return conn

    @staticmethod
    def _create_tables(conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS festivals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                location TEXT,
                description TEXT NOT NULL DEFAULT '',
                album_uri TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS artists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                spotify_uri TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS festival_artists (
                festival_id INTEGER NOT NULL REFERENCES festivals(id) ON DELETE CASCADE,
                artist_id INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (festival_id, artist_id)
            )
        """
        )
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def save(self, festival: FestivalData) -> int:
        """Save a festival with its artist list. Returns the row id."""
        conn = self._get_connection()
        cursor = conn.cursor()
        params = {
            "name": festival.name,
            "start_date": festival.start_date,
            "end_date": festival.end_date,
            "location": festival.location,
            "description": festival.description,
            "album_uri": festival.album_uri,
        }
        if festival.id:
            cursor.execute(
                """
                UPDATE festivals SET
                    name = :name,
                    start_date = :start_date,
                    end_date = :end_date,
                    location = :location,
                    description = :description,
                    album_uri = :album_uri
                WHERE id = :id
            """,
                params | {"id": festival.id},
            )
            festival_id = festival.id
        else:
            cursor.execute(
                """
                INSERT INTO festivals (name, start_date, end_date, location, description, album_uri)
                VALUES (:name, :start_date, :end_date, :location, :description, :album_uri)
            """,
                params,
            )
            festival_id = cursor.lastrowid

        # Replace the artist list
        cursor.execute(
            "DELETE FROM festival_artists WHERE festival_id = ?", (festival_id,)
        )
        for position, artist in enumerate(festival.artists):
            if not artist.name.strip():
                continue
            artist_id = self._upsert_artist(cursor, artist)
            cursor.execute(
                """
                INSERT OR IGNORE INTO festival_artists (festival_id, artist_id, position)
                VALUES (?, ?, ?)
            """,
                (festival_id, artist_id, position),
            )
        conn.commit()
        assert festival_id is not None
        return festival_id

    @staticmethod
    def _upsert_artist(cursor: sqlite3.Cursor, artist: ArtistData) -> int:
        cursor.execute(
            """
            INSERT INTO artists (name, spotify_uri) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET spotify_uri = excluded.spotify_uri
            RETURNING id
        """,
            (artist.name.strip(), artist.spotify_uri),
        )
        row = cursor.fetchone()
        assert row is not None
        return row["id"]

    def get_by_id(self, id: int) -> Optional[FestivalData]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM festivals WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return None
        return FestivalData(
            id=row["id"],
            name=row["name"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            location=row["location"],
            description=row["description"],
            album_uri=row["album_uri"],
            artists=self._artists_for(row["id"]),
        )

    def list_all(self) -> list[FestivalData]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM festivals ORDER BY start_date IS NULL, start_date DESC"
        )
        rows = cursor.fetchall()
        return [
            FestivalData(
                id=row["id"],
                name=row["name"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                location=row["location"],
                description=row["description"],
                album_uri=row["album_uri"],
                artists=self._artists_for(row["id"]),
            )
            for row in rows
        ]

    def _artists_for(self, festival_id: int) -> list[ArtistData]:
        cursor = self._get_connection().cursor()
        cursor.execute(
            """
            SELECT a.id, a.name, a.spotify_uri FROM artists a
            JOIN festival_artists fa ON fa.artist_id = a.id
            WHERE fa.festival_id = ?
            ORDER BY fa.position
        """,
            (festival_id,),
        )
        return [
            ArtistData(id=r["id"], name=r["name"], spotify_uri=r["spotify_uri"])
            for r in cursor.fetchall()
        ]

    def known_album_uris(self) -> list[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT album_uri FROM festivals "
            "WHERE album_uri IS NOT NULL AND album_uri != ''"
        )
        return [r["album_uri"] for r in cursor.fetchall()]

    def delete(self, id: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM festivals WHERE id = ?", (id,))
        conn.commit()
        return cursor.rowcount > 0
