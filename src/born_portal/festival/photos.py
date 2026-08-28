"""Fetch photos from a link-shared Google Photos album.

Google removed API access to shared albums in April 2025, but the public
share page still embeds every photo URL in its HTML. We fetch the share URL
server-side (no login needed for link-shared albums) and extract the media
base URLs from the embedded AF_initDataCallback JSON payload.

Media entries carry a type code in their payload (14 = photo, 1 = video).
Videos are skipped: they cannot be played inline (HEVC/MOV), so the page
links to the album on Google Photos instead. Photos use size suffixes
like "=w1920".
"""

from __future__ import annotations

import html
import json
import re
import time

import httpx

_THUMB_SIZE = "=w400-h400-c"
_VIEW_SIZE = "=w1920"
_FULL_SIZE = "=s0"

_TYPE_VIDEO = 1

_CACHE_TTL_SECONDS = 600
_cache: dict[str, tuple[float, list[dict]]] = {}
_html_cache: dict[str, tuple[float, str]] = {}

_CALLBACK_RE = re.compile(r"AF_initDataCallback\((\{.*?\})\);", re.DOTALL)
_DATA_RE = re.compile(r"data:(\[.*\]),\s*sideChannel", re.DOTALL)
_URL_RE = re.compile(
    r'\["https://lh[3-6]\.googleusercontent\.com/(pw/[A-Za-z0-9_-]+)",(\d+),(\d+)'
)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"|([\w:-]+)\s*=\s*\'([^\']*)\'')
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_GOOGLE_SUFFIX_RE = re.compile(r"\s*[-–—]\s*Google Photos\s*$", re.IGNORECASE)


def _walk(value):
    if isinstance(value, list):
        yield value
        for item in value:
            yield from _walk(item)


def _as_media(entry: list) -> dict | None:
    """Return {url, width, height, is_video} for a media entry, else None."""
    if (
        len(entry) >= 10
        and isinstance(entry[0], str)
        and entry[0].startswith("https://lh")
        and isinstance(entry[1], int)
        and isinstance(entry[2], int)
        and isinstance(entry[8], list)
        and len(entry[8]) > 2
        and isinstance(entry[8][2], int)
    ):
        return {
            "url": entry[0],
            "width": entry[1],
            "height": entry[2],
            "is_video": entry[8][2] == _TYPE_VIDEO,
        }
    return None


def _items_from_payload(html: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for match in _CALLBACK_RE.finditer(html):
        data_match = _DATA_RE.search(match.group(1))
        if not data_match:
            continue
        try:
            data = json.loads(data_match.group(1))
        except json.JSONDecodeError:
            continue
        for entry in _walk(data):
            media = _as_media(entry)
            if media and media["url"] not in seen:
                seen.add(media["url"])
                items.append(media)
    return items


def _fallback_items(html: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(html):
        url = f"https://lh3.googleusercontent.com/{match.group(1)}"
        if url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "url": url,
                "width": int(match.group(2)),
                "height": int(match.group(3)),
                "is_video": False,
            }
        )
    return items


def parse_album_html(html: str) -> list[dict]:
    """Extract unique photo items (poster URLs + dimensions) from album HTML."""
    items = _items_from_payload(html) or _fallback_items(html)
    media = []
    for item in items:
        if item["is_video"]:
            continue
        url = item["url"]
        media.append(
            {
                "thumb": url + _THUMB_SIZE,
                "view": url + _VIEW_SIZE,
                "full": url + _FULL_SIZE,
                "width": item["width"],
                "height": item["height"],
            }
        )
    return media


def _title_from_og_meta(html_text: str) -> str | None:
    for tag in _META_TAG_RE.finditer(html_text):
        attrs = {}
        for m in _ATTR_RE.finditer(tag.group(0)):
            key, value = m.group(1) or m.group(3), m.group(2) or m.group(4)
            attrs[key.lower()] = value
        if attrs.get("property") == "og:title":
            title = html.unescape(attrs.get("content", "")).strip()
            if title:
                return title
    return None


def _title_from_title_tag(html_text: str) -> str | None:
    match = _TITLE_TAG_RE.search(html_text)
    if not match:
        return None
    title = html.unescape(match.group(1)).strip()
    title = _GOOGLE_SUFFIX_RE.sub("", title).strip()
    return title or None


def _title_from_payload(html_text: str) -> str | None:
    """Album title is the first [string, null] pair of a data payload."""
    for match in _CALLBACK_RE.finditer(html_text):
        data_match = _DATA_RE.search(match.group(1))
        if not data_match:
            continue
        try:
            data = json.loads(data_match.group(1))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(data, list)
            and data
            and isinstance(data[0], list)
            and data[0]
            and isinstance(data[0][0], str)
        ):
            return data[0][0]
    return None


def parse_album_title(html_text: str) -> str | None:
    """Extract the album title from an album share page."""
    return (
        _title_from_og_meta(html_text)
        or _title_from_title_tag(html_text)
        or _title_from_payload(html_text)
    )


async def fetch_album_page(album_uri: str) -> str:
    """Fetch the album share page HTML, using an in-memory cache."""
    cached = _html_cache.get(album_uri)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(album_uri, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

    _html_cache[album_uri] = (time.monotonic(), resp.text)
    return resp.text


async def fetch_album_photos(album_uri: str) -> list[dict]:
    """Fetch photos for an album URI, using an in-memory cache."""
    cached = _cache.get(album_uri)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    photos = parse_album_html(await fetch_album_page(album_uri))
    if photos:
        _cache[album_uri] = (time.monotonic(), photos)
    return photos
