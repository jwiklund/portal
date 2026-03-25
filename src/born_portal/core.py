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
from blacksheep import Response
from blacksheep.server.responses import html
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
ALLOWED_USERS = set(os.environ.get("ALLOWED_USERS", "").split(","))

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

REDIRECT_URI = f"{BASE_URL}/auth/callback"

# Jinja2 templates
jinja = Environment(loader=FileSystemLoader("templates"), autoescape=True)


def render(template_name: str, **ctx) -> Response:
    return html(jinja.get_template(template_name).render(**ctx))
