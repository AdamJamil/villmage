"""Gemini async client with API wrappers matching the prior anthropic interface."""

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


async def gemini_call(system: str, text: str, max_tokens: int = 256) -> str:
    client = get_client()
    resp = await client.aio.models.generate_content(
        model=MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (resp.text or "").strip()
