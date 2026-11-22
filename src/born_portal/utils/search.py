"""Kagi subscriber search over the server-rendered HTML endpoint.

A Kagi "session link" is ``https://kagi.com/search?token=<TOKEN>``. The raw
``token`` query value is sent verbatim as the ``kagi_session`` cookie -- there
is no separate login exchange. The HTML results page is then parsed into
:class:`SearchResult` entries.

The token comes from ``KAGI_SESSION_TOKEN`` (see :mod:`born_portal.core`) or
can be passed explicitly to :func:`search`.
"""

from __future__ import annotations

from typing import TypedDict
from urllib.parse import parse_qs, urlencode, urlparse

import httpx2
from bs4 import BeautifulSoup

from born_portal.core import KAGI_SESSION_TOKEN
from born_portal.utils import parse_dates
from born_portal.utils.fetch import FIREFOX_HEADERS
from born_portal.utils.safe_http import get_public

KAGI_BASE_URL = "https://kagi.com"
KAGI_SEARCH_PATH = "/html/search"
KAGI_HOST = "kagi.com"

# A page that contains ALL of these markers is a logged-out landing page
# rather than a results page.
UNAUTHENTICATED_MARKERS = (
    "<title>Kagi Search - A Premium Search Engine</title>",
    "Welcome to Kagi",
    "paid search engine that gives power back to the user",
)


class KagiError(RuntimeError):
    """Base error for Kagi search failures."""


class KagiAuthError(KagiError):
    """The Kagi session token is missing, invalid or expired."""


class SearchResult(TypedDict):
    """One parsed Kagi result."""

    rank: int | None
    url: str
    title: str
    snippet: str
    published: str | None


def normalize_session_token(value: str) -> str:
    """Return the raw session token from a session-link URL or raw token."""
    token = value.strip()
    if not token:
        raise KagiAuthError("session token cannot be empty")

    if token.startswith(("http://", "https://")):
        query = parse_qs(urlparse(token).query)
        raw = (query.get("token") or [""])[0].strip()
        if not raw:
            raise KagiAuthError(
                "session link URL must include a non-empty token= query parameter"
            )
        return raw

    # A token copied from a search URL may still carry trailing query
    # parameters (e.g. "TOKEN&q=%s"). Kagi tokens never contain "&".
    return token.split("&", 1)[0].strip()


async def search(
    query: str,
    *,
    token: str | None = None,
    lens: str | None = None,
    region: str | None = None,
    time: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    order: str | None = None,
    verbatim: bool = False,
    personalized: bool | None = None,
    limit: int | None = None,
) -> list[SearchResult]:
    """Search Kagi and return the parsed results.

    ``token`` falls back to ``KAGI_SESSION_TOKEN`` and may be a session-link URL
    or the raw token. ``time`` is a relative window such as ``day`` or ``week``;
    ``from_date``/``to_date`` are ``YYYY-MM-DD``. ``personalized`` forces the
    setting on (``True``) or off (``False``).
    """
    raw_token = token or KAGI_SESSION_TOKEN
    if not raw_token:
        raise KagiAuthError("a Kagi session token is required; set KAGI_SESSION_TOKEN")

    params: list[tuple[str, str]] = [("q", query.strip())]
    if lens:
        params.append(("l", lens))
    if region:
        params.append(("r", region))
    if time:
        params.append(("dr", time))
    if from_date:
        params.append(("from_date", from_date))
    if to_date:
        params.append(("to_date", to_date))
    if order:
        params.append(("order", order))
    if verbatim:
        params.append(("verbatim", "1"))
    if personalized is not None:
        params.append(("personalized", "1" if personalized else "0"))

    url = f"{KAGI_BASE_URL}{KAGI_SEARCH_PATH}?{urlencode(params)}"
    headers = {
        **FIREFOX_HEADERS,
        "Cookie": f"kagi_session={normalize_session_token(raw_token)}",
    }

    try:
        response = await get_public(url, headers=headers, allowed_hosts={KAGI_HOST})
    except httpx2.HTTPStatusError as error:
        if error.response.status_code in (401, 403):
            raise KagiAuthError("invalid or expired Kagi session token") from error
        raise KagiError(f"Kagi search failed: {error}") from error

    if looks_challenged(str(response.url)):
        raise KagiAuthError(
            "Kagi served a bot challenge instead of results; the session token "
            "is missing, invalid or expired"
        )

    html = response.text
    if looks_unauthenticated(html):
        raise KagiAuthError("invalid or expired Kagi session token")

    results = parse_search_results(html)
    if limit is not None:
        results = results[:limit]
    return results


def looks_challenged(final_url: str) -> bool:
    """Whether Kagi redirected to its bot/turnstile challenge page."""
    return "/turnstile" in final_url


def looks_unauthenticated(html: str) -> bool:
    """Whether the page is Kagi's logged-out landing page."""
    return all(marker in html for marker in UNAUTHENTICATED_MARKERS)


def parse_search_results(html: str) -> list[SearchResult]:
    """Parse a Kagi results page into ranked results."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for element in soup.select(".search-result"):
        result = extract_result(element, ".__sri_title_link")
        if result is not None:
            results.append(result)

    for element in soup.select(".sr-group .__srgi"):
        result = extract_result(element, ".__srgi-title a")
        if result is not None:
            results.append(result)

    for rank, result in enumerate(results, start=1):
        result["rank"] = rank

    return results


def extract_result(element, title_selector: str) -> SearchResult | None:
    """Extract one result from a ``.search-result`` or ``.__srgi`` element."""
    title_link = element.select_one(title_selector)
    if title_link is None:
        return None

    title = collapse_whitespace(title_link.get_text(" ", strip=True))
    url = (title_link.get("href") or "").strip()
    if not title or not url:
        return None

    published = None
    snippet = ""

    desc = element.select_one(".__sri-desc")
    if desc is not None:
        time_node = desc.select_one(".__sri-time")
        if time_node is not None:
            published = parse_iso_date(time_node.get_text())
            # A parsed absolute date is stripped from the snippet; a relative
            # date (published is None) stays in the snippet text.
            if published is not None:
                time_node.extract()

        for link in desc.select(".summarize-link"):
            link.extract()

        snippet = collapse_whitespace(desc.get_text(" ", strip=True))

    return {
        "rank": None,
        "url": url,
        "title": title,
        "snippet": snippet,
        "published": published,
    }


def parse_iso_date(text: str) -> str | None:
    """Convert a result date like ``Oct 4, 2026`` to ``2026-10-04T00:00:00Z``.

    Relative labels such as ``Yesterday`` return ``None`` (they stay in the
    snippet).
    """
    parsed = parse_dates.single(text)
    return f"{parsed}T00:00:00Z" if parsed else None


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())
