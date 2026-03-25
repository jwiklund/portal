import granian

from blacksheep import Application
from blacksheep.sessions import SessionMiddleware
from blacksheep.sessions.memory import InMemorySessionStore

from born_portal.core import ALLOWED_USERS
from born_portal import routes, auth


app = Application()

_PUBLIC_PATHS = {"/login", "/auth/google", "/auth/callback"}

app.middlewares.append(SessionMiddleware(store=InMemorySessionStore()))
app.middlewares.append(
    auth.AuthMiddleware(public_paths=_PUBLIC_PATHS, allowed_users=ALLOWED_USERS)
)

auth.register_routes(app)
routes.register_routes(app)


def main():
    granian.Granian(
        "born_portal.main:app", interface="asgi", port=8080, reload=True
    ).serve()
