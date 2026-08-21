import json

from born_portal.festival.photos import parse_album_html

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
    "ds:1", [["Album title", None], [[PHOTO_ENTRY, VIDEO_ENTRY]]]
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


def test_parses_unique_items():
    items = parse_album_html(HTML)
    assert len(items) == 2
    assert items[0]["full"].startswith(PHOTO_A)
    assert items[1]["full"].startswith(VIDEO_A)


def test_detects_videos_and_builds_stream_url():
    items = parse_album_html(HTML)
    assert items[0]["video"] is None
    assert items[1]["video"] == VIDEO_A + "=dv"


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
    assert items[1]["width"] == 1080
    assert items[1]["height"] == 1920


def test_fallback_parses_untyped_payloads_as_photos():
    items = parse_album_html(PLAIN_HTML)
    assert len(items) == 2
    assert all(item["video"] is None for item in items)
    assert items[0]["thumb"] == PHOTO_A + "=w400-h400-c"
    assert items[1]["width"] == 759
    assert items[1]["height"] == 759


def test_no_photos_in_empty_html():
    assert parse_album_html("<html><body>nothing here</body></html>") == []
