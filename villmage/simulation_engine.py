# pyre-strict

"""Simulation-engine shell that owns startup state and heap primitives."""

from __future__ import annotations

from dataclasses import replace
from heapq import heapify, heappush
from typing import Callable, Protocol

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.autobalance import AutobalanceMultipliers
from villmage.events import (
    ActionCompleteEvent,
    CheckpointEvent,
    MidnightEvent,
    ScheduledEvent,
)
from villmage.villager_state import VillagerState
from villmage.world_state import WorldState


class _ActionSystemProtocol(Protocol):
    """Marker protocol for the action-system API reference owned by the engine."""


class SimulationEngine:
    """Own startup simulation state plus event-heap helpers."""

    current_game_time: int
    event_heap: list[ScheduledEvent]
    next_sequence: int
    autobalance: AutobalanceMultipliers
    villager_states: dict[str, VillagerState]
    world_state: WorldState
    action_system: _ActionSystemProtocol
    ai_coordinator: AICoordinator
    conversation_system: ConversationSystem
    memory_system: MemorySystem
    character_canon: CharacterCanon

    def __init__(
        self,
        character_canon: CharacterCanon,
        action_system: _ActionSystemProtocol,
        ai_coordinator: AICoordinator,
        conversation_system: ConversationSystem,
        memory_system: MemorySystem,
    ) -> None:
        """Initialize the authored Day 1 6:00 AM starting simulation state."""

        self.current_game_time = 360
        self.event_heap = []
        self.next_sequence = 0
        self.character_canon = character_canon
        self.action_system = action_system
        self.ai_coordinator = ai_coordinator
        self.conversation_system = conversation_system
        self.memory_system = memory_system
        self.autobalance = AutobalanceMultipliers()
        self.villager_states = {
            str(villager.id): VillagerState(str(villager.id))
            for villager in self.character_canon.get_all_villagers()
        }
        self.world_state = WorldState()

        for villager_id in self.villager_states:
            self._push(
                ActionCompleteEvent(
                    timestamp=self.current_game_time,
                    sequence=-1,
                    villager_id=villager_id,
                )
            )
        self._push(MidnightEvent(timestamp=1440, sequence=-1))
        self._push(CheckpointEvent(timestamp=540, sequence=-1))

    def _push(self, event: ScheduledEvent) -> None:
        """Stamp one monotone sequence number and push the event onto the heap."""

        stamped_event = replace(event, sequence=self.next_sequence)
        heappush(self.event_heap, stamped_event)
        self.next_sequence += 1

    def _cancel(self, predicate: Callable[[ScheduledEvent], bool]) -> None:
        """Remove all matching heap entries and restore heap ordering."""

        self.event_heap = [
            event for event in self.event_heap if not predicate(event)
        ]
        heapify(self.event_heap)
