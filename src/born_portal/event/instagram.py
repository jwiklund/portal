from __future__ import annotations

import base64
import html
import re

import httpx2

from born_portal import llm
from born_portal.event.model import EventData


async def parse_instagram(html_content: str, url: str) -> EventData:
    from born_portal.event.event import _extract_response_text, _parse_json_output

    image_url = _meta(html_content, "og:image")
    title = _meta(html_content, "og:title")
    description = _meta(html_content, "og:description")

    if not image_url:
        raise ValueError("No image found in Instagram post")

    image_b64 = await _fetch_image_base64(image_url)

    text = (
        "Extract the event name, location, date/time, price and description "
        "from this Instagram post as JSON."
    )
    if title:
        text += f"\n\nTitle: {title}"
    if description:
        text += f"\n\nDescription: {description}"

    response = await llm.completions(
        messages=[
            {
                "role": "system",
                "content": "Extract name, location, date/time, price and description as JSON",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ]
    )

    content = _extract_response_text(response)
    parsed = _parse_json_output(content)

    return EventData(
        url=url,
        name=(parsed.get("name") or "").strip(),
        description=(parsed.get("description") or "").strip(),
        location=(parsed.get("location") or None),
        price=(parsed.get("price") or None),
        date=(parsed.get("date") or None),
    )


def _meta(html_content: str, name: str) -> str | None:
    for pattern in (
        rf'<meta[^>]*?(?:property|name)="{re.escape(name)}"[^>]*?content="([^"]*)"',
        rf'<meta[^>]*?content="([^"]*)"[^>]*?(?:property|name)="{re.escape(name)}"',
    ):
        match = re.search(pattern, html_content)
        if match:
            value = html.unescape(match.group(1)).strip()
            return value or None
    return None


async def _fetch_image_base64(image_url: str) -> str:
    async with httpx2.AsyncClient(timeout=30.0) as client:
        response = await client.get(image_url)
        response.raise_for_status()
        return base64.b64encode(response.content).decode()
