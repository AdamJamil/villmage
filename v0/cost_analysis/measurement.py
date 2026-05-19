"""Token measurement using real transcript data."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from itertools import cycle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import VILLAGERS, LOCATIONS, Villager

from cost_analysis.pricing import count_tokens
from cost_analysis.scenarios import PHASES
from cost_analysis.transcript import load_history_lines, load_memories

from prompts import (
    system_prompt,
    location_choice_user,
    rating_shared,
    rating_character,
    speaking_character,
    memory_save_user,
)


@dataclass(frozen=True)
class TokenMeasurement:
    sys_tokens: int
    loc_user_tokens: int
    shared_tokens_by_turn: list[int]
    avg_shared: int
    rating_char_tokens: int
    speaking_char_tokens: int
    mem_user_tokens: int
    avg_char_tokens: int
    min_char_tokens: int
    max_char_tokens: int


def _get_memories_for_day(day: int) -> list[str]:
    """Get memories for token measurement.

    Uses real memories from the earliest transcript, cycling through them
    if more are needed for multi-day projections.
    """
    n_memories = max(0, (day - 1) * PHASES)
    if n_memories == 0:
        return []

    real_memories = load_memories()
    if not real_memories:
        return []

    # Cycle through real memories to fill the needed count
    return [m for m, _ in zip(cycle(real_memories), range(n_memories))]


def measure_tokens(day: int, avg_turns: int) -> TokenMeasurement:
    """Measure token sizes using real prompt templates and transcript data."""
    villager = VILLAGERS[0]
    memories = _get_memories_for_day(day)
    villager_with_mem = Villager(
        name=villager.name,
        description=villager.description,
        memories=memories,
    )

    sys_tokens = count_tokens(system_prompt())
    loc_user_tokens = count_tokens(
        location_choice_user(villager_with_mem, day, "morning", LOCATIONS)
    )

    # Use real dialogue from the earliest transcript
    history_lines = load_history_lines()

    all_names = ["Pell Arenway", "Sable Dunmore", "Denn Corvale", "Orla Fenn", "Ham Birch"]
    location = LOCATIONS[0]

    shared_tokens_by_turn: list[int] = []
    for t in range(avg_turns):
        history = history_lines[:t]
        shared_text = rating_shared(day, "morning", location, all_names, history)
        shared_tokens_by_turn.append(count_tokens(shared_text))

    full_history = history_lines[:avg_turns]
    mem_user_tokens = count_tokens(
        memory_save_user(villager_with_mem, day, "morning", location, full_history)
    )

    all_rating_tokens = []
    all_speaking_tokens = []
    for v in VILLAGERS:
        v_with_mem = Villager(name=v.name, description=v.description, memories=memories)
        all_rating_tokens.append(count_tokens(rating_character(v_with_mem)))
        all_speaking_tokens.append(count_tokens(speaking_character(v_with_mem)))

    avg_rating = sum(all_rating_tokens) // len(all_rating_tokens)
    return TokenMeasurement(
        sys_tokens=sys_tokens,
        loc_user_tokens=loc_user_tokens,
        shared_tokens_by_turn=shared_tokens_by_turn,
        avg_shared=sum(shared_tokens_by_turn) // len(shared_tokens_by_turn),
        rating_char_tokens=avg_rating,
        speaking_char_tokens=sum(all_speaking_tokens) // len(all_speaking_tokens),
        mem_user_tokens=mem_user_tokens,
        avg_char_tokens=avg_rating,
        min_char_tokens=min(all_rating_tokens),
        max_char_tokens=max(all_rating_tokens),
    )
