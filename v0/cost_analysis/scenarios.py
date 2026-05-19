"""Simulation parameters and scenario definitions."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import VILLAGERS, LOCATIONS

N_VILLAGERS = len(VILLAGERS)  # 8
N_LOCATIONS = len(LOCATIONS)  # 5
PHASES = 3


@dataclass(frozen=True)
class ConversationGroup:
    """Expected conversations per day with a specific group size."""
    size: int
    per_day: float
    turns: int


@dataclass(frozen=True)
class SimParams:
    """All tunable assumptions in one place."""
    name: str
    conversations: list[ConversationGroup]
    out_location: int
    out_rating: int
    out_speaking: int
    out_memory: int

    @property
    def total_convs_per_day(self) -> float:
        return sum(c.per_day for c in self.conversations)

    @property
    def total_villagers_in_convs_per_day(self) -> float:
        return sum(c.size * c.per_day for c in self.conversations)


def _uniform_conversations() -> list[ConversationGroup]:
    """Derive conversation distribution from the binomial occupancy model."""
    p = 1 / N_LOCATIONS
    groups = []
    for k in range(2, N_VILLAGERS + 1):
        pmf = comb(N_VILLAGERS, k) * (p ** k) * ((1 - p) ** (N_VILLAGERS - k))
        per_day = PHASES * N_LOCATIONS * pmf
        if per_day:
            groups.append(ConversationGroup(size=k, per_day=per_day, turns=10))
    return groups


def _observed_conversations() -> list[ConversationGroup]:
    """Actual day 1 conversations, used as the expected-value model."""
    return [
        ConversationGroup(size=5, per_day=2, turns=20),
        ConversationGroup(size=3, per_day=2, turns=20),
        ConversationGroup(size=2, per_day=1, turns=10),
    ]


UNIFORM_PARAMS = SimParams(
    name="Uniform-random (original model)",
    conversations=_uniform_conversations(),
    out_location=10,
    out_rating=5,
    out_speaking=60,
    out_memory=80,
)

OBSERVED_PARAMS = SimParams(
    name="Observed (day 1 transcript)",
    conversations=_observed_conversations(),
    out_location=10,
    out_rating=5,
    out_speaking=77,
    out_memory=250,
)
