"""Resident Advisor (ra.co) event source.

The public event page (https://ra.co/events/se/stockholm) is behind a
bot-protection challenge, so scraping the HTML is not viable.

Instead this source uses ra.co's public GraphQL API at
``POST https://ra.co/graphql``, which answers without authentication. The body
is a JSON object ``{"query": "..."}`` sent with a browser ``User-Agent`` and a
``Referer: https://ra.co/events/se/stockholm``.

Stockholm's area id is ``396``. ``eventListings`` filters on ``startTime``, a
``UtcDateTime`` value, so the local weekend boundary is converted to a UTC ISO
timestamp ending in ``Z``. ``contentUrl`` is relative (``/events/2563067``);
we prefix ``https://ra.co``. ``cost`` is a plain string (sometimes empty) and
``venue.name`` may be ``TBA``.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx2

from born_portal.core import USER_AGENT
from born_portal.upcoming.model import UpcomingData
from born_portal.upcoming.sources.base import Source
from born_portal.utils.date_range import parse_date_range

_GRAPHQL_URL = "https://ra.co/graphql"
_REFERER = "https://ra.co/events/se/stockholm"
_STOCKHOLM_AREA_ID = 396
_BASE_URL = "https://ra.co"
_STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": _REFERER,
    "Content-Type": "application/json",
}

_QUERY = """
query {
  eventListings(
    filters: {areas: {eq: %(area)s}, startTime: {gte: "%(start)s", lte: "%(end)s"}},
    pageSize: 50
  ) {
    data {
      id
      event {
        title date startTime endTime contentUrl cost isTicketed
        content
        venue { name }
      }
    }
  }
}
"""

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(value: str | None) -> str:
    """Collapse an HTML fragment (ra.co ``content``) into plain text."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _event_date(start_time: str | None, end_time: str | None) -> str | None:
    """Combine ra.co's naive start/end timestamps into a formatted range."""
    if not start_time:
        return None
    start = start_time[:19]
    if not end_time:
        return parse_date_range(start)
    return parse_date_range(f"{start} - {end_time[:19]}")


def parse_events(payload: dict) -> list[UpcomingData]:
    """Map a GraphQL ``eventListings`` payload to :class:`UpcomingData`.

    Pure function: no network access, so it can be unit-tested directly.
    """
    listings = (payload.get("data") or {}).get("eventListings") or {}
    rows = listings.get("data") or []

    events: list[UpcomingData] = []
    for row in rows:
        event = row.get("event") if row else None
        if not event:
            continue
        content_url = event.get("contentUrl")
        if not content_url:
            continue

        venue = event.get("venue") or {}
        cost = event.get("cost")
        events.append(
            UpcomingData(
                url=_BASE_URL + content_url,
                name=event.get("title") or "",
                description=_strip_html(event.get("content")),
                location=venue.get("name"),
                price=cost or None,
                date=_event_date(event.get("startTime"), event.get("endTime")),
                ticket=bool(event.get("isTicketed")),
            )
        )
    return events


def _to_utc_z(value: datetime) -> str:
    """Format a Stockholm-local datetime as a UTC ISO timestamp ending in Z."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


async def fetch(start: str, end: str) -> list[UpcomingData]:
    """Return Ra.co events in the inclusive [start, end] date range."""
    start_local = datetime.fromisoformat(start).replace(tzinfo=_STOCKHOLM_TZ)
    end_local = datetime.fromisoformat(end).replace(
        hour=23, minute=59, second=59, tzinfo=_STOCKHOLM_TZ
    )

    query = _QUERY % {
        "area": _STOCKHOLM_AREA_ID,
        "start": _to_utc_z(start_local),
        "end": _to_utc_z(end_local),
    }

    async with httpx2.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.post(_GRAPHQL_URL, json={"query": query}, headers=_HEADERS)
        try:
            resp.raise_for_status()
        except httpx2.HTTPError as e:
            raise RuntimeError(f"ra.co GraphQL request failed: {e}") from e

    payload = resp.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"ra.co GraphQL error: {errors}")

    return parse_events(payload)


SOURCE = Source(
    key="ra",
    name="Ra.co",
    url="https://ra.co/events/se/stockholm",
    fetch=fetch,
)
