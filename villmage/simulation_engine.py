# pyre-strict

"""Simulation-engine shell that owns startup state and heap primitives."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from dataclasses import replace
from enum import Enum
from heapq import heapify, heappush
from typing import Awaitable, Callable, Protocol, cast

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from memory_system.types import (
    CompactionReason,
    EventLogEntry,
    EventType,
    MemorySnapshot,
    VillagerId as MemoryVillagerId,
)
from observability.types import (
    VillagerMemoryCheckpoint,
    _autobalance_from_dict,
    _autobalance_to_dict,
    _require_dict,
    _require_list,
    _scheduled_event_from_dict,
    _scheduled_event_to_dict,
    _villager_state_from_dict,
    _villager_state_to_dict,
    _world_state_from_dict,
    _world_state_to_dict,
)
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.autobalance import AutobalanceMultipliers
from villmage.events import (
    ActionCompleteEvent,
    CarcassRotEvent,
    CheckpointEvent,
    FireExtinctionEvent,
    MidnightEvent,
    ScheduledEvent,
    VillagerId,
)
from villmage.game_types import ActionCategory, ItemType
from action_system.types import ActionType, SelectedAction
from villmage.villager_state import CurrentAction, DecayResult, VillagerState
from villmage.world_state import WorldState


class _ActionSystemProtocol(Protocol):
    """Action-system surface needed by the simulation engine."""

    def complete_action(self, villager_id: VillagerId) -> None:
        """Apply completion effects for the villager's current action."""

    def start_action(self, villager_id: VillagerId, action: SelectedAction) -> int:
        """Start one action and return its completion timestamp."""


class _SleepAdjustingActionSystemProtocol(Protocol):
    """Action-system surface needed for fire-state sleep adjustments."""

    def adjust_active_sleep(self, villager_id: VillagerId) -> None:
        """Split one active sleep segment under the current fire modifier."""


class CrossingType(Enum):
    """Threshold categories emitted by engine-level decay handling."""

    HEALTH_ZERO = 1
    WAKEFULNESS_ZERO = 2


class _CheckpointDependencyPlaceholder:
    """Raise a clear error if an unloaded runtime dependency is used."""

    def __init__(self, dependency_name: str) -> None:
        """Store the missing dependency's stable display name."""

        self._dependency_name = dependency_name

    def __getattr__(self, attribute_name: str) -> object:
        """Reject runtime use until the dependency is reattached explicitly."""

        raise RuntimeError(
            f"{self._dependency_name}.{attribute_name} is unavailable on a "
            "checkpoint-loaded SimulationEngine."
        )


class _CheckpointMemorySystem:
    """Hold restored memory state when a full MemorySystem cannot be rebuilt."""

    def __init__(self, snapshot: MemorySnapshot) -> None:
        """Store the full checkpoint-restored memory snapshot."""

        self._snapshot = snapshot

    def trigger_snapshot(self) -> MemorySnapshot:
        """Return the stored checkpoint snapshot."""

        return self._snapshot

    def get_full_state(self) -> MemorySnapshot:
        """Return the stored checkpoint snapshot."""

        return self._snapshot


def _memory_snapshot_to_checkpoints(
    snapshot: MemorySnapshot,
) -> list[VillagerMemoryCheckpoint]:
    """Convert one in-memory memory snapshot into checkpoint rows."""

    return [
        VillagerMemoryCheckpoint(
            villager_id=str(villager_id),
            short_term_memories=list(snapshot.short_term_memories.get(villager_id, [])),
            medium_term_memories=list(snapshot.medium_term_memories.get(villager_id, [])),
            long_term_memories=list(snapshot.long_term_memories.get(villager_id, [])),
            active_context_log=list(snapshot.active_context_log.get(villager_id, [])),
            relationships=dict(snapshot.relationships.get(villager_id, {})),
            last_long_term_compaction_day=snapshot.last_long_term_compaction_day,
        )
        for villager_id in snapshot.active_context_log
    ]


