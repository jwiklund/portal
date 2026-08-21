import json

from born_portal.festival.photos import parse_album_html, parse_album_title

PHOTO_A = "https://lh3.googleusercontent.com/pw/PHOTO_A"
PHOTO_B = "https://lh3.googleusercontent.com/pw/PHOTO_B"
VIDEO_A = "https://lh3.googleusercontent.com/pw/VIDEO_A"

# Real payload shape: [url, width, height, ..., marker, ...]
# where marker[2] is the media type code (14 = photo, 1 = video).
PHOTO_ENTRY = [
    PHOTO_A,
    1600,
    1200,
    None,
    None,
    None,
    None,
    None,
    [None, None, 14],
    [2763579],
    None,
    [[None, None, 1, 1]],
]
PHOTO_B_ENTRY = [
    PHOTO_B,
    759,
    759,
    None,
    None,
    None,
    None,
    None,
    [None, None, 14],
    [1234567],
    None,
    [[None, None, 1, 1]],
]
VIDEO_ENTRY = [
    VIDEO_A,
    1080,
    1920,
    None,
    None,
    None,
    None,
    None,
    [None, None, 1],
    [4739174],
]
COVER_ENTRY = [
    PHOTO_A,
    1600,
    1200,
    None,
    None,
    None,
    None,
    None,
    [1600, 1200, 14, None, ["Apple", "iPhone 16 Pro Max"]],
    [3289402],
    None,
    [[None, None, 1, 1]],
]


def _callback(key: str, data) -> str:
    return (
        f"<script>AF_initDataCallback({{key: '{key}', isPreloaded:true, "
        f"data:{json.dumps(data)}, sideChannel: []}});</script>"
    )


HTML = _callback("ds:0", [[COVER_ENTRY]]) + _callback(
    "ds:1", [["Album title", None], [[PHOTO_ENTRY, VIDEO_ENTRY, PHOTO_B_ENTRY]]]
)

# Simplified payload without the typed entry structure (fallback path)
PLAIN_HTML = """
<html><script>AF_initDataCallback({key: 'ds:2', isPreloaded:true, data:[
  ["album title", null],
  ["https://lh3.googleusercontent.com/pw/PHOTO_A",1600,1200],
  ["https://lh3.googleusercontent.com/pw/PHOTO_B",759,759],
  ["https://lh3.googleusercontent.com/pw/PHOTO_A",1600,1200]
]});</script></html>
"""


def test_parses_unique_items_skipping_videos():
    items = parse_album_html(HTML)
    assert len(items) == 2
    assert items[0]["full"].startswith(PHOTO_A)
    assert items[1]["full"].startswith(PHOTO_B)


def test_builds_size_variants():
    items = parse_album_html(HTML)
    first = items[0]
    assert first["thumb"] == PHOTO_A + "=w400-h400-c"
    assert first["view"] == PHOTO_A + "=w1920"
    assert first["full"] == PHOTO_A + "=s0"
    assert first["width"] == 1600
    assert first["height"] == 1200


def test_preserves_order_and_dimensions():
    items = parse_album_html(HTML)
    assert items[0]["width"] == 1600
    assert items[0]["height"] == 1200
    assert items[1]["width"] == 759
    assert items[1]["height"] == 759


def test_fallback_parses_untyped_payloads_as_photos():
    items = parse_album_html(PLAIN_HTML)
    assert len(items) == 2
    assert items[0]["thumb"] == PHOTO_A + "=w400-h400-c"
    assert items[1]["width"] == 759
    assert items[1]["height"] == 759


def test_no_photos_in_empty_html():
    assert parse_album_html("<html><body>nothing here</body></html>") == []


def test_title_from_og_meta():
    html = (
        '<html><head><meta property="og:title" content="Way Out West '
        '2026-08-06 - 2026-08-08"></head></html>'
    )
    assert parse_album_title(html) == "Way Out West 2026-08-06 - 2026-08-08"


def test_title_from_og_meta_single_quotes_and_entities():
    html = "<meta content='Siesta &#39;26' property='og:title'>"
    assert parse_album_title(html) == "Siesta '26"


def test_title_from_title_tag_strips_google_suffix():
    html = "<html><head><title>Bråvalla 2026 – Google Photos</title></head></html>"
    assert parse_album_title(html) == "Bråvalla 2026"


def test_title_from_payload_fallback():
    assert parse_album_title(HTML) == "Album title"


def test_title_missing_returns_none():
    assert parse_album_title("<html><body>nothing here</body></html>") is None
