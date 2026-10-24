from __future__ import annotations

import json
import re

from born_portal import llm
from born_portal.event.biletto import parse_biletto
from born_portal.event.instagram import parse_instagram
from born_portal.event.model import EventData
from born_portal.utils import date_range
from born_portal.utils.fetch import fetch_public_html, html_to_markdown


async def parse(url: str, debug: bool = False) -> EventData:
    page = await fetch_public_html(url)
    clean_url = page.url
    hostname = page.hostname
    html = page.html

    if debug:
        print(f"Fetched HTML from {clean_url}:\n{html}\n")

    if hostname == "billetto.se":
        return parse_biletto(html)

    if hostname.endswith("instagram.com"):
        return await parse_instagram(html, clean_url)

    markdown = html_to_markdown(html)

    response = await llm.completions(
        messages=[
            {
                "role": "system",
                "content": "Extract name, location, date/time, price and description as JSON",
            },
            {"role": "user", "content": markdown},
        ]
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


def _extract_response_text(response) -> str:
    if response.choices:
        return response.choices[0].message.content or ""
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
