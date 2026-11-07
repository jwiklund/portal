"""Techno Stockholm (technoistockholm.se) event source.

https://technoistockholm.se/events is a Next.js App Router site whose event
data is embedded in the React Server Component (RSC) payload stream rather
than fetched client-side. A plain HTML GET with a browser ``User-Agent`` is
enough (no JS execution needed): the page contains a series of
``self.__next_f.push([1,"..."])`` calls whose string arguments, concatenated
in order, form the serialised RSC stream.

Inside that stream sits an ``"events":[...]`` JSON array (~two dozen objects).
Each object has ``startDate`` (UTC ISO with milliseconds), ``slug``, ``title``,
``description`` (plain text), ``venues`` (list of ``{name, address, city, ...}``)
and ``tickets`` (list of ``{url, type, price}``). The first well-formed ticket
link is used as the import URL; the event's own ``/events/<slug>`` page is the
fallback. ``startDate`` is converted to ``Europe/Stockholm`` before deciding
which day the event falls on.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx2

from born_portal.core import USER_AGENT
from born_portal.upcoming.model import UpcomingData
from born_portal.upcoming.sources.base import Source, unique_url
from born_portal.utils.date_range import parse_date_range

_EVENTS_URL = "https://technoistockholm.se/events"
_BASE_URL = "https://technoistockholm.se/events/"
_STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")

_HEADERS = {
    "User-Agent": USER_AGENT,
}

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)')


def _get_array(text: str, key: str) -> list | None:
    """Extract and decode the JSON array that follows ``"<key>":`` in ``text``.

    Bracket matching respects JSON strings and escapes, so braces/brackets
    inside string values do not confuse it. Returns None when absent/invalid.
    """
    marker = f'"{key}":['
    start = text.find(marker)
    if start == -1:
        return None
    start += len(marker) - 1  # position of the opening '['
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def extract_events(html: str) -> list[dict]:
    """Extract the ``events`` array from a technoistockholm.se HTML page.

    Pure function: no network access, so it can be unit-tested directly.
    """
    chunks = _PUSH_RE.findall(html)
    stream = "".join(json.loads(chunk) for chunk in chunks)
    events = _get_array(stream, "events")
    return events if isinstance(events, list) else []


def _location(venues: list) -> str | None:
    """Best-effort venue label: the venue name, else its address/city."""
    if not venues:
        return None
    venue = venues[0] or {}
    name = (venue.get("name") or "").strip()
    if name:
        return name
    parts = [venue.get("address"), venue.get("city")]
    joined = ", ".join(part.strip() for part in parts if part and part.strip())
    return joined or None


def _price(tickets: list) -> str | None:
    """First ticket with a price, as a plain string."""
    for ticket in tickets:
        if not ticket:
            continue
        price = ticket.get("price")
        if price:
            return str(price)
    return None


def _ticket_url(tickets: list) -> str | None:
    """First well-formed ticket link (the ticket provider), if any.

    The source occasionally repeats a malformed URL such as
    ``https://billetto.sehttps://billetto.se/...``; skip those and fall back to
    the event's own page.
    """
    for ticket in tickets:
        if not ticket:
            continue
        url = (ticket.get("url") or "").strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        if url.count("://") > 1:
            continue
        return url
    return None


def _local_start(start_date: str | None) -> datetime | None:
    """Parse a UTC ISO ``startDate`` and convert it to Europe/Stockholm."""
    if not start_date:
        return None
    try:
        parsed = datetime.fromisoformat(start_date)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(_STOCKHOLM_TZ)


def parse_events(rows: list[dict], start: str, end: str) -> list[UpcomingData]:
    """Map raw event dicts to :class:`UpcomingData`, filtered to [start, end].

    Pure function: no network access, so it can be unit-tested directly.
    """
    events: list[UpcomingData] = []
    seen_urls: set[str] = set()
    for row in rows:
        if not row:
            continue
        slug = row.get("slug")
        if not slug:
            continue
        start_local = _local_start(row.get("startDate"))
        if start_local is None:
            continue

        local_date = start_local.date().isoformat()
        if local_date < start or local_date > end:
            continue

        venues = row.get("venues") or []
        tickets = row.get("tickets") or []
        start_label = start_local.strftime("%Y-%m-%d %H:%M")
        fallback_url = f"{_BASE_URL}{slug}"

        events.append(
            UpcomingData(
                url=unique_url(_ticket_url(tickets), fallback_url, seen_urls),
                name=(row.get("title") or "").strip(),
                description=(row.get("description") or "").strip(),
                location=_location(venues),
                price=_price(tickets),
                date=parse_date_range(start_label) or start_label,
                ticket=bool(tickets),
            )
        )
    return events


async def fetch(start: str, end: str) -> list[UpcomingData]:
    """Return Techno Stockholm events in the inclusive [start, end] range."""
    async with httpx2.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(_EVENTS_URL, headers=_HEADERS)
        try:
            resp.raise_for_status()
        except httpx2.HTTPError as e:
            raise RuntimeError(f"technoistockholm.se request failed: {e}") from e

    return parse_events(extract_events(resp.text), start, end)


SOURCE = Source(
    key="technoistockholm",
    name="Techno Stockholm",
    url="https://technoistockholm.se/events",
    fetch=fetch,
)
