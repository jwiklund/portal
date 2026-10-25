import json

from born_portal.playlist import routes as playlist_routes


def test_parse_year_accepts_valid_range():
    assert playlist_routes._parse_year("2025") == 2025
    assert playlist_routes._parse_year(" 1999 ") == 1999
    assert playlist_routes._parse_year(2024) == 2024


def test_parse_year_rejects_invalid():
    assert playlist_routes._parse_year("") is None
    assert playlist_routes._parse_year("abc") is None
    assert playlist_routes._parse_year("1200") is None
    assert playlist_routes._parse_year(None) is None


def test_parse_artists_filters_invalid_entries():
    raw = json.dumps(
        [
            {"name": "Alpha", "spotify_uri": "spotify:artist:1"},
            {"name": "  "},
            "nope",
            5,
        ]
    )
    assert playlist_routes._parse_artists(raw) == [
        {"name": "Alpha", "spotify_uri": "spotify:artist:1", "image": ""}
    ]


def test_parse_artists_handles_bad_json():
    assert playlist_routes._parse_artists("not json") == []
    assert playlist_routes._parse_artists(None) == []
    assert playlist_routes._parse_artists("{}") == []


def test_prune_pending_drops_expired_entries():
    playlist_routes._pending.clear()
    try:
        playlist_routes._pending["old"] = {"created_at": 0}
        playlist_routes._pending["fresh"] = {
            "created_at": playlist_routes._PENDING_TTL,
        }
        playlist_routes._prune_pending(now=playlist_routes._PENDING_TTL + 1)
        assert "old" not in playlist_routes._pending
        assert "fresh" in playlist_routes._pending
    finally:
        playlist_routes._pending.clear()


def test_remember_pending_stores_playlist():
    playlist_routes._pending.clear()
    try:
        playlist_routes._remember_pending("state123", "Party 2025", ["Alpha"])
        entry = playlist_routes._pending["state123"]
        assert entry["name"] == "Party 2025"
        assert entry["artist_names"] == ["Alpha"]
        assert "created_at" in entry
    finally:
        playlist_routes._pending.clear()
