from __future__ import annotations

import json
import os
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import markdownify

from born_portal.event.biletto import parse_biletto
from born_portal.event.model import EventData
from born_portal.utils import date_range

_model = os.environ.get("MODEL")

FIREFOX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
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


async def parse(url: str) -> EventData:
    from litellm import acompletion

    clean_url = _clean_url(url)
    html = await _fetch_html(clean_url)
    if url.startswith("https://billetto.se/"):
        return parse_biletto(html)

    markdown = _html_to_markdown(html)

    if not _model:
        raise ValueError("MODEL environment variable is not set")

    response = await acompletion(
        messages=[
            {
                "role": "system",
                "content": "Extract name, location, date/time, price and description as JSON",
            },
            {"role": "user", "content": markdown},
        ],
        model=_model,
        max_tokens=1024,
    )

    content = _extract_response_text(response)
    parsed = _parse_json_output(content)

    return EventData(
        url=clean_url,
        name=(parsed.get("name") or "").strip(),
        description=(parsed.get("description") or "").strip(),
        location=(parsed.get("location") or None),
        price=(parsed.get("price") or None),
        date=(parsed.get("date") or None),
    )


def _clean_url(url: str) -> str:
    parsed = urlparse(url)

    params = {
        key: value
        for key, value in parse_qs(parsed.query).items()
        if not key.startswith("utm_")
    }
    new_query = urlencode(params, doseq=True)
    filtered_url = urlunparse(parsed._replace(query=new_query))
    return filtered_url


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=30.0, headers=FIREFOX_HEADERS) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def _html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown using markdownify."""
    return markdownify.markdownify(html, heading_style="ATX").strip()


def _extract_response_text(response) -> str:
    if hasattr(response, "choices") and response.choices:
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        if message is not None:
            return getattr(message, "content", "") or ""
    if hasattr(response, "text"):
        return response.text
    return str(response)


def _parse_json_output(raw: str) -> dict[str, str | None]:
    raw = raw.strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw[len("```json") : -len("```")].strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = raw[3:-3].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract a JSON object inside the response.
        match = re.search(r"(\{(?:.|\n)*\})", raw)
        if match:
            data = json.loads(match.group(1))
        else:
            raise
    date = None
    for key, value in data.items():
        if key.startswith("date"):
            date = date_range.parse_date_range(value)
    return {
        "name": data.get("name"),
        "description": data.get("description"),
        "location": data.get("location"),
        "price": data.get("price"),
        "date": date,
    }
