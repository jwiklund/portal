"""SQLite backup and restore utilities (dump/load as .sql files)."""

import logging
import re
import sqlite3
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKUP_NAME = re.compile(r"^backup-(\d{4}-\d{2}-\d{2})\.sql$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def default_backup_name(today: date | None = None) -> str:
    """Return the default backup filename, e.g. ``backup-2026-11-09.sql``."""
    return f"backup-{(today or date.today()).isoformat()}.sql"


def latest_backup(directory: str | Path = ".") -> str:
    """Return the path of the newest ``backup-YYYY-MM-DD.sql`` in a directory."""
    files = sorted(
        path
        for path in Path(directory).iterdir()
        if path.is_file() and _BACKUP_NAME.match(path.name)
    )
    if not files:
        raise FileNotFoundError(
            f"No backup-YYYY-MM-DD.sql files found in {Path(directory).resolve()}"
        )
    return str(files[-1])


def resolve_backup(value: str | None, directory: str | Path = ".") -> str:
    """Resolve a restore argument to a backup file path.

    ``None`` selects the latest dated backup, a plain date like ``2026-11-09``
    maps to ``backup-2026-11-09.sql``, and anything else is treated as a path.
    """
    if value is None:
        return latest_backup(directory)
    if _DATE_ONLY.match(value):
        date.fromisoformat(value)  # Reject impossible dates such as 2026-13-01.
        return str(Path(directory) / f"backup-{value}.sql")
    return value

# Tables excluded from backups. Sessions hold short-lived data (including OAuth
# tokens); they are neither dumped nor dropped, so a restore leaves the current
# logins untouched and no tokens end up in a backup file.
_EXCLUDED_TABLES = ("sessions",)

_TABLE_STATEMENT = re.compile(
    r"^(?:CREATE\s+TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX|INSERT\s+INTO)"
    r"\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r'(?:"(?P<quoted>[^"]+)"|(?P<plain>[^\s(]+))',
    re.IGNORECASE,
)


def _statement_table(statement: str) -> str | None:
    """Return the table a dump statement targets, if it is one we track."""
    match = _TABLE_STATEMENT.match(statement)
    if match is None:
        return None
    return match.group("quoted") or match.group("plain")


def _is_excluded(statement: str) -> bool:
    return _statement_table(statement) in _EXCLUDED_TABLES


def backup_db(db_path: str, output: str) -> None:
    """Dump the SQLite database to a .sql file.

    Session data is omitted, so login state and OAuth tokens never end up in a
    backup file.
    """
    conn = sqlite3.connect(db_path)
    try:
        with open(output, "w") as f:
            for statement in conn.iterdump():
                if _is_excluded(statement):
                    continue
                f.write(f"{statement}\n")
    finally:
        conn.close()
    logger.info("Backed up %s to %s", db_path, output)


def restore_db(input: str, db_path: str) -> None:
    """Restore the SQLite database from a .sql file.

    The restore is destructive for everything except sessions: existing tables
    and views are dropped before the dump is applied, but the ``sessions``
    table is left in place so active logins survive a restore. Dropping the
    other tables also makes restoring over a populated database (or re-running
    a restore) succeed instead of failing with ``table ... already exists``.
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
    """Drop every user-defined table and view except the excluded ones."""
    rows = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for type_, name in rows:
        if name in _EXCLUDED_TABLES:
            continue
        quoted = name.replace('"', '""')
        conn.execute(f'DROP {type_.upper()} IF EXISTS "{quoted}"')
    conn.commit()
