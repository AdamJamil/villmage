# pyre-strict

"""Simulation-engine shell that owns startup state and heap primitives."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from enum import Enum
from heapq import heapify, heappush
from typing import Awaitable, Callable, Protocol, cast

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from memory_system.types import (
    EventLogEntry,
    EventType,
    VillagerId as MemoryVillagerId,
)
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.autobalance import AutobalanceMultipliers
from villmage.events import (
    ActionCompleteEvent,
    CheckpointEvent,
    FireExtinctionEvent,
    MidnightEvent,
    ScheduledEvent,
    VillagerId,
)
from villmage.game_types import ActionCategory
from villmage.game_types import ItemType
from villmage.villager_state import CurrentAction, DecayResult, VillagerState
from villmage.world_state import WorldState


class _ActionSystemProtocol(Protocol):
    """Marker protocol for the action-system API reference owned by the engine."""


class CrossingType(Enum):
    """Threshold categories emitted by engine-level decay handling."""

    HEALTH_ZERO = 1
    WAKEFULNESS_ZERO = 2


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

    @staticmethod
    def _to_crossings(decay_result: DecayResult) -> list[CrossingType]:
        """Translate one decay-result bundle into ordered threshold crossings."""

        crossings: list[CrossingType] = []
        if decay_result.health_zero:
            crossings.append(CrossingType.HEALTH_ZERO)
        if decay_result.wakefulness_zero:
            crossings.append(CrossingType.WAKEFULNESS_ZERO)
        return crossings

    def _apply_decay_all(self, elapsed_hours: float) -> dict[VillagerId, list[CrossingType]]:
        """Apply decay to every living villager and return only threshold crossings."""

        threshold_crossings: dict[VillagerId, list[CrossingType]] = {}
        for villager_id, villager_state in self.villager_states.items():
            crossings = self._to_crossings(villager_state.apply_decay(elapsed_hours))
            if crossings:
                threshold_crossings[villager_id] = crossings
        return threshold_crossings

    def _apply_thresholds(
        self,
        villager_id: VillagerId,
        crossings: list[CrossingType],
    ) -> bool:
        """Apply death and forced-sleep thresholds in authored precedence order."""

        if CrossingType.HEALTH_ZERO in crossings:
            self._kill_villager(villager_id)
            return True
        if CrossingType.WAKEFULNESS_ZERO in crossings:
            self._force_sleep(villager_id)
            return True
        return False

    def _force_sleep(self, villager_id: VillagerId) -> None:
        """Cancel pending work, set forced sleep, and schedule wake-up in 4 hours."""

        self._cancel(
            lambda event: isinstance(event, ActionCompleteEvent)
            and event.villager_id == villager_id
        )
        villager_state = self.villager_states[villager_id]
        forced_sleep_end = self.current_game_time + 240
        villager_state.set_current_action(
            CurrentAction(
                category=ActionCategory.SLEEPING,
                detail=None,
                completion_timestamp=forced_sleep_end,
            )
        )
        self._push(
            ActionCompleteEvent(
                timestamp=forced_sleep_end,
                sequence=-1,
                villager_id=villager_id,
            )
        )

    def _kill_villager(self, villager_id: VillagerId) -> None:
        """Cancel pending work, remove the villager, and notify base awake observers."""

        self._cancel(
            lambda event: isinstance(event, ActionCompleteEvent)
            and event.villager_id == villager_id
        )
        villager_state = self.villager_states[villager_id]
        villager_state.inventory.clear()
        villager_state.is_alive = False
        del self.villager_states[villager_id]

        death_event = EventLogEntry(
            game_time=self.current_game_time,
            type=EventType.BASE_EVENT,
            text=f"{villager_id} died.",
        )
        for observer_id, observer_state in self.villager_states.items():
            current_action = observer_state.current_action
            is_awake = (
                current_action is None
                or current_action.category is not ActionCategory.SLEEPING
            )
            is_at_base = (
                current_action is None or not current_action.category.is_away
            )
            if is_awake and is_at_base:
                self.memory_system.append_event(
                    MemoryVillagerId(observer_id),
                    death_event,
                )

    def _sync_fire_event(self) -> None:
        """Reconcile the heap fire-extinction event with WorldState's fire snapshot."""

        self._cancel(lambda event: isinstance(event, FireExtinctionEvent))
        extinction_timestamp = self.world_state.fire.extinction_timestamp
        if self.world_state.fire.lit and extinction_timestamp is not None:
            self._push(
                FireExtinctionEvent(
                    timestamp=extinction_timestamp,
                    sequence=-1,
                )
            )

    @staticmethod
    def _inventory_edible_calories(villager_state: VillagerState) -> int:
        """Return the edible calories currently carried by one villager."""

        peach_calories = villager_state.inventory.get(ItemType.PEACH, 0) * 60
        cooked_meat_calories = (
            villager_state.inventory.get(ItemType.COOKED_MEAT, 0) * 800
        )
        return peach_calories + cooked_meat_calories

    @staticmethod
    def _resolve_awaitable(result: object) -> object:
        """Run one awaitable result to completion and otherwise return it unchanged."""

        if inspect.isawaitable(result):
            return asyncio.run(cast(Awaitable[object], result))
        return result

    def _compute_autobalance_aggregates(self) -> tuple[float, float, float]:
        """Return average satiation, hydration, and food-safety aggregates."""

        living_villagers = list(self.villager_states.values())
        living_count = len(living_villagers)
        if living_count == 0:
            return (0.0, 0.0, 0.0)

        shared_base_calories = self.world_state.get_total_edible_calories()
        base_calorie_share = shared_base_calories / float(living_count)
        total_satiation_pct = 0.0
        total_hydration_pct = 0.0
        total_food_safety_days = 0.0

        for villager_state in living_villagers:
            total_satiation_pct += villager_state.satiation / 1800.0
            total_hydration_pct += villager_state.hydration / 6000.0
            inventory_calories = self._inventory_edible_calories(villager_state)
            total_food_safety_days += (
                (inventory_calories / 2200.0) + (base_calorie_share / 2200.0)
            ) / 5.0

        return (
            total_satiation_pct / float(living_count),
            total_hydration_pct / float(living_count),
            total_food_safety_days / float(living_count),
        )

    def _handle_midnight(self) -> None:
        """Run the midnight autobalance and compaction cycle."""

        threshold_crossings = self._apply_decay_all(0.0)
        for villager_id, crossings in threshold_crossings.items():
            self._apply_thresholds(villager_id, crossings)

        avg_satiation_pct, avg_hydration_pct, avg_food_safety_days = (
            self._compute_autobalance_aggregates()
        )
        self.autobalance.adjust(
            avg_satiation_pct,
            avg_hydration_pct,
            avg_food_safety_days,
        )
        self._resolve_awaitable(
            self.memory_system.trigger_midnight_compaction(
                current_game_time=self.current_game_time
            )
        )
        self._push(
            MidnightEvent(
                timestamp=self.current_game_time + 1440,
                sequence=-1,
            )
        )
