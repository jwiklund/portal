import asyncio
import json
import os
from urllib.parse import parse_qs, urlparse

from blacksheep.testing import TestClient

# Give the real app its own Router so this import doesn't collide with the
# throwaway Applications other tests build via the shared default router.
os.environ["APP_DEFAULT_ROUTER"] = "0"

from born_portal import spotify
from born_portal.main import app
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


def _location(response) -> str:
    return response.get_first_header(b"location").decode()


def test_test_flow_returns_to_test_without_session(monkeypatch):
    async def fake_exchange(code, redirect_uri=None):
        return {"access_token": "t", "refresh_token": "r", "expires_in": 3600}

    monkeypatch.setattr(spotify, "exchange_code", fake_exchange)

    async def run():
        if not app.started:
            await app.start()
        client = TestClient(app)

        start = await client.get("/test/spotify")
        assert start.status == 302
        state = parse_qs(urlparse(_location(start)).query)["state"][0]
        assert state.startswith("test-")

        # No session cookie: simulates the callback running in a different
        # cookie jar (e.g. an iOS home-screen app handing off to Safari).
        callback = await client.get(
            "/spotify/callback", query={"code": "x", "state": state}
        )
        assert callback.status == 302
        assert _location(callback) == "/test"

    asyncio.run(run())


def test_normal_callback_rejects_unmatched_state():
    async def run():
        if not app.started:
            await app.start()
        client = TestClient(app)
        callback = await client.get(
            "/spotify/callback", query={"code": "x", "state": "playlist-bogus"}
        )
        assert callback.status == 302
        assert _location(callback) == "/playlists"

    asyncio.run(run())
