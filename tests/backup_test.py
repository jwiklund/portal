"""Tests for SQLite backup/restore, especially the excluded tables."""

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

_EPHEMERAL_TABLES = ("sessions", "push_subscriptions", "error_log")


def _seed(path, *, sessions, upcoming, push=(), errors=()):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, data TEXT, expires_at FLOAT);"
        "CREATE TABLE upcoming (id INTEGER PRIMARY KEY, url TEXT, name TEXT);"
        "CREATE TABLE push_subscriptions ("
        " id INTEGER PRIMARY KEY, endpoint TEXT UNIQUE, auth TEXT);"
        'CREATE INDEX "ix_push_subscriptions_endpoint"'
        ' ON "push_subscriptions" ("endpoint");'
        "CREATE TABLE error_log ("
        " id INTEGER PRIMARY KEY, created_at TEXT, message TEXT);"
        'CREATE INDEX "ix_error_log_created_at" ON "error_log" ("created_at");'
    )
    conn.executemany("INSERT INTO sessions VALUES (?, ?, 0.0)", sessions)
    conn.executemany("INSERT INTO upcoming VALUES (?, ?, ?)", upcoming)
    conn.executemany("INSERT INTO push_subscriptions VALUES (?, ?, ?)", push)
    conn.executemany("INSERT INTO error_log VALUES (?, ?, ?)", errors)
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


def test_backup_omits_ephemeral_tables(tmp_path):
    db = tmp_path / "portal.db"
    out = tmp_path / "backup.sql"
    _seed(
        db,
        sessions=[("sid1", '{"user": "a@b", "spotify_refresh_token": "SECRET"}')],
        upcoming=[(1, "http://x", "Party")],
        push=[(1, "https://push.example/abc", "PUSHKEY")],
        errors=[(1, "2026-11-09", "BOOM")],
    )

    backup_db(str(db), str(out))

    dump = out.read_text()
    assert "Party" in dump
    for table in _EPHEMERAL_TABLES:
        assert f'CREATE TABLE "{table}"' not in dump
        assert f"CREATE TABLE {table}" not in dump
    # No session payload, push endpoint or error record leaks into the dump.
    assert "a@b" not in dump
    assert "SECRET" not in dump
    assert "push.example" not in dump
    assert "BOOM" not in dump


def test_restore_preserves_ephemeral_tables_and_replaces_data(tmp_path):
    db = tmp_path / "portal.db"
    out = tmp_path / "backup.sql"
    _seed(
        db,
        sessions=[("sid1", '{"user": "a@b"}')],
        upcoming=[(1, "http://x", "Old")],
    )
    backup_db(str(db), str(out))

    # Mutate the live database after the backup: newer sessions, a new push
    # subscription, a new error and changed data.
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO sessions VALUES ('sid2', '{}', 0.0)")
    conn.execute("INSERT INTO push_subscriptions VALUES (1, 'https://p/1', 'KEY')")
    conn.execute("INSERT INTO error_log VALUES (1, '2026-11-09', 'BOOM')")
    conn.execute("UPDATE upcoming SET name = 'New' WHERE id = 1")
    conn.commit()
    conn.close()

    restore_db(str(out), str(db))

    # Ephemeral tables are preserved; everything else is restored from the dump.
    session_ids = {row[0] for row in _rows(db, "sessions")}
    assert session_ids == {"sid1", "sid2"}
    assert _rows(db, "push_subscriptions") == [(1, "https://p/1", "KEY")]
    assert _rows(db, "error_log") == [(1, "2026-11-09", "BOOM")]
    assert _rows(db, "upcoming") == [(1, "http://x", "Old")]


def test_restore_ignores_ephemeral_tables_in_old_backup(tmp_path):
    db = tmp_path / "portal.db"
    out = tmp_path / "old-backup.sql"
    _seed(db, sessions=[], upcoming=[])
    out.write_text(
        'CREATE TABLE "upcoming" (id INTEGER PRIMARY KEY, url TEXT, name TEXT);\n'
        "INSERT INTO \"upcoming\" VALUES(1,'http://x','Party');\n"
        'CREATE TABLE "push_subscriptions" (id INTEGER PRIMARY KEY, endpoint TEXT);\n'
        "INSERT INTO \"push_subscriptions\" VALUES(1,'https://old/push');\n"
        'CREATE TABLE "error_log" (id INTEGER PRIMARY KEY, message TEXT);\n'
        "INSERT INTO \"error_log\" VALUES(1,'OLD BOOM');\n"
    )

    restore_db(str(out), str(db))

    assert _rows(db, "upcoming") == [(1, "http://x", "Party")]
    # The old dump must not overwrite or fail on the live ephemeral tables.
    assert _rows(db, "push_subscriptions") == []
    assert _rows(db, "error_log") == []


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
