import secrets
import urllib.parse
from typing import Awaitable, Callable

import httpx
from blacksheep import Request, Response
from blacksheep.server.responses import redirect

from born_portal.core import (GOOGLE_AUTH_URL, GOOGLE_CLIENT_ID,
                              GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN_URL,
                              GOOGLE_USERINFO_URL, REDIRECT_URI, render)


class AuthMiddleware:
    def __init__(self, public_paths: set[str], allowed_users: set[str]):
        self._public = public_paths or {"/login", "/auth/google", "/auth/callback"}
        self._allowed_users = allowed_users

    async def __call__(
        self, request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.path in self._public:
            return await handler(request)

        if not request.session.get("user"):
            return redirect("/login")

        if request.session.get("user") not in self._allowed_users:
            return render(
                "error.html", message="Access denied: your account is not allowed."
            )

        return await handler(request)


def register_routes(app):
    @app.router.get("/login")
    async def login_page(request: Request):
        if request.session.get("user"):
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
            return render(
                "error.html", message="Invalid OAuth state. Please try again."
            )

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

        request.session["user"] = user.get("email", "")
        return redirect("/")

    @app.router.get("/logout")
    async def logout(request: Request):
        del request.session["user"]
        return redirect("/login")
