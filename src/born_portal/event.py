from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import markdownify
import httpx
from litellm import completion

DEFAULT_MODEL = "ollama/gemma4"
DEFAULT_API_BASE = "http://localhost:11434"


@dataclass
class EventData:
    name: str
    description: str
    price: Optional[str] = None
    date: Optional[str] = None


def html_to_markdown(html: str) -> str:
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


async def parse(url: str) -> EventData:
    html = await fetch_html(url)
    markdown = html_to_markdown(html)

    model = os.environ.get("MODEL", DEFAULT_MODEL)
    api_base = os.environ.get("API_BASE", DEFAULT_API_BASE)

    response = completion(
        model=model,
        messages=[
            {"role": "user", "content": markdown},
            {
                "role": "user",
                "content": "The markdown content contains information about an event (possibly in swedish). "
                "Please detect/infer the name, description, price and date and return as json.",
            },
        ],
        api_base=api_base,
        temperature=0.0,
        max_tokens=1024,
    )

    print(response)

    content = _extract_response_text(response)
    parsed = _parse_json_output(content)

    return EventData(
        name=(parsed["name"] or "").strip(),
        description=(parsed["description"] or "").strip(),
        price=(parsed["price"] or None),
        date=(parsed["date"] or None),
    )


async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
