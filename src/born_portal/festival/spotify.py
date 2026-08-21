"""Spotify artist search using the client credentials flow (no user login)."""

from __future__ import annotations

import time

import httpx

from born_portal.core import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SEARCH_URL = "https://api.spotify.com/v1/search"

_token: str | None = None
_token_expires_at: float = 0.0


class SpotifyError(Exception):
    pass


async def search_artists(query: str, limit: int = 8) -> list[dict]:
    """Search Spotify for artists. Returns [{name, spotify_uri, image}]."""
    token = await _get_token()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _SEARCH_URL,
            params={"q": query, "type": "artist", "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        items = resp.json().get("artists", {}).get("items", [])

    return [
        {
            "name": item["name"],
            "spotify_uri": item["uri"],
            "image": _smallest_image(item.get("images")),
        }
        for item in items
    ]


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

    async with httpx.AsyncClient() as client:
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
