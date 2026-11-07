"""SQLite backup and restore utilities (dump/load as .sql files)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def backup_db(db_path: str, output: str) -> None:
    """Dump the SQLite database to a .sql file."""
    conn = sqlite3.connect(db_path)
    try:
        with open(output, "w") as f:
            f.writelines(f"{line}\n" for line in conn.iterdump())
    finally:
        conn.close()
    logger.info("Backed up %s to %s", db_path, output)


def restore_db(input: str, db_path: str) -> None:
    """Restore the SQLite database from a .sql file.

    The restore is destructive: existing tables and views in the target
    database are dropped before the dump is applied. This makes restoring over
    a populated database (or re-running a restore) succeed instead of failing
    with ``table ... already exists``.
    """
    with open(input) as f:
        script = f.read()
    conn = sqlite3.connect(db_path)
    try:
        _drop_all(conn)
        conn.executescript(script)
    finally:
        conn.close()
    logger.info("Restored %s from %s", db_path, input)


def _drop_all(conn: sqlite3.Connection) -> None:
    """Drop every user-defined table and view in the database."""
    rows = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for type_, name in rows:
        quoted = name.replace('"', '""')
        conn.execute(f'DROP {type_.upper()} IF EXISTS "{quoted}"')
    conn.commit()
