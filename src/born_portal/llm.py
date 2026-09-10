from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from born_portal.core import API_KEY, API_URL, BASE_URL, MODEL


@lru_cache(maxsize=1)
def client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=API_KEY,
        base_url=API_URL,
        default_headers={
            "HTTP-Referer": BASE_URL,
            "X-Title": "Portal",
        },
    )


async def completions(
    messages: Iterable[ChatCompletionMessageParam], max_tokens: int = 1024
) -> Any:
    if not API_KEY:
        raise ValueError("API_KEY environment variable is not set")
    if not MODEL:
        raise ValueError("MODEL environment variable is not set")
    return await client().chat.completions.create(
        messages=messages,
        model=MODEL,
        max_tokens=max_tokens,
    )
