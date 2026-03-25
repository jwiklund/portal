"""
BlackSheep + Google OAuth example.

All routes are protected except:
  GET /login   – renders the login page
  GET /auth/callback – Google OAuth redirect URI

Set these environment variables (or create a .env file):
  GOOGLE_CLIENT_ID     – your Google OAuth 2.0 client ID
  GOOGLE_CLIENT_SECRET – your Google OAuth 2.0 client secret
  SECRET_KEY           – a long random string for session signing
  BASE_URL             – e.g. http://localhost:8000
"""

import os
import secrets
import urllib.parse
from functools import wraps

import httpx
from blacksheep import Application, Request, Response
from blacksheep.server.responses import html, redirect
from blacksheep.sessions import InMemorySessionSerializer, SessionMiddleware
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

REDIRECT_URI = f"{BASE_URL}/auth/callback"

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Application()

# Session middleware (signs cookies with SECRET_KEY)
app.middlewares.append(
    SessionMiddleware(
        secret_key=SECRET_KEY,
        session_serializer=InMemorySessionSerializer(),
    )
)

# Jinja2 templates
jinja = Environment(loader=FileSystemLoader("templates"), autoescape=True)


def render(template_name: str, **ctx) -> Response:
    return html(jinja.get_template(template_name).render(**ctx))


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
PUBLIC_PATHS = {"/login", "/auth/callback"}


def get_user(request: Request):
    """Return the user dict stored in the session, or None."""
    session = request.session  # type: ignore[attr-defined]
    return session.get("user")


def login_required(handler):
    """Decorator that redirects to /login when no session user is present."""

    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        if not get_user(request):
            return redirect("/login")
        return await handler(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Auth routes  (PUBLIC)
# ---------------------------------------------------------------------------
@app.router.get("/login")
async def login_page(request: Request):
    if get_user(request):
        return redirect("/")
    return render("login.html")


@app.router.get("/auth/google")
async def auth_google(request: Request):
    """Kick off the OAuth flow."""
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state  # type: ignore[index]

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return redirect(url)


@app.router.get("/auth/callback")
async def auth_callback(request: Request):
    """Google redirects here with ?code=… and ?state=…"""
    params = dict(request.query)
    code = params.get("code", [None])[0]
    state = params.get("state", [None])[0]

    if not code or state != request.session.get("oauth_state"):
        return render("error.html", message="Invalid OAuth state. Please try again.")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        user = userinfo_resp.json()

    request.session["user"] = {  # type: ignore[index]
        "sub": user["sub"],
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "picture": user.get("picture", ""),
    }
    return redirect("/")


@app.router.get("/logout")
async def logout(request: Request):
    request.session.clear()  # type: ignore[union-attr]
    return redirect("/login")


# ---------------------------------------------------------------------------
# Protected routes
# ---------------------------------------------------------------------------
@app.router.get("/")
@login_required
async def index(request: Request):
    user = get_user(request)
    return render("index.html", user=user)


@app.router.get("/profile")
@login_required
async def profile(request: Request):
    user = get_user(request)
    return render("profile.html", user=user)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
