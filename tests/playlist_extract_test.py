from born_portal.playlist.extract import (
    _clean_artist_names,
    _clean_event_name,
    _clean_year,
    _resolve_artists,
)


def test_resolve_artists_without_token_skips_spotify():
    import asyncio

    resolved = asyncio.run(_resolve_artists(["Alpha", "Beta"], None))
    assert resolved == [
        {"name": "Alpha", "spotify_uri": None, "image": None},
        {"name": "Beta", "spotify_uri": None, "image": None},
    ]


def test_resolve_artists_dedupes_case_insensitively_without_token():
    import asyncio

    resolved = asyncio.run(_resolve_artists(["Alpha", "alpha", "Beta"], None))
    assert [a["name"] for a in resolved] == ["Alpha", "Beta"]


def test_placeholders_dropped_from_artists():
    assert _clean_artist_names(
        ["Ummet Ozcan", "TBA", "More TBA", "  ", "Blastoyz"]
    ) == [
        "Ummet Ozcan",
        "Blastoyz",
    ]


def test_clean_artist_names_ignores_non_strings():
    assert _clean_artist_names(["Real", None, 42, {"name": "x"}]) == ["Real"]


def test_event_name_stripped_from_object():
    assert _clean_event_name({"name": "  Alive Festival  "}) == "Alive Festival"


def test_event_name_missing_or_invalid():
    assert _clean_event_name(None) == ""
    assert _clean_event_name({"name": 7}) == ""
    assert _clean_event_name({}) == ""


def test_year_accepts_numbers_in_range():
    assert _clean_year({"year": 2024}) == 2024


def test_year_parsed_from_strings():
    assert _clean_year({"year": "July 2025"}) == 2025


def test_year_rejects_out_of_range_and_invalid():
    assert _clean_year({"year": 1200}) is None
    assert _clean_year({"year": True}) is None
    assert _clean_year(None) is None
    assert _clean_year({"year": "soon"}) is None
