"""Token estimation and model pricing."""

from __future__ import annotations

from dataclasses import dataclass

CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD = 4


def count_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN + MESSAGE_OVERHEAD


@dataclass(frozen=True)
class ModelPricing:
    input: float
    output: float
    cache_write: float
    cache_read: float

    # Minimum prefix size (in tokens) for caching to kick in.
    min_cache_prefix: int = 1024


SONNET = ModelPricing(
    input=3.00, output=15.00, cache_write=3.75, cache_read=0.30,
    min_cache_prefix=1024,
)
OPUS = ModelPricing(
    input=5.00, output=25.00, cache_write=6.25, cache_read=0.50,
    min_cache_prefix=2048,
)


def cost(tokens: int, rate: float) -> float:
    """Cost in dollars for *tokens* at *rate* per 1M tokens."""
    return tokens * rate / 1_000_000
