from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import markdownify

from born_portal.event.biletto import parse_biletto
from born_portal.model import EventData

_model = os.environ.get("MODEL")


async def parse(url: str) -> EventData:
    from litellm import acompletion

    html = await _fetch_html(_clean_url(url))
    if url.startswith("https://billetto.se/"):
        return parse_biletto(html)

    markdown = _html_to_markdown(html)

    response = await acompletion(
        messages=[
            {
                "role": "system",
                "content": "Extract name, location, date/time, cost and description as JSON",
            },
            {"role": "user", "content": markdown},
        ],
        model=_model,
        max_tokens=1024,
    )

    content = _extract_response_text(response)
    parsed = _parse_json_output(content)

    return EventData(
        name=(parsed["name"] or "").strip(),
        description=(parsed["description"] or "").strip(),
        location=(parsed["location"] or None),
        price=(parsed["price"] or None),
        date=(parsed["date"] or None),
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
    async with httpx.AsyncClient(timeout=30.0) as client:
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


def _parse_json_output(raw: str) -> dict[str, Optional[str]]:
    print(raw)

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
    return {
        "name": data.get("name"),
        "description": data.get("description"),
        "price": data.get("price"),
        "date": data.get("date"),
    }
