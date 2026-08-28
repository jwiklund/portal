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
    """Restore the SQLite database from a .sql file."""
    with open(input) as f:
        script = f.read()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(script)
    finally:
        conn.close()
    logger.info("Restored %s from %s", db_path, input)
