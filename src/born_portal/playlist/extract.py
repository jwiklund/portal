"""Extract the event name, year and lineup from event content.

Content comes either from a fetched event URL (same safe-fetch path as event
import) or from text pasted directly by the user. In both cases the text is
handed to the LLM, which returns the event metadata and artist names as JSON.
Each artist is then looked up on Spotify so the page can show and match them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from born_portal import llm, spotify
from born_portal.utils.fetch import fetch_page_markdown

_SYSTEM_PROMPT = (
    "You extract the music lineup from a single event page or from pasted "
    "event/lineup text. Reply with ONLY a JSON object of the shape "
    '{"event": {"name": string, "year": number or null}, "artists": [string, ...]}. '
    '"event.name" is the title of the event itself (the party or festival '
    'name), never the venue, city or website name. "event.year" is the '
    "four-digit year the event takes place, or null when it is not stated. "
    '"artists" are the performing artists or DJs. Extract ONLY the artists '
    "that belong to the event this page is about (its headline lineup). Ignore "
    "everything else: navigation, menus, footers, newsletters, social links, "
    'cookie notices, "other events"/"upcoming events" lists, embedded '
    "Instagram or Facebook feeds, related-event promos, and artist biographies "
    "or descriptions of other events. Do not extract DJ or producer real names "
    'from biography text. Skip placeholders such as "TBA", "More TBA" or '
    '"TBC". Use the exact names as written; do not invent or translate names. '
    "Use an empty array when no artists are found."
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


@dataclass
class Lineup:
    """Event metadata plus the Spotify-matched artists for the page."""

    name: str = ""
    year: int | None = None
    artists: list[dict] = field(default_factory=list)


async def extract(url: str) -> Lineup:
    """Fetch an event page and return its event metadata and matched artists."""
    markdown = await fetch_page_markdown(url)
    return await extract_from_text(markdown)


async def extract_from_text(text: str) -> Lineup:
    """Extract event name/year and artists from pasted text."""
    response = await llm.completions(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        max_tokens=2048,
    )

    data = _parse_json(_response_text(response))
    event = data.get("event")
    artists = await _resolve_artists(_clean_artist_names(data.get("artists")))
    return Lineup(
        name=_clean_event_name(event),
        year=_clean_year(event),
        artists=artists,
    )


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


def _clean_event_name(raw) -> str:
    if not isinstance(raw, dict):
        return ""
    name = raw.get("name")
    return name.strip() if isinstance(name, str) else ""


def _clean_year(raw) -> int | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("year")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1990 <= value <= 2100 else None
    if isinstance(value, str):
        match = re.search(r"\b(19|20)\d{2}\b", value)
        if match:
            year = int(match.group(0))
            return year if 1990 <= year <= 2100 else None
    return None


def _clean_artist_names(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    names = []
    for item in raw:
        if isinstance(item, str) and item.strip() and not _is_placeholder(item):
            names.append(item.strip())
    return names


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
