import sqlite3

from born_portal.migrate import migrate_db

_ARTISTS_TABLE = """
    CREATE TABLE artists (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        spotify_uri TEXT
    );
"""


def _legacy_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            name TEXT,
            description TEXT,
            location TEXT,
            price TEXT,
            date TEXT,
            ticket BOOLEAN
        );
        CREATE TABLE festivals (
            id INTEGER PRIMARY KEY,
            name TEXT,
            start_date TEXT,
            end_date TEXT,
            location TEXT,
            description TEXT,
            album_uri TEXT
        );
        """
        + _ARTISTS_TABLE
        + """
        CREATE TABLE festival_artists (
            festival_id INTEGER,
            artist_id INTEGER,
            position INTEGER,
            PRIMARY KEY (festival_id, artist_id)
        );
        INSERT INTO events VALUES
            (1, 'https://a', 'Party', 'desc', 'Stockholm', '100kr', '2026-01-01', 1);
        INSERT INTO festivals VALUES
            (1, 'Way Out West', '2026-08-12', '2026-08-14', 'Gothenburg',
             'A festival.', 'https://photos/x');
        INSERT INTO artists VALUES (1, 'Artist One', 'spotify:artist:1');
        INSERT INTO festival_artists VALUES (1, 1, 0);
        """
    )
    conn.commit()
    conn.close()


def _intermediate_db(path):
    """A database already migrated to the intermediate previous tables."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE previous (
            id INTEGER PRIMARY KEY,
            name TEXT,
            start_date TEXT,
            end_date TEXT,
            location TEXT,
            description TEXT,
            album_uri TEXT
        );
        """
        + _ARTISTS_TABLE
        + """
        CREATE TABLE previous_artists (
            previous_id INTEGER,
            artist_id INTEGER,
            position INTEGER,
            PRIMARY KEY (previous_id, artist_id)
        );
        INSERT INTO previous VALUES
            (1, 'Way Out West', '2026-08-12', '2026-08-14', 'Gothenburg',
             'A festival.', 'https://photos/x');
        INSERT INTO artists VALUES (1, 'Artist One', 'spotify:artist:1');
        INSERT INTO previous_artists VALUES (1, 1, 0);
        """
    )
    conn.commit()
    conn.close()


def _tables(conn):
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def test_migrate_copies_rows_and_keeps_legacy_tables(tmp_path):
    db = tmp_path / "legacy.db"
    _legacy_db(db)

    migrate_db(str(db))

    conn = sqlite3.connect(db)
    try:
        tables = _tables(conn)
        # Legacy tables are kept as a backup.
        assert {"events", "festivals", "festival_artists"} <= tables
        assert {"upcoming", "past", "past_artists"} <= tables

        assert conn.execute("SELECT COUNT(*) FROM upcoming").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM past").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM past_artists").fetchone()[0] == 1

        row = conn.execute("SELECT name, ticket FROM upcoming WHERE id=1").fetchone()
        assert row == ("Party", 1)

        link = conn.execute(
            "SELECT past_id, artist_id, position FROM past_artists"
        ).fetchone()
        assert link == (1, 1, 0)
    finally:
        conn.close()


def test_migrate_from_intermediate_previous_tables(tmp_path):
    db = tmp_path / "intermediate.db"
    _intermediate_db(db)

    migrate_db(str(db))

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM past").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM past_artists").fetchone()[0] == 1
        row = conn.execute("SELECT name FROM past WHERE id=1").fetchone()
        assert row == ("Way Out West",)
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path):
    db = tmp_path / "legacy.db"
    _legacy_db(db)

    migrate_db(str(db))
    migrate_db(str(db))

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM upcoming").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM past").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM past_artists").fetchone()[0] == 1
    finally:
        conn.close()


def test_migrate_without_legacy_tables_creates_new_schema(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()

    migrate_db(str(db))

    conn = sqlite3.connect(db)
    try:
        assert {"upcoming", "past", "past_artists"} <= _tables(conn)
        assert conn.execute("SELECT COUNT(*) FROM upcoming").fetchone()[0] == 0
    finally:
        conn.close()
