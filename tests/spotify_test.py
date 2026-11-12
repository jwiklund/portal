import asyncio
import time

import pytest

from born_portal import spotify
from born_portal.spotify import SpotifyError, _error_message, _is_close_name


def test_identical_names_match_regardless_of_case():
    assert _is_close_name("Evertwo", "EverTwo")
    assert _is_close_name("Skyvibes", "SkyVibes")


def test_containment_matches_multi_artist_strings():
    assert _is_close_name("Aphex Twin", "Aphex Twin, Someone Else")


def test_punctuation_and_spacing_ignored():
    assert _is_close_name("Infected Mushroom", "InfectedMushroom")
    assert _is_close_name("SH;IFT", "shift")


def test_unrelated_top_hits_are_rejected():
    assert not _is_close_name("Vigx", "BigXthaPlug")
    assert not _is_close_name("Papi Chulo", "Papi Santana")
    assert not _is_close_name("Nick Psarros", "Nicky Pulse")
    assert not _is_close_name("Jenny With a View", "Terra")


def test_blank_names_never_match():
    assert not _is_close_name("", "Phaxe")
    assert not _is_close_name("Phaxe", "")


class _FakeResponse:
    def __init__(self, *, json_body=None, text="", status_code=403):
        self._json = json_body
        self.text = text
        self.status_code = status_code

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


def test_error_message_reads_plain_text_body():
    resp = _FakeResponse(text="Active premium subscription required for the owner.")
    assert _error_message(resp) == "Active premium subscription required for the owner."


def test_error_message_reads_nested_json_error():
    resp = _FakeResponse(
        json_body={"error": {"status": 403, "message": "Forbidden"}},
        text="ignored",
    )
    assert _error_message(resp) == "Forbidden"


def test_error_message_falls_back_without_body():
    resp = _FakeResponse()
    assert _error_message(resp) == "Spotify request failed (403)"


def test_is_connected_false_for_empty_session():
    assert not spotify.is_connected({})


def test_is_connected_true_with_refresh_or_access_token():
    assert spotify.is_connected({"spotify_refresh_token": "r"})
    assert spotify.is_connected({"spotify_access_token": "a"})


def test_require_user_token_raises_when_not_connected():
    with pytest.raises(SpotifyError):
        asyncio.run(spotify.require_user_token({}))


def test_require_user_token_returns_valid_token():
    session = {
        "spotify_access_token": "fresh",
        "spotify_expires_at": time.time() + 3600,
    }
    assert asyncio.run(spotify.require_user_token(session)) == "fresh"
