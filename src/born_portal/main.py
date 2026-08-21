import argparse
import asyncio
import json
import logging

from blacksheep import Application
from blacksheep.sessions import SessionMiddleware
from blacksheep.sessions.cookies import CookieSessionStore

from born_portal import auth, event, festival, podcast, routes, show
from born_portal.core import ADMIN_USERS, SECRET_KEY, VIEW_USERS

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

app = Application()

_PUBLIC_PATHS = {
    "/login",
    "/auth/google",
    "/auth/callback",
    "/podcasts/audio/",
    "/shows/video/",
}

app.middlewares.append(SessionMiddleware(store=CookieSessionStore(SECRET_KEY)))
app.middlewares.append(
    auth.AuthMiddleware(
        public_paths=_PUBLIC_PATHS,
        admin_users=ADMIN_USERS,
        view_users=VIEW_USERS,
    )
)

auth.register_routes(app)
routes.register_routes(app)
event.register_routes(app)
festival.register_routes(app)
podcast.register_routes(app)
show.register_routes(app)


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
    parse_parser = subparsers.add_parser("parse", help="Parse event example")
    fetch_parser.add_argument("url", help="URL to fetch and parse")

    args = parser.parse_args(argv)

    if args.command == "fetch":
        event_data = asyncio.run(event.parse(args.url))
        print(json.dumps(event_data.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "parse":
        with open("biletto.html") as r:
            event_data = event.parse_biletto(r.read())
            print(event_data.description)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
