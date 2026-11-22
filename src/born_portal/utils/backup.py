"""SQLite backup and restore utilities (dump/load as .sql files)."""

import logging
import re
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKUP_NAME = re.compile(r"^backup-(\d{4}-\d{2}-\d{2})\.sql$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def default_backup_name(today: date | None = None) -> str:
    """Return the default backup filename, e.g. ``backup-2026-11-09.sql``."""
    current = today or datetime.now(UTC).astimezone().date()
    return f"backup-{current.isoformat()}.sql"


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


# Tables excluded from backups. These hold machine-local, ephemeral data:
# sessions (short-lived OAuth tokens), push subscriptions (per-browser
# endpoints and keys) and the error log (transient diagnostics). They are
# neither dumped nor dropped, so a restore leaves the current state untouched
# and no secrets or stale endpoints end up in a backup file.
_EXCLUDED_TABLES = ("sessions", "push_subscriptions", "error_log")

_TABLE_STATEMENT = re.compile(
    r"^(?:CREATE\s+TABLE|INSERT\s+INTO)"
    r"\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r'(?:"(?P<quoted>[^"]+)"|(?P<plain>[^\s(]+))',
    re.IGNORECASE,
)

_INDEX_STATEMENT = re.compile(
    r"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r'(?:"[^"]+"|[^\s(]+)\s+ON\s+'
    r'(?:"(?P<quoted>[^"]+)"|(?P<plain>[^\s(]+))',
    re.IGNORECASE,
)


def _statement_table(statement: str) -> str | None:
    """Return the table a dump statement targets, if it is one we track."""
    for pattern in (_INDEX_STATEMENT, _TABLE_STATEMENT):
        match = pattern.match(statement)
        if match is not None:
            return match.group("quoted") or match.group("plain")
    return None


def _is_excluded(statement: str) -> bool:
    return _statement_table(statement) in _EXCLUDED_TABLES


def backup_db(db_path: str, output: str) -> None:
    """Dump the SQLite database to a .sql file.

    Session, push subscription and error log data is omitted, so login state,
    OAuth tokens, browser push endpoints and stale diagnostics never end up in
    a backup file.
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

    The restore is destructive for everything except the excluded tables
    (sessions, push subscriptions and the error log): existing tables and views
    are dropped before the dump is applied, but those tables are left in place
    so active logins, push subscriptions and the current error log survive a
    restore. Dropping the other tables also makes restoring over a populated
    database (or re-running a restore) succeed instead of failing with
    ``table ... already exists``.

    Statements for the excluded tables are skipped as well, so older backups
    that still contain them cannot overwrite the live data.
    """
    with open(input) as f:
        script = f.read()
    statements = [
        statement
        for statement in _split_statements(script)
        if not _is_excluded(statement)
    ]
    conn = sqlite3.connect(db_path)
    try:
        _drop_all(conn)
        conn.executescript("\n".join(statements))
    finally:
        conn.close()
    logger.info("Restored %s from %s", db_path, input)


def _split_statements(script: str) -> list[str]:
    """Split a dump script into complete SQL statements."""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements


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
