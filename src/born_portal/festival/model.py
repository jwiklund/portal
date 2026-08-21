from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ArtistData:
    id: Optional[int] = None
    name: str = ""
    spotify_uri: Optional[str] = None


@dataclass(frozen=True)
class FestivalData:
    id: Optional[int] = None
    name: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    description: str = ""
    album_uri: Optional[str] = None
    artists: list[ArtistData] = field(default_factory=list)
