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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from blacksheep import Request, Response
from blacksheep.server.responses import html
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
ADMIN_USERS = set(os.environ.get("ADMIN_USERS", "").split(","))
VIEW_USERS = set(os.environ.get("VIEW_USERS", "").split(","))

# Role names used by the @auth authorization policies.
ADMIN_ROLE = "admin"
VIEWER_ROLE = "viewer"
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SHOWS_DIR = Path(os.environ.get("SHOWS_DIR", "shows"))
SHOWS_CACHE_DIR = Path(os.environ.get("SHOWS_CACHE_DIR", "shows_cache"))
SECRET_KEY = os.environ["SECRET_KEY"]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

REDIRECT_URI = f"{BASE_URL}/auth/callback"

# Jinja2 templates
jinja = Environment(loader=FileSystemLoader("templates"), autoescape=True)


def user(request) -> dict | None:
    email = request.session.get("user")
    if not email:
        return None
    return {"name": email.split("@")[0], "email": email}


def form_value(form: Mapping[str, Any] | None, key: str) -> str | None:
    """Extract a single string value from a parsed form body."""
    if not form:
        return None
    value = form.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                return item
    return None


def is_admin(request) -> bool:
    return request.session.get("user") in ADMIN_USERS


def is_viewer(request) -> bool:
    return request.session.get("user") in VIEW_USERS


def render(template_name: str, request: Request | None = None, **ctx) -> Response:
    if request is not None:
        ctx.setdefault("user", user(request))
        ctx.setdefault("is_admin", is_admin(request))
    return html(jinja.get_template(template_name).render(**ctx))