def _memory_snapshot_from_checkpoints(
    checkpoints: list[VillagerMemoryCheckpoint],
) -> MemorySnapshot:
    """Convert persisted per-villager memory rows into one typed snapshot."""

    return MemorySnapshot(
        active_context_log={
            MemoryVillagerId(checkpoint.villager_id): list(checkpoint.active_context_log)
            for checkpoint in checkpoints
        },
        short_term_memories={
            MemoryVillagerId(checkpoint.villager_id): list(checkpoint.short_term_memories)
            for checkpoint in checkpoints
        },
        medium_term_memories={
            MemoryVillagerId(checkpoint.villager_id): list(checkpoint.medium_term_memories)
            for checkpoint in checkpoints
        },
        long_term_memories={
            MemoryVillagerId(checkpoint.villager_id): list(checkpoint.long_term_memories)
            for checkpoint in checkpoints
        },
        relationships={
            MemoryVillagerId(checkpoint.villager_id): {
                MemoryVillagerId(subject_id): record
                for subject_id, record in checkpoint.relationships.items()
            }
            for checkpoint in checkpoints
        },
        last_long_term_compaction_day=(
            -1
            if len(checkpoints) == 0
            else checkpoints[0].last_long_term_compaction_day
        ),
    )


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
    checkpoint_dir: Path

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
        self.checkpoint_dir = Path("checkpoints")
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
        self._append_base_awake_event(death_event)

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

    def _handle_fire_extinction(self) -> None:
        """Mark the fire out and resplit every living villager's active sleep."""

        self.world_state.mark_fire_extinguished()
        action_system = cast(
            _SleepAdjustingActionSystemProtocol,
            self.action_system,
        )
        for villager_id, villager_state in self.villager_states.items():
            current_action = villager_state.current_action
            if (
                current_action is not None
                and current_action.category is ActionCategory.SLEEPING
            ):
                action_system.adjust_active_sleep(villager_id)

    def _append_base_awake_event(self, entry: EventLogEntry) -> None:
        """Append one base event for every villager who is both present and awake."""

        for villager_id, villager_state in self.villager_states.items():
            current_action = villager_state.current_action
            is_awake = (
                current_action is None
                or current_action.category is not ActionCategory.SLEEPING
            )
            is_at_base = (
                current_action is None or not current_action.category.is_away
            )
            if is_awake and is_at_base:
                self.memory_system.append_event(
                    MemoryVillagerId(villager_id),
                    entry,
                )

    def _handle_carcass_rot(self, event: CarcassRotEvent) -> None:
        """Remove one rotted carcass and notify base awake villagers."""

        self.world_state.mark_carcass_rotted(event.carcass_id)
        rot_event = EventLogEntry(
            game_time=self.current_game_time,
            type=EventType.BASE_EVENT,
            text=f"Carcass {event.carcass_id} rotted away.",
        )
        self._append_base_awake_event(rot_event)

    def _trigger_short_term_compaction(
        self,
        villager_id: VillagerId,
        reason: CompactionReason,
    ) -> None:
        """Run one per-villager short-term compaction to completion."""

        self._resolve_awaitable(
            self.memory_system.trigger_short_term_compaction(
                MemoryVillagerId(villager_id),
                self.current_game_time,
                reason,
            )
        )

    def _handle_action_complete(
        self,
        event: ActionCompleteEvent,
        crossings: list[CrossingType] | None = None,
    ) -> None:
        """Complete the prior action, compact memory if needed, and start the next."""

        villager_id = event.villager_id
        villager_state = self.villager_states.get(villager_id)
        if villager_state is None:
            return

        if villager_state.current_action is not None:
            self.action_system.complete_action(villager_id)

        effective_crossings = [] if crossings is None else crossings
        if self._apply_thresholds(villager_id, effective_crossings):
            return

        compaction_ran = False
        if villager_state.awake_minutes_since_compaction >= 240:
            self._trigger_short_term_compaction(
                villager_id,
                CompactionReason.AWAKE_THRESHOLD,
            )
            villager_state.reset_compaction_counter()
            compaction_ran = True

        selection = self.ai_coordinator.select_action(
            villager_id,
            self.current_game_time,
        )
        if selection.thought is not None:
            self.memory_system.append_thought(
                MemoryVillagerId(villager_id),
                self.current_game_time,
                selection.thought,
            )

        if (
            selection.action.action_type is ActionType.GO_TO_SLEEP
            and not compaction_ran
        ):
            self._trigger_short_term_compaction(villager_id, CompactionReason.SLEEP)

        target_id = selection.action.target_villager_id
        if selection.action.action_type is ActionType.TALK_TO:
            if target_id is None:
                raise ValueError("Talk-to action requires target_villager_id.")
            self._handle_conversation_action(villager_id, target_id)
            return

        completion_timestamp = self.action_system.start_action(
            villager_id,
            selection.action,
        )
        self._push(
            ActionCompleteEvent(
                timestamp=completion_timestamp,
                sequence=-1,
                villager_id=villager_id,
            )
        )

    def _handle_conversation_action(
        self,
        initiator_id: VillagerId,
        target_id: VillagerId,
    ) -> None:
        """Run the authored conversation branch once it is implemented."""

        del initiator_id, target_id
        raise NotImplementedError("Conversation handling is implemented in the next diff.")

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

    def _handle_checkpoint(self) -> None:
        """Persist one full engine snapshot and schedule the next checkpoint."""

        self._cancel(
            lambda event: isinstance(event, CheckpointEvent)
            and event.timestamp == self.current_game_time
        )
        memory_snapshot = self.memory_system.get_full_state()
        payload = {
            "villager_states": [
                _villager_state_to_dict(state)
                for state in self.villager_states.values()
            ],
            "world_state": _world_state_to_dict(self.world_state),
            "memory_state": [
                checkpoint.to_dict()
                for checkpoint in _memory_snapshot_to_checkpoints(memory_snapshot)
            ],
            "autobalance": _autobalance_to_dict(self.autobalance),
            "event_heap": [
                _scheduled_event_to_dict(event) for event in self.event_heap
            ],
            "current_game_time": self.current_game_time,
        }
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = self.checkpoint_dir / f"{self.current_game_time}.json"
        with checkpoint_path.open("w", encoding="utf-8") as checkpoint_file:
            json.dump(payload, checkpoint_file, indent=2, sort_keys=True)
            checkpoint_file.write("\n")
        self._push(
            CheckpointEvent(
                timestamp=self.current_game_time + 180,
                sequence=-1,
            )
        )

    @classmethod
    def load_checkpoint(cls, path: Path) -> SimulationEngine:
        """Reconstruct one engine shell from a checkpoint file."""

        with path.open("r", encoding="utf-8") as checkpoint_file:
            data = _require_dict(json.load(checkpoint_file))

        engine = cls.__new__(cls)
        engine.current_game_time = int(data["current_game_time"])
        engine.event_heap = [
            _scheduled_event_from_dict(_require_dict(event))
            for event in _require_list(data["event_heap"])
        ]
        heapify(engine.event_heap)
        engine.next_sequence = (
            0 if len(engine.event_heap) == 0 else max(event.sequence for event in engine.event_heap) + 1
        )
        engine.autobalance = _autobalance_from_dict(_require_dict(data["autobalance"]))
        engine.villager_states = {
            state.villager_id: state
            for state in [
                _villager_state_from_dict(_require_dict(raw_state))
                for raw_state in _require_list(data["villager_states"])
            ]
        }
        engine.world_state = _world_state_from_dict(_require_dict(data["world_state"]))
        memory_snapshot = _memory_snapshot_from_checkpoints(
            [
                VillagerMemoryCheckpoint.from_dict(_require_dict(raw_state))
                for raw_state in _require_list(data["memory_state"])
            ]
        )
        engine.memory_system = cast(
            MemorySystem,
            _CheckpointMemorySystem(memory_snapshot),
        )
        engine.character_canon = CharacterCanon()
        engine.action_system = cast(
            _ActionSystemProtocol,
            _CheckpointDependencyPlaceholder("action_system"),
        )
        engine.ai_coordinator = cast(
            AICoordinator,
            _CheckpointDependencyPlaceholder("ai_coordinator"),
        )
        engine.conversation_system = cast(
            ConversationSystem,
            _CheckpointDependencyPlaceholder("conversation_system"),
        )
        engine.checkpoint_dir = path.parent
        if not any(isinstance(event, CheckpointEvent) for event in engine.event_heap):
            engine._push(
                CheckpointEvent(
                    timestamp=engine.current_game_time + 180,
                    sequence=-1,
                )
            )
        return engine
