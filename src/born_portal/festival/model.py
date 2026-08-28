from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArtistData:
    id: int | None = None
    name: str = ""
    spotify_uri: str | None = None


@dataclass(frozen=True)
class FestivalData:
    id: int | None = None
    name: str = ""
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    description: str = ""
    album_uri: str | None = None
    artists: list[ArtistData] = field(default_factory=list)
