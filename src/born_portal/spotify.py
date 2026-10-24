"""Spotify Web API helpers using the client credentials flow (no user login).

Shared by the festival page (artist search) and the playlist page (artist and
track search plus name lookups).
"""

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

import httpx2

from born_portal.core import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SEARCH_URL = "https://api.spotify.com/v1/search"

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


async def lookup_track(name: str, artist: str | None = None) -> dict | None:
    """Return a close Spotify track match for a title (and artist), or None."""
    query = f'track:"{name}"'
    if artist:
        query += f' artist:"{artist}"'

    tracks = await search_tracks(query, limit=5)
    if not tracks and artist:
        # Field filters can be too strict; retry with a plain text query.
        tracks = await search_tracks(f"{artist} {name}", limit=5)

    for track in tracks:
        if _is_close_name(name, track["name"]) and _artist_matches(
            artist, track["artist"]
        ):
            return track
    return None


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
