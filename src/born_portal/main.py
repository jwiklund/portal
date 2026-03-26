import granian

from blacksheep import Application
from blacksheep.sessions import SessionMiddleware
from blacksheep.sessions.cookies import CookieSessionStore

from born_portal.core import ALLOWED_USERS, SECRET_KEY
from born_portal import routes, auth


app = Application()

_PUBLIC_PATHS = {"/login", "/auth/google", "/auth/callback"}

app.middlewares.append(SessionMiddleware(store=CookieSessionStore(SECRET_KEY)))
app.middlewares.append(
    auth.AuthMiddleware(public_paths=_PUBLIC_PATHS, allowed_users=ALLOWED_USERS)
)

auth.register_routes(app)
routes.register_routes(app)


def main():
    granian.Granian(
        "born_portal.main:app", interface="asgi", port=8080, reload=True
    ).serve()
