"""Fetching public web pages for parsing.

Centralises the safe-fetch path used by event import and playlist extraction:
tracking parameters are stripped, the URL is validated against SSRF, and a
browser-like header set is chosen per host. The fetched HTML can be converted
to Markdown for LLM prompts.
"""

from __future__ import annotations

from typing import NamedTuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx2
import markdownify

from born_portal.utils.url_guard import validate_public_http_url

GOOGLEBOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

FIREFOX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
}


class FetchedPage(NamedTuple):
    """A fetched public page: the cleaned URL, its host and the HTML body."""

    url: str
    hostname: str
    html: str


async def fetch_public_html(url: str) -> FetchedPage:
    """Clean, validate and fetch a public page as HTML."""
    clean = validate_public_http_url(clean_url(url))
    hostname = urlparse(clean).hostname or ""
    html = await fetch_html(clean, headers=headers_for(hostname))
    return FetchedPage(url=clean, hostname=hostname, html=html)


async def fetch_page_markdown(url: str) -> str:
    """Fetch a public page and convert it to Markdown for LLM prompts."""
    page = await fetch_public_html(url)
    return html_to_markdown(page.html)


def clean_url(url: str) -> str:
    """Drop tracking query parameters (utm_*, stkn, fbclid) from a URL."""
    parsed = urlparse(url)

    params = {
        key: value
        for key, value in parse_qs(parsed.query).items()
        if _keep_parameter(key)
    }
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _keep_parameter(key: str) -> bool:
    # google analytics
    if key.startswith("utm_"):
        return False
    # instagram tracking
    if key == "stkn":
        return False
    # facebook tracking
    return key != "fbclid"


def headers_for(hostname: str) -> dict[str, str]:
    if hostname.endswith("instagram.com"):
        return GOOGLEBOT_HEADERS
    return FIREFOX_HEADERS


async def fetch_html(url: str, headers: dict[str, str]) -> str:
    async with httpx2.AsyncClient(
        timeout=30.0, headers=headers, follow_redirects=True
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown using markdownify."""
    return markdownify.markdownify(html, heading_style="ATX").strip()
