"""Aggregate events from the supported sources for the potential page.

The parsed events for each source are cached in memory for an hour so that
importing several events from the page does not refetch the source.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from born_portal.upcoming.model import UpcomingData
from born_portal.upcoming.sources import Source, all_sources, get_source

_CACHE_TTL_SECONDS = 3600

# source key -> (monotonic timestamp, parsed events)
_cache: dict[str, tuple[float, list[UpcomingData]]] = {}

# Ra.Clock event names start with a type marker, e.g. "🔴 HARD | ...".
# Keep it in the display name, but ignore it when matching events.
_RAVE_TYPE_RE = re.compile(r"^\s*[^\w\s]*\s*([A-Z][A-Z ]*)\s*\|\s*")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "club",
    "feat",
    "featuring",
    "for",
    "from",
    "in",
    "invite",
    "invites",
    "label",
    "live",
    "night",
    "of",
    "on",
    "pres",
    "present",
    "presents",
    "the",
    "to",
    "vs",
    "with",
    "x",
}


@dataclass
class SourceResult:
    """The events fetched from one source, or the error that stopped it."""

    source: Source
    events: list[UpcomingData] = field(default_factory=list)
    error: str | None = None


@dataclass
class SourceEvent:
    """An event together with the source that produced it."""

    source: Source
    event: UpcomingData


@dataclass
class EventCluster:
    """One event, possibly listed by several sources under different names.

    ``primary`` is the event shown in the single list; ``alternatives`` are the
    other source entries that matched it, shown as merge options. ``date`` is
    the best display date for the cluster (usually the primary's, but a precise
    alternative when the primary only has a date).
    """

    primary: SourceEvent
    alternatives: list[SourceEvent] = field(default_factory=list)
    date: str | None = None


def clear_cache() -> None:
    """Drop every cached source result."""
    _cache.clear()


async def source_events(
    source: Source, start: str, end: str, *, refresh: bool = False
) -> list[UpcomingData]:
    """Return a source's events for [start, end], using the in-memory cache."""
    if not refresh:
        cached = _cache.get(source.key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    events = await source.fetch(start, end)
    _cache[source.key] = (time.monotonic(), events)
    return events


async def all_potential(
    start: str, end: str, *, refresh: bool = False
) -> list[SourceResult]:
    """Fetch every source for [start, end], keeping per-source errors."""
    results: list[SourceResult] = []
    for source in all_sources():
        try:
            events = await source_events(source, start, end, refresh=refresh)
            results.append(SourceResult(source=source, events=events))
        except Exception as e:  # noqa: BLE001
            results.append(SourceResult(source=source, error=str(e)))
    return results


def rave_type(name: str) -> str | None:
    """Return the Ra.Clock type prefix (e.g. ``HARD``) or None."""
    match = _RAVE_TYPE_RE.match(name or "")
    return match.group(1).strip() if match else None


def normalize_name(name: str) -> str:
    """Normalise a name for matching.

    The Ra.Clock type prefix is dropped, separators are flattened, and common
    filler words are removed. The original name is kept for display.
    """
    text = _RAVE_TYPE_RE.sub("", name or "")
    text = text.replace("&", " and ").replace("@", " at ").replace("+", " and ")
    text = _PUNCT_RE.sub(" ", text)
    text = text.lower()
    words = [word for word in text.split() if word not in _STOPWORDS]
    return " ".join(words)


def _event_datetime(event: UpcomingData) -> datetime | None:
    """Parse the first part of a rendered event date, if possible."""
    if not event.date:
        return None
    first = event.date.split(" - ")[0]
    try:
        return datetime.fromisoformat(first)
    except ValueError:
        return None


def _jaccard(first: set[str], second: set[str]) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def _similar(first: SourceEvent, second: SourceEvent) -> bool:
    """Whether two source entries look like the same event.

    Matching is intentionally name- and date-based: same first word (or strong
    token overlap) and starts within a day. The Ra.Clock type is ignored.
    """
    first_date = _event_datetime(first.event)
    second_date = _event_datetime(second.event)
    if first_date is None or second_date is None:
        return False
    if abs((first_date.date() - second_date.date()).days) > 1:
        return False

    first_name = normalize_name(first.event.name)
    second_name = normalize_name(second.event.name)
    if not first_name or not second_name:
        return False

    first_words = first_name.split()
    second_words = second_name.split()
    if first_words[:2] == second_words[:2]:
        return True
    # A single-word promoter name (e.g. "Skyddsrum") is safe to match by its
    # first word, but generic short prefixes like "DJ" are not.
    if (
        len(first_words) == 1
        and len(first_words[0]) >= 4
        and first_words[0] == second_words[0]
    ):
        return True
    if (
        len(second_words) == 1
        and len(second_words[0]) >= 4
        and second_words[0] == first_words[0]
    ):
        return True
    return _jaccard(set(first_words), set(second_words)) >= 0.5


def _choose_primary(members: list[SourceEvent]) -> SourceEvent:
    """Prefer an entry with a Ra.Clock type (keeps the type), then the longest."""
    typed = [member for member in members if rave_type(member.event.name)]
    if typed:
        return typed[0]
    return max(members, key=lambda member: len(member.event.name))


def _has_time(event: UpcomingData) -> bool:
    """Whether the event's rendered date includes a time of day."""
    if not event.date:
        return False
    return " " in event.date.split(" - ")[0]


def _best_date(members: list[SourceEvent]) -> str | None:
    """Prefer the primary's date when it has a time; else a precise alternative."""
    primary = members[0]
    if _has_time(primary.event):
        return primary.event.date
    for member in members[1:]:
        if _has_time(member.event):
            return member.event.date
    return primary.event.date


def _sort_key(date: str | None) -> tuple[int, str]:
    if not date:
        return (1, "")
    return (0, date.split(" - ")[0])


def cluster_events(source_events: list[SourceEvent]) -> list[EventCluster]:
    """Group source events into one event per cluster, ordered by date."""
    clusters: list[EventCluster] = []
    for source_event in source_events:
        for cluster in clusters:
            members = [cluster.primary, *cluster.alternatives]
            if any(_similar(source_event, member) for member in members):
                cluster.alternatives.append(source_event)
                break
        else:
            clusters.append(EventCluster(primary=source_event))

    for cluster in clusters:
        members = [cluster.primary, *cluster.alternatives]
        primary = _choose_primary(members)
        cluster.primary = primary
        cluster.alternatives = [member for member in members if member is not primary]
        cluster.date = _best_date([primary, *cluster.alternatives])

    return sorted(clusters, key=lambda cluster: _sort_key(cluster.date))


def cluster_results(results: list[SourceResult]) -> list[EventCluster]:
    """Flatten successful results into a single date-ordered event list."""
    source_events = [
        SourceEvent(source=result.source, event=event)
        for result in results
        if not result.error
        for event in result.events
    ]
    return cluster_events(source_events)


async def find_event(
    source_key: str, url: str, start: str, end: str
) -> UpcomingData | None:
    """Look up a single cached event by source and URL."""
    source = get_source(source_key)
    if source is None:
        return None

    for event in await source_events(source, start, end):
        if event.url == url:
            return event
    return None
