from born_portal import spotify
from born_portal.core import current_year
from born_portal.playlist.builder import (
    MAX_TRACKS_PER_ARTIST,
    MIN_TRACKS_PER_ARTIST,
    build_playlist,
    playlist_name,
    tracks_per_artist,
)


def test_playlist_name_uses_event_and_year():
    assert playlist_name("Alive Festival", 2025) == "Alive Festival 2025"


def test_playlist_name_trims_event_name():
    assert playlist_name("  Rave  ", 2024) == "Rave 2024"


def test_playlist_name_falls_back_when_no_event_name():
    assert playlist_name("", 2025) == "Playlist 2025"
    assert playlist_name("   ", None).startswith("Playlist ")


def test_playlist_name_defaults_to_current_year():
    assert playlist_name("Rave") == f"Rave {current_year()}"


def test_tracks_per_artist_targets_about_20_total():
    cases = {
        1: 10,  # capped at the max
        2: 10,  # 20 total
        3: 7,  # 21 total
        4: 5,  # 20 total
        5: 4,  # 20 total
        6: 3,  # 18 total
        7: 3,  # 21 total
        10: 3,  # 30 total (min floor)
    }
    for artist_count, expected in cases.items():
        assert tracks_per_artist(artist_count) == expected


def test_tracks_per_artist_stays_within_bounds():
    for artist_count in range(1, 100):
        per_artist = tracks_per_artist(artist_count)
        assert MIN_TRACKS_PER_ARTIST <= per_artist <= MAX_TRACKS_PER_ARTIST


def test_tracks_per_artist_handles_empty_lineup():
    assert tracks_per_artist(0) == MAX_TRACKS_PER_ARTIST
    assert tracks_per_artist(-1) == MAX_TRACKS_PER_ARTIST


def _fake_top_tracks(mapping):
    async def top_tracks_for_artist(name, limit):
        return mapping.get(name, [])[:limit]

    return top_tracks_for_artist


def _fake_create_playlist(calls):
    async def create_playlist(access_token, name, track_uris, public=False):
        calls.append(
            {
                "access_token": access_token,
                "name": name,
                "track_uris": track_uris,
                "public": public,
            }
        )
        return {
            "id": "pl1",
            "name": name,
            "url": "https://open.spotify.com/playlist/pl1",
            "track_count": len(track_uris),
        }

    return create_playlist


def test_build_playlist_dedupes_tracks_across_artists(monkeypatch):
    calls = []
    monkeypatch.setattr(
        spotify,
        "top_tracks_for_artist",
        _fake_top_tracks(
            {
                "Alpha": [
                    {"spotify_uri": "spotify:track:1"},
                    {"spotify_uri": "spotify:track:2"},
                ],
                "Beta": [
                    {"spotify_uri": "spotify:track:2"},
                    {"spotify_uri": "spotify:track:3"},
                ],
            }
        ),
    )
    monkeypatch.setattr(spotify, "create_playlist", _fake_create_playlist(calls))

    import asyncio

    result = asyncio.run(
        build_playlist("token", ["Alpha", "Beta"], "Party 2025", per_artist=2)
    )

    assert calls[0]["track_uris"] == [
        "spotify:track:1",
        "spotify:track:2",
        "spotify:track:3",
    ]
    assert calls[0]["name"] == "Party 2025"
    assert calls[0]["public"] is False
    assert result["track_count"] == 3


def test_build_playlist_skips_tracks_without_uri(monkeypatch):
    calls = []
    monkeypatch.setattr(
        spotify,
        "top_tracks_for_artist",
        _fake_top_tracks(
            {
                "Alpha": [
                    {"spotify_uri": None},
                    {"spotify_uri": "spotify:track:9"},
                ]
            }
        ),
    )
    monkeypatch.setattr(spotify, "create_playlist", _fake_create_playlist(calls))

    import asyncio

    asyncio.run(build_playlist("token", ["Alpha"], "Party 2025", per_artist=3))
    assert calls[0]["track_uris"] == ["spotify:track:9"]


def test_build_playlist_uses_dynamic_limit_by_default(monkeypatch):
    limits = []

    async def top_tracks_for_artist(name, limit):
        limits.append(limit)
        return []

    monkeypatch.setattr(spotify, "top_tracks_for_artist", top_tracks_for_artist)
    monkeypatch.setattr(spotify, "create_playlist", _fake_create_playlist([]))

    import asyncio

    # Five artists -> round(20 / 5) = 4 tracks each.
    asyncio.run(build_playlist("token", ["A", "B", "C", "D", "E"], "Party 2025"))
    assert limits == [4, 4, 4, 4, 4]


def test_build_playlist_explicit_limit_overrides_dynamic(monkeypatch):
    limits = []

    async def top_tracks_for_artist(name, limit):
        limits.append(limit)
        return []

    monkeypatch.setattr(spotify, "top_tracks_for_artist", top_tracks_for_artist)
    monkeypatch.setattr(spotify, "create_playlist", _fake_create_playlist([]))

    import asyncio

    asyncio.run(
        build_playlist("token", ["A", "B", "C", "D", "E"], "Party 2025", per_artist=2)
    )
    assert limits == [2, 2, 2, 2, 2]
