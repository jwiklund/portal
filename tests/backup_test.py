"""Tests for SQLite backup/restore, especially the sessions exclusion."""

import sqlite3

from born_portal.backup import backup_db, restore_db


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
