import argparse
import asyncio
import json
import logging

from blacksheep import Application, Request
from blacksheep.cookies import Cookie, CookieSameSiteMode
from blacksheep.sessions.cookies import CookieSessionStore
from sqlmodel import SQLModel, create_engine

from born_portal import auth, backup, event, festival, podcast, pwa, routes, show
from born_portal.auth import configure as configure_auth
from born_portal.core import DB_URL, ENV, SECRET_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

app = Application()

# Session cookies: 7-day expiry, SameSite=Lax, Secure outside development.
_SESSION_MAX_AGE = 7 * 24 * 3600

# Google Cast SDK script, Google-hosted avatars/album photos, and inline
# scripts/styles used across templates.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://www.gstatic.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://*.googleusercontent.com; "
    "media-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
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


class HardenedCookieSessionStore(CookieSessionStore):
    def __init__(self, *args, secure: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._secure = secure

    def _prepare_cookie(self, value: str) -> Cookie:
        cookie = super()._prepare_cookie(value)
        cookie.secure = self._secure
        cookie.same_site = CookieSameSiteMode.STRICT
        return cookie


app.use_sessions(
    HardenedCookieSessionStore(
        SECRET_KEY,
        session_max_age=_SESSION_MAX_AGE,
        secure=ENV != "development",
    )
)
app.middlewares.append(security_headers_middleware)
configure_auth(app)

engine = create_engine(DB_URL)
SQLModel.metadata.create_all(engine)

auth.register_routes(app)
routes.register_routes(app)
event.register_routes(app, engine)
festival.register_routes(app, engine)
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
        event_data = asyncio.run(event.parse(args.url, debug=args.debug))
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
