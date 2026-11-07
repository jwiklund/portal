"""Registry of supported potential-event sources.

Add a source by creating a module that exposes a module-level ``SOURCE`` and
importing it below.
"""

from __future__ import annotations

from born_portal.upcoming.sources.base import Source
from born_portal.upcoming.sources.ra import SOURCE as _ra
from born_portal.upcoming.sources.raveoclock import SOURCE as _raveoclock
from born_portal.upcoming.sources.technobeatscloud import (
    SOURCE as _technobeatscloud,
)
from born_portal.upcoming.sources.technoistockholm import SOURCE as _technoistockholm

SOURCES: tuple[Source, ...] = (
    _ra,
    _raveoclock,
    _technoistockholm,
    _technobeatscloud,
)


def all_sources() -> tuple[Source, ...]:
    """Return every registered source, in display order."""
    return SOURCES


def get_source(key: str) -> Source | None:
    """Return the source registered under ``key``, or None."""
    for source in SOURCES:
        if source.key == key:
            return source
    return None


__all__ = ["Source", "all_sources", "get_source"]
