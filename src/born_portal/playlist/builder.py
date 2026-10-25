"""Build a Spotify playlist from a list of artists.

For each artist the best-matching tracks are looked up and the unique URIs are
added to a new playlist named after the event and year.
"""

from __future__ import annotations

from born_portal import spotify
from born_portal.core import current_year

# Aim for roughly this many tracks in the finished playlist. The per-artist
# count is derived from the lineup size so short lineups get more tracks and
# long lineups get fewer, always staying within [MIN, MAX].
TARGET_TRACKS = 20
MIN_TRACKS_PER_ARTIST = 3
MAX_TRACKS_PER_ARTIST = 10


def tracks_per_artist(artist_count: int) -> int:
    """Pick tracks per artist to land near TARGET_TRACKS, within [3, 10].

    Examples: 2 artists -> 10 each (20 total), 4 -> 5 each, 5 -> 4 each,
    7 -> 3 each (21 total).
    """
    if artist_count <= 0:
        return MAX_TRACKS_PER_ARTIST
    return max(
        MIN_TRACKS_PER_ARTIST,
        min(MAX_TRACKS_PER_ARTIST, round(TARGET_TRACKS / artist_count)),
    )


def playlist_name(event_name: str, year: int | None = None) -> str:
    """Compose the playlist title, e.g. "Alive Festival 2025"."""
    year = year or current_year()
    name = (event_name or "").strip()
    return f"{name} {year}" if name else f"Playlist {year}"


async def build_playlist(
    access_token: str,
    artist_names: list[str],
    name: str,
    *,
    per_artist: int | None = None,
    public: bool = False,
) -> dict:
    """Create a playlist with the top tracks of the given artists.

    When ``per_artist`` is omitted it is derived from the number of artists
    so the playlist ends up near ``TARGET_TRACKS``.
    """
    if per_artist is None:
        per_artist = tracks_per_artist(len(artist_names))

    uris: list[str] = []
    seen: set[str] = set()
    for artist_name in artist_names:
        tracks = await spotify.top_tracks_for_artist(artist_name, per_artist)
        for track in tracks:
            uri = track.get("spotify_uri")
            if uri and uri not in seen:
                seen.add(uri)
                uris.append(uri)
    return await spotify.create_playlist(access_token, name, uris, public=public)
