"""Rave O'Clock (raveoclock.se) event source.

https://raveoclock.se/ loads its calendar client-side ("Loading picks…") and
links to a public Google Calendar, so scraping the page is not viable. The
calendar's public iCal feed is::

    https://calendar.google.com/calendar/ical/34360595c3674b6bbca61d88c826ddde8634a5ad81eb30e24d689218df20cf7c%40group.calendar.google.com/public/basic.ics

It downloads without authentication (a plain ``httpx2`` GET is enough). The
feed is small (~a few dozen events), so the whole thing is fetched and filtered
locally to the requested date range.

Each ``VEVENT`` has ``DTSTART``/``DTEND`` in UTC (``...Z``), plus ``SUMMARY``,
``DESCRIPTION`` (HTML), ``LOCATION`` and ``UID``. There is no ``URL`` property,
but descriptions often contain a ticket or listing link; that is used as the
import URL when present. Otherwise a stable, unique link is synthesised from
the ``UID``. ``DTSTART`` is converted to ``Europe/Stockholm`` (stdlib
``zoneinfo``) before deciding which day the event falls on.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx2

from born_portal.core import USER_AGENT
from born_portal.upcoming.model import UpcomingData
from born_portal.upcoming.sources.base import Source, unique_url
from born_portal.utils.date_range import parse_date_range

_ICAL_URL = (
    "https://calendar.google.com/calendar/ical/"
    "34360595c3674b6bbca61d88c826ddde8634a5ad81eb30e24d689218df20cf7c"
    "%40group.calendar.google.com/public/basic.ics"
)
_BASE_URL = "https://raveoclock.se/"
_STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")

_HEADERS = {
    "User-Agent": USER_AGENT,
}

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_ESCAPE_RE = re.compile(r"\\(.)")
_TEXT_ESCAPES = {"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")

# Hosts that are social/meeting pages rather than an event or ticket listing.
_NON_EVENT_HOSTS = (
    "instagram.com",
    "facebook.com",
    "fb.com",
    "meet.google.com",
    "google.com",
    "forms.gle",
    "linktr.ee",
    "spotify.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "t.me",
    "wa.me",
    "twitter.com",
    "x.com",
)


def _is_non_event_host(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in _NON_EVENT_HOSTS)


def _listing_url(description: str) -> str | None:
    """First real event/ticket link in the description, if any.

    The iCal feed has no ``URL`` property, but descriptions often include a
    ticket or listing link. Social and meeting links are skipped so the import
    lands on something that describes the event.
    """
    text = html.unescape(_unescape(description or ""))
    for raw in _URL_RE.findall(text):
        url = raw.rstrip(").,;\"'")
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if _is_non_event_host(host):
            continue
        return url
    return None


def _unescape(value: str) -> str:
    """Undo iCal text escapes (``\\,`` ``\\;`` ``\\n`` ``\\\\``)."""
    return _ESCAPE_RE.sub(lambda m: _TEXT_ESCAPES.get(m.group(1), m.group(1)), value)


def _strip_html(value: str | None) -> str:
    """Collapse an HTML fragment into plain text."""
    if not value:
        return ""
    text = _unescape(value)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _unfold(text: str) -> list[str]:
    """Unfold iCal lines: a continuation starts with a space or tab."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []
    for line in lines:
        if line[:1] in (" ", "\t") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _split_property(line: str) -> tuple[str, dict[str, str], str]:
    """Split ``NAME[;PARAM=VALUE]:value`` into (name, params, value)."""
    name_part, _, value = line.partition(":")
    segments = name_part.split(";")
    name = segments[0].upper()
    params: dict[str, str] = {}
    for segment in segments[1:]:
        key, _, param_value = segment.partition("=")
        params[key.upper()] = param_value
    return name, params, value


def _parse_datetime(value: str, params: dict[str, str]) -> tuple[datetime, bool]:
    """Parse an iCal date/datetime, returning (aware datetime, is_date_only)."""
    value = value.strip()
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        return dt, False
    if "T" in value:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S")  # noqa: DTZ007
        tzid = params.get("TZID")
        try:
            tz = ZoneInfo(tzid) if tzid else _STOCKHOLM_TZ
        except (KeyError, ValueError):
            tz = _STOCKHOLM_TZ
        return dt.replace(tzinfo=tz), False
    dt = datetime.strptime(value, "%Y%m%d")  # noqa: DTZ007
    return dt.replace(tzinfo=_STOCKHOLM_TZ), True


def _format_date(
    start_local: datetime, end_local: datetime | None, date_only: bool
) -> str:
    """Format the local start/end as a range via ``parse_date_range``."""
    if date_only:
        start = start_local.date().isoformat()
        end = end_local.date().isoformat() if end_local else None
        if end and end != start:
            return parse_date_range(f"{start} - {end}") or start
        return parse_date_range(start) or start

    start = start_local.strftime("%Y-%m-%d %H:%M")
    if end_local is None:
        return parse_date_range(start) or start
    end = end_local.strftime("%Y-%m-%d %H:%M")
    return parse_date_range(f"{start} - {end}") or start


def _iter_vevents(lines: list[str]):
    """Yield each VEVENT as a dict of property name -> (params, value)."""
    current: dict[str, tuple[dict[str, str], str]] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None:
                yield current
            current = None
        elif current is not None and line and not line.startswith((" ", "\t")):
            name, params, value = _split_property(line)
            current[name] = (params, value)


def parse_ical(text: str, start: str, end: str) -> list[UpcomingData]:
    """Parse an iCal feed, keeping events whose local start date is in range.

    Pure function: no network access, so it can be unit-tested directly.
    """
    events: list[UpcomingData] = []
    seen_urls: set[str] = set()
    for props in _iter_vevents(_unfold(text)):
        dtstart = props.get("DTSTART")
        if not dtstart:
            continue
        params, raw_start = dtstart
        start_dt, date_only = _parse_datetime(raw_start, params)
        start_local = start_dt.astimezone(_STOCKHOLM_TZ)

        local_date = start_local.date().isoformat()
        if local_date < start or local_date > end:
            continue

        end_local: datetime | None = None
        if "DTEND" in props:
            end_params, raw_end = props["DTEND"]
            end_dt, _ = _parse_datetime(raw_end, end_params)
            end_local = end_dt.astimezone(_STOCKHOLM_TZ)

        uid = _unescape(props.get("UID", ({}, ""))[1]).strip()
        summary = props.get("SUMMARY", ({}, ""))[1]
        description = props.get("DESCRIPTION", ({}, ""))[1]
        fallback_url = f"{_BASE_URL}#{uid}"

        events.append(
            UpcomingData(
                url=unique_url(_listing_url(description), fallback_url, seen_urls),
                name=_unescape(summary).strip(),
                description=_strip_html(description),
                location=(
                    _unescape(props["LOCATION"][1]).strip()
                    if "LOCATION" in props
                    else None
                ),
                price=None,
                date=_format_date(start_local, end_local, date_only),
                ticket=False,
            )
        )
    return events


async def fetch(start: str, end: str) -> list[UpcomingData]:
    """Return Rave O'Clock events in the inclusive [start, end] date range."""
    async with httpx2.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(_ICAL_URL, headers=_HEADERS)
        try:
            resp.raise_for_status()
        except httpx2.HTTPError as e:
            raise RuntimeError(f"raveoclock.se iCal request failed: {e}") from e

    return parse_ical(resp.text, start, end)


SOURCE = Source(
    key="raveoclock",
    name="Ra.Clock",
    url="https://raveoclock.se/",
    fetch=fetch,
)
