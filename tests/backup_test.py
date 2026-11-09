"""Tests for SQLite backup/restore, especially the sessions exclusion."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from born_portal.backup import (
    backup_db,
    default_backup_name,
    latest_backup,
    resolve_backup,
    restore_db,
)


def _seed(path, *, sessions, upcoming):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, data TEXT, expires_at FLOAT);"
        "CREATE TABLE upcoming (id INTEGER PRIMARY KEY, url TEXT, name TEXT);"
    )
    conn.executemany("INSERT INTO sessions VALUES (?, ?, 0.0)", sessions)
    conn.executemany("INSERT INTO upcoming VALUES (?, ?, ?)", upcoming)
    conn.commit()
    conn.close()


def _rows(path, table):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()


def test_default_backup_name_uses_date():
    assert default_backup_name(date(2026, 11, 9)) == "backup-2026-11-09.sql"


def test_latest_backup_picks_newest_dated_file(tmp_path):
    for name in ("backup-2026-11-08.sql", "backup-2026-11-09.sql", "notes.sql"):
        (tmp_path / name).write_text("")

    assert Path(latest_backup(tmp_path)).name == "backup-2026-11-09.sql"


def test_latest_backup_without_files_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        latest_backup(tmp_path)


def test_resolve_backup_defaults_to_latest(tmp_path):
    (tmp_path / "backup-2026-11-08.sql").write_text("")
    (tmp_path / "backup-2026-11-09.sql").write_text("")

    assert resolve_backup(None, tmp_path) == str(tmp_path / "backup-2026-11-09.sql")


def test_resolve_backup_date_maps_to_dated_file(tmp_path):
    assert resolve_backup("2026-11-09", tmp_path) == str(
        tmp_path / "backup-2026-11-09.sql"
    )


def test_resolve_backup_accepts_explicit_path(tmp_path):
    assert resolve_backup("custom.sql", tmp_path) == "custom.sql"


def test_resolve_backup_rejects_invalid_date(tmp_path):
    with pytest.raises(ValueError):
        resolve_backup("2026-13-01", tmp_path)


def test_backup_omits_sessions(tmp_path):
    db = tmp_path / "portal.db"
    out = tmp_path / "backup.sql"
    _seed(
        db,
        sessions=[("sid1", '{"user": "a@b", "spotify_refresh_token": "SECRET"}')],
        upcoming=[(1, "http://x", "Party")],
    )

    backup_db(str(db), str(out))

    dump = out.read_text()
    assert "sessions" not in dump
    assert "Party" in dump
    # No session payload (identity or token) leaks into the dump.
    assert "a@b" not in dump
    assert "SECRET" not in dump


def test_restore_preserves_sessions_and_replaces_data(tmp_path):
    db = tmp_path / "portal.db"
    out = tmp_path / "backup.sql"
    _seed(
        db,
        sessions=[("sid1", '{"user": "a@b"}')],
        upcoming=[(1, "http://x", "Old")],
    )
    backup_db(str(db), str(out))

    # Mutate the live database after the backup: a newer session and changed data.
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO sessions VALUES ('sid2', '{}', 0.0)")
    conn.execute("UPDATE upcoming SET name = 'New' WHERE id = 1")
    conn.commit()
    conn.close()

    restore_db(str(out), str(db))

    # Sessions are preserved; everything else is restored from the dump.
    session_ids = {row[0] for row in _rows(db, "sessions")}
    assert session_ids == {"sid1", "sid2"}
    assert _rows(db, "upcoming") == [(1, "http://x", "Old")]


def test_restore_into_empty_database_succeeds(tmp_path):
    source = tmp_path / "source.db"
    out = tmp_path / "backup.sql"
    _seed(source, sessions=[], upcoming=[(1, "http://x", "Party")])
    backup_db(str(source), str(out))

    # A brand-new target DB has no tables at all; restore must still work.
    target = tmp_path / "target.db"
    sqlite3.connect(target).close()

    restore_db(str(out), str(target))

    assert _rows(target, "upcoming") == [(1, "http://x", "Party")]
