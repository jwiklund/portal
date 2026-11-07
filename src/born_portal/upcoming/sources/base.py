"""The interface every potential-event source implements.

A *source* is an external calendar or event listing (Resident Advisor,
Rave O'Clock, ...) that the potential-events page can fetch, display and
import. Each source lives in its own module and exposes a module-level
``SOURCE`` object whose ``fetch`` returns parsed :class:`UpcomingData`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from born_portal.upcoming.model import UpcomingData

# (weekend_start, weekend_end) as inclusive ISO dates -> parsed events.
FetchFn = Callable[[str, str], Awaitable[list[UpcomingData]]]


@dataclass(frozen=True)
class Source:
    """An external event source that can be listed and imported."""

    key: str
    name: str
    url: str
    fetch: FetchFn


def unique_url(preferred: str | None, fallback: str, seen: set[str]) -> str:
    """Choose the URL to import an event under.

    ``preferred`` (usually a ticket link) is used when it is present and not
    already taken; otherwise ``fallback`` (the event's own page) keeps the
    imported URL unique. ``seen`` is mutated so later duplicates fall back.
    """
    if preferred and preferred not in seen:
        seen.add(preferred)
        return preferred
    seen.add(fallback)
    return fallback
