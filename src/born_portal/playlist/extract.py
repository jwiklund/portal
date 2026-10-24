"""Extract artist and track names from event content, then match on Spotify.

Content comes either from a fetched event URL (same safe-fetch path as event
import) or from text pasted directly by the user. In both cases the text is
handed to the LLM, which returns artist and track names as JSON. Each name is
then looked up on Spotify so the page can show playable links.
"""

from __future__ import annotations

import json
import re

from born_portal import llm, spotify
from born_portal.utils.fetch import fetch_page_markdown

_SYSTEM_PROMPT = (
    "You extract the music lineup from a single event page or from pasted "
    "event/lineup text. Reply with ONLY a JSON object with two arrays: "
    '"artists" (performing artists or DJs) and "tracks" (song titles). '
    'Each "tracks" entry must be an object {"artist": string, "name": string}. '
    "Extract ONLY the artists and tracks that belong to the event this page "
    "is about (its headline lineup or set list). Ignore everything else: "
    "navigation, menus, footers, newsletters, social links, cookie notices, "
    '"other events"/"upcoming events" lists, embedded Instagram or Facebook '
    "feeds, related-event promos, and artist biographies or descriptions of "
    "other events. Do not extract DJ or producer real names from biography "
    'text. Skip placeholders such as "TBA", "More TBA" or "TBC", and skip '
    "unknown/unreleased track IDs. Use the exact names as written; do not "
    "invent or translate names. Use empty arrays when none are found."
)

# Names that are not real entries and should be dropped even if the model
# returns them.
_PLACEHOLDERS = {
    "tba",
    "tbc",
    "tba...",
    "tba…",
    "more tba",
    "more tbc",
    "to be announced",
    "to be confirmed",
    "more to be announced",
    "unreleased",
    "unknown",
    "id",
    "track id",
}


async def extract(url: str) -> tuple[list[dict], list[dict]]:
    """Fetch an event page and return (artists, tracks) matched on Spotify."""
    markdown = await fetch_page_markdown(url)
    return await extract_from_text(markdown)


async def extract_from_text(text: str) -> tuple[list[dict], list[dict]]:
    """Extract artists/tracks from pasted text and match them on Spotify."""
    response = await llm.completions(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        max_tokens=2048,
    )

    data = _parse_json(_response_text(response))
    artist_names = _clean_artist_names(data.get("artists"))
    track_specs = _clean_tracks(data.get("tracks"))

    artists = await _resolve_artists(artist_names)
    tracks = await _resolve_tracks(track_specs)
    return artists, tracks


def _response_text(response) -> str:
    if response.choices:
        return response.choices[0].message.content or ""
    return str(response)


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(1))

    if not isinstance(data, dict):
        raise TypeError("Unexpected response from the model")
    return data


def _is_placeholder(name: str) -> bool:
    cleaned = name.strip().rstrip(".").lower()
    return cleaned in _PLACEHOLDERS or cleaned.startswith("more tba")


def _clean_artist_names(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    names = []
    for item in raw:
        if isinstance(item, str) and item.strip() and not _is_placeholder(item):
            names.append(item.strip())
    return names


def _clean_tracks(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    tracks = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        artist = (item.get("artist") or "").strip()
        if name and not _is_placeholder(name):
            tracks.append({"name": name, "artist": artist})
    return tracks


async def _resolve_artists(names: list[str]) -> list[dict]:
    resolved = []
    seen: set[str] = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(await _match_artist(name))
    return resolved


async def _match_artist(name: str) -> dict:
    try:
        match = await spotify.lookup_artist(name)
    except spotify.SpotifyError:
        match = None
    return match or {"name": name, "spotify_uri": None, "image": None}


async def _resolve_tracks(specs: list[dict]) -> list[dict]:
    resolved = []
    seen: set[tuple[str, str]] = set()
    for spec in specs:
        key = (spec["name"].lower(), spec["artist"].lower())
        if key in seen:
            continue
        seen.add(key)
        resolved.append(await _match_track(spec["name"], spec["artist"]))
    return resolved


async def _match_track(name: str, artist: str) -> dict:
    try:
        match = await spotify.lookup_track(name, artist or None)
    except spotify.SpotifyError:
        match = None
    return match or {
        "name": name,
        "artist": artist,
        "spotify_uri": None,
        "image": None,
    }
