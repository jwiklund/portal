"""TechnoBeatsCloud (technobeatscloud.com) event source.

https://technobeatscloud.com/en/events/map/november-2026/sweden/stockholm
renders its event map client-side, but the underlying data comes from a public
JSON endpoint (no authentication, a browser ``User-Agent`` is enough)::

    GET https://technobeatscloud.com/api/agenda/map-events
        ?locale=en&tz=Europe/Stockholm&from=<YYYY-MM-DD>&to=<YYYY-MM-DD>
        &bbox=<minLng,minLat,maxLng,maxLat>

``bbox`` is required; the Stockholm bounding box is taken from the page's
JSON-LD. ``from``/``to`` are inclusive dates scoped to ``Europe/Stockholm``,
matching the source's ``start``/``end`` arguments directly.

The response is a JSON object with an ``events`` array. Each event has
``slug``, ``name``, ``start_date``/``start_time``, venue fields
(``venue_name_override``, ``computed_venue_name``, ``location_label``) and
``min_price``/``min_currency``. The detail page is
``https://technobeatscloud.com/en/events/event/<slug>`` (reached via redirect).
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx2

from born_portal.core import USER_AGENT
from born_portal.upcoming.model import UpcomingData
from born_portal.upcoming.sources.base import Source
from born_portal.utils.date_range import parse_date_range

_API_URL = "https://technobeatscloud.com/api/agenda/map-events"
_BASE_URL = "https://technobeatscloud.com/en/events/event"
_STOCKHOLM_BBOX = "17.6087,59.0994,18.5214,59.5658"

_HEADERS = {
    "User-Agent": USER_AGENT,
}


def build_url(start: str, end: str) -> str:
    """Build the map-events API URL for the inclusive date range."""
    query = urlencode(
        {
            "locale": "en",
            "tz": "Europe/Stockholm",
            "from": start,
            "to": end,
            "bbox": _STOCKHOLM_BBOX,
        }
    )
    return f"{_API_URL}?{query}"


def _location(row: dict) -> str | None:
    """Venue override, then computed name, then the location label."""
    for key in ("venue_name_override", "computed_venue_name", "location_label"):
        value = (row.get(key) or "").strip()
        if value:
            return value
    return None


def _price(row: dict) -> str | None:
    """Format ``min_price`` with ``min_currency`` (whole numbers lose ``.0``)."""
    price = row.get("min_price")
    if price is None:
        return None
    if isinstance(price, float) and price.is_integer():
        amount = str(int(price))
    else:
        amount = str(price)
    currency = (row.get("min_currency") or "").strip()
    return f"{amount} {currency}".strip()


def _event_date(row: dict) -> str | None:
    """Combine ``start_date`` and ``start_time`` into a formatted date."""
    start_date = row.get("start_date")
    if not start_date:
        return None
    start_time = row.get("start_time")
    if start_time:
        return parse_date_range(f"{start_date} {start_time}")
    return parse_date_range(start_date)


def parse_events(payload: dict, start: str, end: str) -> list[UpcomingData]:
    """Map a map-events payload to :class:`UpcomingData`, filtered to [start, end].

    Pure function: no network access, so it can be unit-tested directly.
    """
    rows = payload.get("events") or []

    events: list[UpcomingData] = []
    for row in rows:
        if not row:
            continue
        slug = row.get("slug")
        start_date = row.get("start_date")
        if not slug or not start_date:
            continue
        if start_date < start or start_date > end:
            continue

        min_price = row.get("min_price")
        events.append(
            UpcomingData(
                url=f"{_BASE_URL}/{slug}",
                name=row.get("name") or "",
                description="",
                location=_location(row),
                price=_price(row),
                date=_event_date(row),
                ticket=min_price is not None and min_price > 0,
            )
        )
    return events


async def fetch(start: str, end: str) -> list[UpcomingData]:
    """Return TechnoBeatsCloud events in the inclusive [start, end] range."""
    async with httpx2.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(build_url(start, end), headers=_HEADERS)
        try:
            resp.raise_for_status()
        except httpx2.HTTPError as e:
            raise RuntimeError(f"technobeatscloud.com request failed: {e}") from e

    return parse_events(resp.json(), start, end)


SOURCE = Source(
    key="technobeatscloud",
    name="TechnoBeatsCloud",
    url=("https://technobeatscloud.com/en/events/map/november-2026/sweden/stockholm"),
    fetch=fetch,
)
