import argparse
import asyncio
import json
import logging

from blacksheep import Application, Request
from sqlalchemy import event
from sqlmodel import SQLModel, create_engine

from born_portal import (
    auth,
    backup,
    errors,
    past,
    playlist,
    podcast,
    pwa,
    routes,
    show,
    upcoming,
)
from born_portal.auth import configure as configure_auth
from born_portal.core import DB_URL, ENV, SECRET_KEY
from born_portal.sessions import SqliteSessionStore

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

app = Application()

# Google Cast SDK script, Google-hosted avatars/album photos, and inline
# scripts/styles used across templates.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://www.gstatic.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://*.googleusercontent.com https://*.scdn.co; "
    "media-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    # Chrome/Safari enforce form-action across redirects, so the Spotify
    # authorize redirect after the create-playlist form POST must be allowed.
    "form-action 'self' https://accounts.spotify.com; "
    "frame-ancestors 'none'"
)

_SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


async def security_headers_middleware(request: Request, handler):
    response = await handler(request)
    for name, value in _SECURITY_HEADERS.items():
        response.set_header(name.encode(), value.encode())
    return response


engine = create_engine(
    DB_URL,
    connect_args={
        "timeout": 5.0,
        "check_same_thread": False,
    },
)
SQLModel.metadata.create_all(engine)


@event.listens_for(engine, "connect")
def configure_sqlite(dbapi_connection, connection_record):

    cursor = dbapi_connection.cursor()

    # Enforce foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # Configure durability
    cursor.execute("PRAGMA synchronous = NORMAL")

    # Configure lock timeout
    cursor.execute("PRAGMA busy_timeout = 5000")

    # Configure cache
    cursor.execute("PRAGMA cache_size = -64000")

    # Store temporary tables in memory
    cursor.execute("PRAGMA temp_store = MEMORY")

    cursor.close()


# Session cookies: 7-day expiry, SameSite=Lax, Secure outside development.
# Lax is deliberate: the OAuth callback (/auth/callback) arrives via a
# cross-site top-level navigation, so a Strict cookie would not be sent
# there and the oauth_state check would fail. Lax still blocks all
# cross-site POSTs, and every mutating route in this app is a POST.
#
# The cookie only carries an opaque, signed session id; the payload (user
# identity, OAuth state, Spotify tokens) lives server-side in the sessions
# table, so a stolen cookie discloses no secrets.
_SESSION_MAX_AGE = 7 * 24 * 3600

app.use_sessions(
    SqliteSessionStore(
        engine,
        SECRET_KEY,
        session_max_age=_SESSION_MAX_AGE,
        secure=ENV != "development",
    )
)
app.middlewares.append(security_headers_middleware)
configure_auth(app)

