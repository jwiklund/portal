import argparse
import asyncio
import json
import logging

from blacksheep import Application

from born_portal import auth, backup, event, festival, podcast, pwa, routes, show
from born_portal.auth import configure as configure_auth
from born_portal.core import SECRET_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

app = Application()

app.use_sessions(SECRET_KEY)
configure_auth(app)

auth.register_routes(app)
routes.register_routes(app)
event.register_routes(app)
festival.register_routes(app)
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

    parse_parser = subparsers.add_parser("parse", help="Parse event example")
    parse_parser.add_argument("--file", help="File to parse", default="biletto.html")

    backup_parser = subparsers.add_parser(
        "backup", help="Back up the SQLite database to a .sql file"
    )
    backup_parser.add_argument(
        "output", help="Path to the backup file (e.g. events-backup.sql)"
    )
    backup_parser.add_argument(
        "--db", default="events.db", help="Path to the SQLite database"
    )

    restore_parser = subparsers.add_parser(
        "restore", help="Restore the SQLite database from a .sql file"
    )
    restore_parser.add_argument(
        "input", help="Path to the backup file (e.g. events-backup.sql)"
    )
    restore_parser.add_argument(
        "--db", default="events.db", help="Path to the SQLite database"
    )

    args = parser.parse_args(argv)

    if args.command == "fetch":
        event_data = asyncio.run(event.parse(args.url))
        print(json.dumps(event_data.model_dump(), indent=2, ensure_ascii=False))
        return

    if args.command == "parse":
        with open(args.file) as r:
            event_data = event.parse_biletto(r.read())
        print(json.dumps(event_data.model_dump(), indent=2, ensure_ascii=False))
        return

    if args.command == "backup":
        backup.backup_db(args.db, args.output)
        return

    if args.command == "restore":
        backup.restore_db(args.input, args.db)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
