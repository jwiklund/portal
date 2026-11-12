from __future__ import annotations

import json
import secrets
import time

from blacksheep import Request
from blacksheep.server.responses import json as json_response
from blacksheep.server.responses import redirect

from born_portal import playlist, spotify
from born_portal.auth.guard import allow_anonymous, auth
from born_portal.core import (
    ADMIN_ROLE,
    SPOTIFY_REDIRECT_URI,
    current_year,
    form_value,
    render,
)
from born_portal.errors import record_error

_STATE_KEY = "spotify_oauth_state"
_NEXT_KEY = "spotify_post_login"
_FLASH_KEY = "playlist_flash"

# Pending playlist requests keyed by OAuth state. Kept server-side so long
# lineups do not bloat the signed session cookie.
_PENDING_TTL = 15 * 60
_pending: dict[str, dict] = {}


def _prune_pending(now: float | None = None) -> None:
    now = now or time.time()
    for state, item in list(_pending.items()):
        if now - item.get("created_at", 0) > _PENDING_TTL:
            _pending.pop(state, None)


def _remember_pending(state: str, name: str, artist_names: list[str]) -> None:
    _prune_pending()
    _pending[state] = {
        "name": name,
        "artist_names": artist_names,
        "created_at": time.time(),
    }


def register_routes(app):
    @app.router.get("/playlists")
    @auth(roles=[ADMIN_ROLE])
    async def playlists_page(request: Request):
        flash = _take_flash(request.session)
        return _render_page(
            request,
            created=flash.get("created"),
            error=flash.get("error"),
        )

    @app.router.post("/playlists")
    @auth(roles=[ADMIN_ROLE])
    async def playlists_parse(request: Request):
        form = await request.form()
        url = (form_value(form, "url") or "").strip()
        text = form_value(form, "text") or ""
        access_token = await _optional_token(request)

        if text.strip():
            try:
                lineup = await playlist.extract_from_text(text, access_token)
            except Exception as e:  # noqa: BLE001
                await record_error(request, e, context={"source": "text"})
                return _render_page(request, error=str(e), text=text)
        elif url.strip():
            try:
                lineup = await playlist.extract(url, access_token)
            except Exception as e:  # noqa: BLE001
                await record_error(request, e, context={"url": url})
                return _render_page(request, error=str(e), url=url)
        else:
            return _render_page(request, error="Please enter a URL or paste some text")

        return _render_page(
            request,
            artists=lineup.artists,
            event_name=lineup.name,
            year=lineup.year or current_year(),
            text=text,
            url=url,
        )

    @app.router.post("/playlists/create")
    @auth(roles=[ADMIN_ROLE])
    async def playlists_create(request: Request):
        form = await request.form()
        event_name = (form_value(form, "event_name") or "").strip()
        year = _parse_year(form_value(form, "year"))
        artists = _parse_artists(form_value(form, "artists"))
        artist_names = [a["name"] for a in artists if a.get("name")]

        if not artist_names:
            return _render_page(
                request,
                error="Add at least one artist before creating a playlist.",
                artists=artists,
                event_name=event_name,
                year=year,
            )

        name = playlist.playlist_name(event_name, year)

        try:
            access_token = await spotify.user_access_token(request.session)
        except Exception:  # noqa: BLE001 - refresh failure means "log in again"
            access_token = None

        if access_token:
            try:
                created = await playlist.build_playlist(
                    access_token, artist_names, name
                )
            except Exception as e:  # noqa: BLE001
                await record_error(request, e, context={"stage": "build_playlist"})
                return _render_page(
                    request,
                    error=f"Could not create the playlist: {e}",
                    artists=artists,
                    event_name=event_name,
                    year=year,
                )
            return _render_page(request, created=created)

        # Not logged in to Spotify yet: remember the playlist, then send the
        # user through the authorization code flow, which redirects back here.
        state = secrets.token_urlsafe(16)
        _remember_pending(state, name, artist_names)
        request.session[_STATE_KEY] = state
        return redirect(spotify.authorize_url(state, SPOTIFY_REDIRECT_URI))

    @app.router.get("/spotify/login")
    @auth(roles=[ADMIN_ROLE])
    async def spotify_login(request: Request):
        params = dict(request.query)
        next_path = (params.get("next", ["/playlists"])[0] or "").strip()
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/playlists"

        state = secrets.token_urlsafe(16)
        request.session[_STATE_KEY] = state
        request.session[_NEXT_KEY] = next_path
        return redirect(spotify.authorize_url(state, SPOTIFY_REDIRECT_URI))

    @app.router.get("/spotify/callback")
    @allow_anonymous()
    async def spotify_callback(request: Request):
        params = dict(request.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        session_state = request.session.get(_STATE_KEY)
        if error:
            if state and state == session_state:
                _pending.pop(state, None)
                del request.session[_STATE_KEY]
                _clear_next(request.session)
            _flash(request.session, error=f"Spotify login was cancelled: {error}")
            return redirect("/playlists")
        if not code or not state or state != session_state:
            _flash(request.session, error="Invalid Spotify login state. Please retry.")
            return redirect("/playlists")
        del request.session[_STATE_KEY]
        next_path = _take_next(request.session)

        try:
            tokens = await spotify.exchange_code(code, SPOTIFY_REDIRECT_URI)
        except Exception as e:  # noqa: BLE001
            await record_error(request, e, context={"stage": "spotify_exchange_code"})
            _pending.pop(state, None)
            _flash(request.session, error=f"Spotify login failed: {e}")
            return redirect("/playlists")

        spotify.store_user_tokens(request.session, tokens)

        pending = _pending.pop(state, None)
        if pending:
            try:
                created = await playlist.build_playlist(
                    tokens["access_token"], pending["artist_names"], pending["name"]
                )
                _flash(request.session, created=created)
            except Exception as e:  # noqa: BLE001
                await record_error(
                    request, e, context={"stage": "build_playlist_pending"}
                )
                _flash(request.session, error=f"Could not create the playlist: {e}")
        else:
            # Plain "Connect Spotify" login returns to where the user was.
            if next_path:
                return redirect(next_path)
            _flash(
                request.session,
                error=(
                    "Spotify login succeeded, but the pending playlist was lost. "
                    "Please try creating it again."
                ),
            )
        return redirect("/playlists")

    @app.router.get("/playlists/api/spotify/search")
    @auth(roles=[ADMIN_ROLE])
    async def playlist_spotify_search(request: Request):
        params = dict(request.query)
        query = (params.get("q", [""])[0] or "").strip()

        if not query:
            return json_response({"results": []})

        try:
            access_token = await spotify.require_user_token(request.session)
            results = await playlist.search_artists(access_token, query)
        except spotify.SpotifyError as e:
            return json_response({"error": str(e)}, status=502)
        except Exception as e:  # noqa: BLE001
            await record_error(request, e, context={"query": query})
            return json_response({"error": str(e)}, status=502)

        return json_response({"results": results})


def _render_page(
    request,
    *,
    artists=None,
    event_name="",
    year=None,
    text="",
    url="",
    error=None,
    created=None,
):
    return render(
        "playlists.html",
        request,
        artists=artists or [],
        event_name=event_name,
        year=year or current_year(),
        text=text,
        url=url,
        error=error,
        created=created,
        spotify_connected=spotify.is_connected(request.session),
    )


def _flash(session, *, created=None, error=None):
    session[_FLASH_KEY] = {"created": created, "error": error}


def _take_next(session) -> str | None:
    next_path = session.get(_NEXT_KEY)
    if _NEXT_KEY in session:
        del session[_NEXT_KEY]
    return next_path


def _clear_next(session) -> None:
    if _NEXT_KEY in session:
        del session[_NEXT_KEY]


async def _optional_token(request) -> str | None:
    """The user's Spotify token if connected, otherwise None (never raises)."""
    try:
        return await spotify.user_access_token(request.session)
    except Exception:  # noqa: BLE001 - a refresh failure just means "not connected"
        return None


def _take_flash(session):
    flash = session.get(_FLASH_KEY) or {}
    if _FLASH_KEY in session:
        del session[_FLASH_KEY]
    return flash


def _parse_year(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        year = value
    else:
        try:
            year = int(str(value or "").strip())
        except (TypeError, ValueError):
            return None
    return year if 1990 <= year <= 2100 else None


def _parse_artists(raw) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    artists = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if name:
            artists.append(
                {
                    "name": name,
                    "spotify_uri": item.get("spotify_uri") or "",
                    "image": item.get("image") or "",
                }
            )
    return artists
