"""Spotify Web API helpers.

Artist/track search and name lookups use the client credentials flow (no user
login) and are shared by the festival and playlist pages. Creating a playlist
uses the authorization code flow so the user can log in and grant the
``playlist-modify-*`` scopes.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from difflib import SequenceMatcher

import httpx2

from born_portal.core import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
)

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SEARCH_URL = "https://api.spotify.com/v1/search"
_API_URL = "https://api.spotify.com/v1"
_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
_USER_SCOPES = "playlist-modify-private"

# Keys used to keep the logged-in user's tokens in the signed session cookie.
_ACCESS_TOKEN_KEY = "spotify_access_token"
_REFRESH_TOKEN_KEY = "spotify_refresh_token"
_EXPIRES_AT_KEY = "spotify_expires_at"

# Minimum fuzzy similarity between a requested name and a Spotify result before
# the result is accepted, so unrelated top hits are not returned as matches.
_MATCH_THRESHOLD = 0.8

_token: str | None = None
_token_expires_at: float = 0.0


class SpotifyError(Exception):
    pass


async def search_artists(query: str, limit: int = 8) -> list[dict]:
    """Search Spotify for artists. Returns [{name, spotify_uri, image}]."""
    items = await _search(query, "artist", limit)
    return [
        {
            "name": item["name"],
            "spotify_uri": item["uri"],
            "image": _smallest_image(item.get("images")),
        }
        for item in items
    ]


async def search_tracks(query: str, limit: int = 8) -> list[dict]:
    """Search Spotify for tracks. Returns [{name, artist, spotify_uri, image}]."""
    items = await _search(query, "track", limit)
    return [_track_from_item(item) for item in items]


async def lookup_artist(name: str) -> dict | None:
    """Return a close Spotify artist match for a name, or None."""
    artists = await search_artists(name, limit=5)
    for artist in artists:
        if _is_close_name(name, artist["name"]):
            return artist
    return None


async def top_tracks_for_artist(name: str, limit: int = 3) -> list[dict]:
    """Best-effort "top tracks" for an artist.

    The dedicated artist top-tracks endpoint was removed from the Web API in
    February 2026, so search (which orders by relevance/popularity) is used and
    the results are filtered to tracks actually credited to the artist.
    """
    query = f'artist:"{_sanitize_query(name)}"'
    search_limit = min(10, max(limit, 1) * 3)
    tracks = await search_tracks(query, limit=search_limit)
    picked = [track for track in tracks if _artist_matches(name, track["artist"])]

    if not picked:
        # Field filters can be too strict; retry with a plain text query.
        tracks = await search_tracks(_sanitize_query(name), limit=search_limit)
        picked = [track for track in tracks if _artist_matches(name, track["artist"])]

    return picked[:limit]


def _sanitize_query(name: str) -> str:
    return name.replace('"', " ").strip()


def _artist_matches(query: str | None, candidate: str) -> bool:
    if not query or not candidate:
        return True
    return _is_close_name(query, candidate)


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _is_close_name(query: str, candidate: str) -> bool:
    """True when two names are the same artist/track, allowing for styling."""
    a = _normalize_name(query)
    b = _normalize_name(candidate)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= _MATCH_THRESHOLD


def _track_from_item(item: dict) -> dict:
    artists = item.get("artists") or []
    return {
        "name": item["name"],
        "artist": ", ".join(a.get("name", "") for a in artists).strip(),
        "spotify_uri": item["uri"],
        "image": _smallest_image((item.get("album") or {}).get("images")),
    }


async def _search(query: str, kind: str, limit: int) -> list[dict]:
    token = await _get_token()
    async with httpx2.AsyncClient() as client:
        resp = await client.get(
            _SEARCH_URL,
            params={"q": query, "type": kind, "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get(f"{kind}s", {}).get("items", [])


def _smallest_image(images: list[dict] | None) -> str | None:
    if not images:
        return None
    return min(images, key=lambda img: img.get("width") or 0).get("url")


async def _get_token() -> str:
    global _token, _token_expires_at
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise SpotifyError(
            "Spotify search is not configured: set SPOTIFY_CLIENT_ID and "
            "SPOTIFY_CLIENT_SECRET"
        )
    if _token and time.monotonic() < _token_expires_at - 60:
        return _token

    async with httpx2.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        )
        resp.raise_for_status()
        data = resp.json()

    _token = data["access_token"]
    assert _token is not None
    _token_expires_at = time.monotonic() + data.get("expires_in", 3600)
    return _token


# ---------------------------------------------------------------------------
# User login (authorization code flow) and playlist creation
# ---------------------------------------------------------------------------


def authorize_url(state: str, redirect_uri: str = SPOTIFY_REDIRECT_URI) -> str:
    """Build the Spotify authorization URL that starts the user login flow."""
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": _USER_SCOPES,
        "state": state,
    }
    return _AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


async def exchange_code(code: str, redirect_uri: str = SPOTIFY_REDIRECT_URI) -> dict:
    """Exchange the authorization code from the callback for tokens."""
    return await _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
    )


async def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh token to obtain a fresh access token."""
    return await _token_request(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    )


def store_user_tokens(session, tokens: dict) -> None:
    """Persist the user's Spotify tokens in the session cookie."""
    session[_ACCESS_TOKEN_KEY] = tokens.get("access_token")
    if tokens.get("refresh_token"):
        session[_REFRESH_TOKEN_KEY] = tokens["refresh_token"]
    session[_EXPIRES_AT_KEY] = time.time() + int(tokens.get("expires_in", 3600))


async def user_access_token(session) -> str | None:
    """Return a usable access token for the logged-in user, or None."""
    token = session.get(_ACCESS_TOKEN_KEY)
    expires_at = session.get(_EXPIRES_AT_KEY) or 0
    if token and time.time() < float(expires_at) - 60:
        return token

    refresh = session.get(_REFRESH_TOKEN_KEY)
    if not refresh:
        return None

    tokens = await refresh_access_token(refresh)
    store_user_tokens(session, tokens)
    return tokens.get("access_token")


async def create_playlist(
    access_token: str,
    name: str,
    track_uris: list[str],
    public: bool = False,
) -> dict:
    """Create a playlist for the logged-in user and add the given tracks."""
    playlist = await _api_post(
        "/me/playlists",
        access_token,
        {"name": name, "public": public, "description": ""},
    )
    if track_uris:
        await _api_post(
            f"/playlists/{playlist['id']}/items",
            access_token,
            {"uris": track_uris},
        )
    return {
        "id": playlist["id"],
        "name": playlist.get("name", name),
        "url": (playlist.get("external_urls") or {}).get("spotify", ""),
        "track_count": len(track_uris),
    }


async def _token_request(data: dict) -> dict:
    async with httpx2.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data=data,
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        )
    if resp.status_code >= 400:
        raise SpotifyError(_error_message(resp))
    return resp.json()


async def _api_post(path: str, access_token: str, json_body: dict) -> dict:
    async with httpx2.AsyncClient() as client:
        resp = await client.post(
            _API_URL + path,
            json=json_body,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code >= 400:
        raise SpotifyError(_error_message(resp))
    return resp.json()


def _error_message(resp) -> str:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return f"Spotify request failed ({resp.status_code})"
    message = body.get("error_description") or body.get("error")
    if isinstance(message, dict):
        message = message.get("message")
    return message or f"Spotify request failed ({resp.status_code})"
