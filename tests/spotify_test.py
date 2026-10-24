from born_portal.spotify import _is_close_name


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