auth.register_routes(app)
errors.register_routes(app, engine)
routes.register_routes(app)
upcoming.register_routes(app, engine)
past.register_routes(app, engine)
playlist.register_routes(app)
podcast.register_routes(app)
show.register_routes(app)
pwa.register_routes(app)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main",
        description="Start the portal or fetch and parse event data from a URL.",
    )
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Start the portal web server")
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind the portal server",
    )

    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch an event URL and parse event data"
    )
    fetch_parser.add_argument("url", help="URL to fetch and parse")
    fetch_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    backup_parser = subparsers.add_parser(
        "backup", help="Back up the SQLite database to a .sql file"
    )
    backup_parser.add_argument(
        "output", help="Path to the backup file (e.g. portal-backup.sql)"
    )
    backup_parser.add_argument(
        "--db", default="portal.db", help="Path to the SQLite database"
    )

    restore_parser = subparsers.add_parser(
        "restore", help="Restore the SQLite database from a .sql file"
    )
    restore_parser.add_argument(
        "input", help="Path to the backup file (e.g. portal-backup.sql)"
    )
    restore_parser.add_argument(
        "--db", default="portal.db", help="Path to the SQLite database"
    )

    potential_parser = subparsers.add_parser(
        "potential", help="List events from the supported event sources"
    )
    potential_parser.add_argument(
        "source",
        nargs="?",
        help="Only list a single source (e.g. ra, raveoclock)",
    )
    potential_parser.add_argument(
        "--json", action="store_true", help="Output JSON instead of text"
    )
    potential_parser.add_argument(
        "--refresh", action="store_true", help="Bypass the in-memory cache"
    )
    potential_parser.add_argument(
        "--duplicates",
        action="store_true",
        help="Group similar events and show merge options",
    )

    subparsers.add_parser(
        "init-db", help="Initialize the SQLite database with WAL mode"
    )

    args = parser.parse_args(argv)

    if args.command == "fetch":
        upcoming_data = asyncio.run(upcoming.parse(args.url, debug=args.debug))
        print(json.dumps(upcoming_data.model_dump(), indent=2, ensure_ascii=False))
        return

    if args.command == "backup":
        backup.backup_db(args.db, args.output)
        return

    if args.command == "restore":
        backup.restore_db(args.input, args.db)
        return

    if args.command == "potential":
        _list_potential(args.source, args.json, args.refresh, args.duplicates)
        return

    if args.command == "init-db":
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode = WAL")
        return

    parser.print_help()


def _list_potential(
    source_key: str | None,
    as_json: bool,
    refresh: bool,
    duplicates: bool = False,
) -> None:
    from born_portal.utils.date_range import upcoming_weekend

    sources = [
        source
        for source in upcoming.sources.all_sources()
        if source_key is None or source.key == source_key
    ]
    if not sources:
        print(f"Unknown source: {source_key}")
        print(
            "Supported sources: "
            + ", ".join(s.key for s in upcoming.sources.all_sources())
        )
        return

    start, end = upcoming_weekend()

    async def fetch_all():
        results = []
        for source in sources:
            try:
                events = await upcoming.potential.source_events(
                    source, start, end, refresh=refresh
                )
                results.append((source, events, None))
            except Exception as e:  # noqa: BLE001
                results.append((source, [], str(e)))
        return results

    results = asyncio.run(fetch_all())

    if duplicates:
        source_results = [
            upcoming.potential.SourceResult(source=source, events=events, error=error)
            for source, events, error in results
        ]
        clusters = upcoming.potential.cluster_results(source_results)
        if as_json:
            payload = [
                {
                    "primary": {
                        "source": cluster.primary.source.key,
                        "name": cluster.primary.source.name,
                        "event": cluster.primary.event.model_dump(),
                    },
                    "alternatives": [
                        {
                            "source": alternative.source.key,
                            "name": alternative.source.name,
                            "event": alternative.event.model_dump(),
                        }
                        for alternative in cluster.alternatives
                    ],
                }
                for cluster in clusters
            ]
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        print(f"Merged events — {start} to {end}")
        for cluster in clusters:
            primary = cluster.primary
            location = f"  {primary.event.location}" if primary.event.location else ""
            print(
                f"  {cluster.date or 'TBD'}  {primary.event.name}"
                f"  [{primary.source.name}]{location}"
            )
            for alternative in cluster.alternatives:
                print(
                    f"      also: {alternative.source.name} — "
                    f"{alternative.event.name}"
                )
        return

    if as_json:
        payload = [
            {
                "source": source.key,
                "name": source.name,
                "error": error,
                "events": [event.model_dump() for event in events],
            }
            for source, events, error in results
        ]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    for source, events, error in results:
        print(f"{source.name} ({source.key}) — {start} to {end}")
        if error:
            print(f"  error: {error}")
            continue
        if not events:
            print("  no events")
            continue
        for e in events:
            location = f"  {e.location}" if e.location else ""
            print(f"  {e.date or 'TBD'}  {e.name}{location}")


if __name__ == "__main__":
    main()
