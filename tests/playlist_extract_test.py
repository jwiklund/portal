from born_portal.playlist.extract import _clean_artist_names, _clean_tracks


def test_placeholders_dropped_from_artists():
    assert _clean_artist_names(
        ["Ummet Ozcan", "TBA", "More TBA", "  ", "Blastoyz"]
    ) == [
        "Ummet Ozcan",
        "Blastoyz",
    ]


def test_clean_artist_names_ignores_non_strings():
    assert _clean_artist_names(["Real", None, 42, {"name": "x"}]) == ["Real"]


def test_unreleased_tracks_dropped():
    assert _clean_tracks(
        [
            {"artist": "EverTwo", "name": "unreleased"},
            {"artist": "Aphex Twin", "name": "Windowlicker"},
        ]
    ) == [{"name": "Windowlicker", "artist": "Aphex Twin"}]


def test_clean_tracks_skips_invalid_entries():
    assert _clean_tracks([{"name": ""}, "nope", {"artist": "x"}]) == []
