"""Migrate legacy SQLite tables to the renamed upcoming/past tables.

The portal used to store upcoming items in an ``events`` table and past items
in a ``festivals`` table (with a ``festival_artists`` link table). These were
renamed to ``upcoming``, ``past`` and ``past_artists``. An intermediate rename
used ``previous``/``previous_artists``; those tables are migrated too.

This migration is idempotent and non-destructive:

* the new tables are created if they do not exist yet;
* rows are copied from the legacy tables with ``INSERT OR IGNORE`` so
  re-running never duplicates data and never overwrites newer edits;
* the legacy tables are left in place as a backup.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# (new table, legacy table, {new_column: legacy_column})
_TABLE_MIGRATIONS: list[tuple[str, str, dict[str, str]]] = [
    (
        "upcoming",
        "events",
        {
            "id": "id",
            "url": "url",
            "name": "name",
            "description": "description",
            "location": "location",
            "price": "price",
            "date": "date",
            "ticket": "ticket",
        },
    ),
    (
        "past",
        "festivals",
        {
            "id": "id",
            "name": "name",
            "start_date": "start_date",
            "end_date": "end_date",
            "location": "location",
            "description": "description",
            "album_uri": "album_uri",
        },
    ),
    (
        "past_artists",
        "festival_artists",
        {
            "past_id": "festival_id",
            "artist_id": "artist_id",
            "position": "position",
        },
    ),
    # Intermediate rename (festivals -> previous -> past).
    (
        "past",
        "previous",
        {
            "id": "id",
            "name": "name",
            "start_date": "start_date",
            "end_date": "end_date",
            "location": "location",
            "description": "description",
            "album_uri": "album_uri",
        },
    ),
    (
        "past_artists",
        "previous_artists",
        {
            "past_id": "previous_id",
            "artist_id": "artist_id",
            "position": "position",
        },
    ),
]


def _ensure_new_tables(db_path: str) -> None:
    """Create the renamed tables (and their dependencies) if missing."""
    # Importing the model modules registers their tables on SQLModel.metadata.
    from sqlmodel import SQLModel, create_engine

    from born_portal.past import model as _past_model  # noqa: F401
    from born_portal.upcoming import model as _upcoming_model  # noqa: F401

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        engine.dispose()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def migrate_db(db_path: str = "events.db") -> None:
    """Copy legacy table data into the renamed tables. Safe to re-run."""
    _ensure_new_tables(db_path)

    conn = sqlite3.connect(db_path)
    try:
        for new_table, old_table, columns in _TABLE_MIGRATIONS:
            if not _table_exists(conn, old_table):
                logger.info(
                    "Skipping %s: legacy table %s not found", new_table, old_table
                )
                continue

            before = conn.execute(f"SELECT COUNT(*) FROM {new_table}").fetchone()[0]
            new_cols = ", ".join(columns)
            old_cols = ", ".join(columns.values())
            conn.execute(
                f"INSERT OR IGNORE INTO {new_table} ({new_cols}) "
                f"SELECT {old_cols} FROM {old_table}"
            )
            conn.commit()
            after = conn.execute(f"SELECT COUNT(*) FROM {new_table}").fetchone()[0]
            logger.info(
                "Migrated %d rows from %s to %s",
                after - before,
                old_table,
                new_table,
            )
    finally:
        conn.close()

    logger.info("Migration complete. Legacy tables were left intact as a backup.")
