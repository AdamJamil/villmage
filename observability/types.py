# pyre-strict

"""On-disk observability schema types plus checkpoint persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import json
import os
from pathlib import Path

from memory_system.types import EventLogEntry, EventType, MemoryEntry, RelationshipRecord
from villmage.autobalance import AutobalanceMultipliers
from villmage.events import (
    ActionCompleteEvent,
    CarcassRotEvent,
    CheckpointEvent,
    FireExtinctionEvent,
    MidnightEvent,
    ScheduledEvent,
)
from villmage.game_types import (
    ActionCategory,
    CraftableItem,
    ItemType,
    RestingSpotType,
)
from villmage.villager_state import CraftingProgress, CurrentAction, VillagerState
from villmage.world_state import (
    Carcass,
    DirtinessSource,
    Fire,
    FuelType,
    FuelUnit,
    WorldState,
)


class DeltaKind(IntEnum):
    """Tagged delta variants written to the append-only JSONL stream."""

    VILLAGER_STATS = 1
    VILLAGER_INV = 2
    WORLD_STATE = 3
    MEMORY_UPDATE = 4


@dataclass(frozen=True)
class FieldChange:
    """One JSON-encoded before/after field transition."""

    field: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class DeltaRecord:
    """One tagged on-disk state delta."""

    game_time: int
    kind: DeltaKind
    villager_id: str | None = None
    changes: list[FieldChange] | None = None
    memory_kind: str | None = None
    content: str | None = None
    subject_id: str | None = None

    def __post_init__(self) -> None:
        """Enforce that exactly one payload group matches the record kind."""

        has_memory_payload = self.memory_kind is not None or self.content is not None
        if self.kind is DeltaKind.MEMORY_UPDATE:
            if self.villager_id is None or self.memory_kind is None or self.content is None:
                raise ValueError("MEMORY_UPDATE records require villager_id, memory_kind, and content.")
            if self.changes is not None:
                raise ValueError("MEMORY_UPDATE records must not include changes.")
            return
        if has_memory_payload or self.subject_id is not None:
            raise ValueError("Non-memory delta records must not include memory payload fields.")
        if self.changes is None or len(self.changes) == 0:
            raise ValueError("Non-memory delta records require at least one FieldChange.")
        if self.kind in {DeltaKind.VILLAGER_STATS, DeltaKind.VILLAGER_INV} and self.villager_id is None:
            raise ValueError("Villager delta records require villager_id.")
        if self.kind is DeltaKind.WORLD_STATE and self.villager_id is not None:
            raise ValueError("WORLD_STATE records must not include villager_id.")

    def to_dict(self) -> dict[str, object]:
        """Return the exact JSON-serializable delta payload."""

        data: dict[str, object] = {
            "game_time": self.game_time,
            "kind": int(self.kind),
        }
        if self.villager_id is not None:
            data["villager_id"] = self.villager_id
        if self.changes is not None:
            data["changes"] = [_field_change_to_dict(change) for change in self.changes]
        if self.memory_kind is not None:
            data["memory_kind"] = self.memory_kind
        if self.content is not None:
            data["content"] = self.content
        if self.subject_id is not None:
            data["subject_id"] = self.subject_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DeltaRecord:
        """Reconstruct one delta record from parsed JSON data."""

        changes_data = data.get("changes")
        changes = (
            None
            if changes_data is None
            else [_field_change_from_dict(_require_dict(entry)) for entry in _require_list(changes_data)]
        )
        return cls(
            game_time=_require_int(data["game_time"]),
            kind=DeltaKind(_require_int(data["kind"])),
            villager_id=_optional_str(data.get("villager_id")),
            changes=changes,
            memory_kind=_optional_str(data.get("memory_kind")),
            content=_optional_str(data.get("content")),
            subject_id=_optional_str(data.get("subject_id")),
        )


@dataclass(frozen=True)
class VillagerMemoryCheckpoint:
    """Complete persisted memory state for one villager."""

    villager_id: str
    short_term_memories: list[MemoryEntry]
    medium_term_memories: list[MemoryEntry]
    long_term_memories: list[MemoryEntry]
    active_context_log: list[EventLogEntry]
    relationships: dict[str, RelationshipRecord]
    last_long_term_compaction_day: int

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-serializable memory-checkpoint payload."""

        return {
            "villager_id": self.villager_id,
            "short_term_memories": [_memory_entry_to_dict(entry) for entry in self.short_term_memories],
            "medium_term_memories": [_memory_entry_to_dict(entry) for entry in self.medium_term_memories],
            "long_term_memories": [_memory_entry_to_dict(entry) for entry in self.long_term_memories],
            "active_context_log": [_event_log_entry_to_dict(entry) for entry in self.active_context_log],
            "relationships": {
                subject_id: _relationship_record_to_dict(record)
                for subject_id, record in self.relationships.items()
            },
            "last_long_term_compaction_day": self.last_long_term_compaction_day,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> VillagerMemoryCheckpoint:
        """Reconstruct one memory checkpoint from parsed JSON data."""

        return cls(
            villager_id=_require_str(data["villager_id"]),
            short_term_memories=[
                _memory_entry_from_dict(_require_dict(entry))
                for entry in _require_list(data["short_term_memories"])
            ],
            medium_term_memories=[
                _memory_entry_from_dict(_require_dict(entry))
                for entry in _require_list(data["medium_term_memories"])
            ],
            long_term_memories=[
                _memory_entry_from_dict(_require_dict(entry))
                for entry in _require_list(data["long_term_memories"])
            ],
            active_context_log=[
                _event_log_entry_from_dict(_require_dict(entry))
                for entry in _require_list(data["active_context_log"])
            ],
            relationships={
                subject_id: _relationship_record_from_dict(_require_dict(record))
                for subject_id, record in _require_dict(data["relationships"]).items()
            },
            last_long_term_compaction_day=_require_int(data["last_long_term_compaction_day"]),
        )


@dataclass(frozen=True)
class CheckpointRecord:
    """Complete machine-readable simulation snapshot."""

    game_time: int
    villager_states: list[VillagerState]
    world_state: WorldState
    memory_state: list[VillagerMemoryCheckpoint]
    autobalance: AutobalanceMultipliers
    event_heap: list[ScheduledEvent]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-serializable checkpoint payload."""

        return {
            "game_time": self.game_time,
            "villager_states": [_villager_state_to_dict(state) for state in self.villager_states],
            "world_state": _world_state_to_dict(self.world_state),
            "memory_state": [memory.to_dict() for memory in self.memory_state],
            "autobalance": _autobalance_to_dict(self.autobalance),
            "event_heap": [_scheduled_event_to_dict(event) for event in self.event_heap],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CheckpointRecord:
        """Reconstruct one checkpoint from parsed JSON data."""

        return cls(
            game_time=_require_int(data["game_time"]),
            villager_states=[
                _villager_state_from_dict(_require_dict(state))
                for state in _require_list(data["villager_states"])
            ],
            world_state=_world_state_from_dict(_require_dict(data["world_state"])),
            memory_state=[
                VillagerMemoryCheckpoint.from_dict(_require_dict(state))
                for state in _require_list(data["memory_state"])
            ],
            autobalance=_autobalance_from_dict(_require_dict(data["autobalance"])),
            event_heap=[
                _scheduled_event_from_dict(_require_dict(event))
                for event in _require_list(data["event_heap"])
            ],
        )


def append_delta(data_dir: Path, record: DeltaRecord) -> None:
    """Append one delta as a newline-terminated JSON object."""

    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / "state_deltas.jsonl"
    with output_path.open("a", encoding="utf-8") as output_file:
        output_file.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        output_file.flush()
        os.fsync(output_file.fileno())


def save_checkpoint(data_dir: Path, record: CheckpointRecord) -> None:
    """Write one checkpoint file using the zero-padded chronological filename."""

    checkpoint_dir = data_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    output_path = checkpoint_dir / f"{record.game_time:05d}.json"
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(record.to_dict(), output_file, indent=2, sort_keys=True)
        output_file.write("\n")


def load_checkpoint(data_dir: Path, game_time: int) -> CheckpointRecord:
    """Load one checkpoint file for a restart or replay base state."""

    input_path = data_dir / "checkpoints" / f"{game_time:05d}.json"
    with input_path.open("r", encoding="utf-8") as input_file:
        data: object = json.load(input_file)
    return CheckpointRecord.from_dict(_require_dict(data))


def _field_change_to_dict(change: FieldChange) -> dict[str, object]:
    """Serialize one field-change record."""

    return {
        "field": change.field,
        "old_value": change.old_value,
        "new_value": change.new_value,
    }


def _field_change_from_dict(data: dict[str, object]) -> FieldChange:
    """Deserialize one field-change record."""

    return FieldChange(
        field=_require_str(data["field"]),
        old_value=_require_str(data["old_value"]),
        new_value=_require_str(data["new_value"]),
    )


def _memory_entry_to_dict(entry: MemoryEntry) -> dict[str, object]:
    """Serialize one memory entry."""

    return {"game_time": entry.game_time, "text": entry.text}


def _memory_entry_from_dict(data: dict[str, object]) -> MemoryEntry:
    """Deserialize one memory entry."""

    return MemoryEntry(
        game_time=_require_int(data["game_time"]),
        text=_require_str(data["text"]),
    )


def _event_log_entry_to_dict(entry: EventLogEntry) -> dict[str, object]:
    """Serialize one event-log entry."""

    return {
        "game_time": entry.game_time,
        "type": entry.type.name,
        "text": entry.text,
    }


def _event_log_entry_from_dict(data: dict[str, object]) -> EventLogEntry:
    """Deserialize one event-log entry."""

    return EventLogEntry(
        game_time=_require_int(data["game_time"]),
        type=EventType[_require_str(data["type"])],
        text=_require_str(data["text"]),
    )


def _relationship_record_to_dict(record: RelationshipRecord) -> dict[str, object]:
    """Serialize one directional relationship record."""

    return {
        "description": record.description,
        "recent_impressions": list(record.recent_impressions),
    }


def _relationship_record_from_dict(data: dict[str, object]) -> RelationshipRecord:
    """Deserialize one directional relationship record."""

    return RelationshipRecord(
        description=_require_str(data["description"]),
        recent_impressions=[_require_str(value) for value in _require_list(data["recent_impressions"])],
    )


def _villager_state_to_dict(state: VillagerState) -> dict[str, object]:
    """Serialize one villager state snapshot."""

    return {
        "villager_id": state.villager_id,
        "wakefulness": state.wakefulness,
        "satiation": state.satiation,
        "hydration": state.hydration,
        "social_joy": state.social_joy,
        "connectedness": state.connectedness,
        "cleanliness": state.cleanliness,
        "inventory": {item.name: count for item, count in state.inventory.items()},
        "sleep_spot_claim": (
            None if state.sleep_spot_claim is None else state.sleep_spot_claim.name
        ),
        "crafting_in_progress": _crafting_progress_to_dict(state.crafting_in_progress),
        "cooking_paused": state.cooking_paused,
        "current_action": _current_action_to_dict(state.current_action),
        "last_rest_game_time": state.last_rest_game_time,
        "awake_minutes_since_compaction": state.awake_minutes_since_compaction,
        "is_alive": state.is_alive,
    }


def _villager_state_from_dict(data: dict[str, object]) -> VillagerState:
    """Deserialize one villager state snapshot."""

    state = VillagerState(_require_str(data["villager_id"]))
    state.wakefulness = _require_float(data["wakefulness"])
    state.satiation = _require_float(data["satiation"])
    state.hydration = _require_float(data["hydration"])
    state.social_joy = _require_float(data["social_joy"])
    state.connectedness = _require_float(data["connectedness"])
    state.cleanliness = _require_float(data["cleanliness"])
    state.inventory = {
        ItemType[item_name]: _require_int(count)
        for item_name, count in _require_dict(data["inventory"]).items()
    }
    state.sleep_spot_claim = _optional_resting_spot(data.get("sleep_spot_claim"))
    state.crafting_in_progress = _crafting_progress_from_dict(data.get("crafting_in_progress"))
    state.cooking_paused = _require_bool(data["cooking_paused"])
    state.current_action = _current_action_from_dict(data.get("current_action"))
    state.last_rest_game_time = _optional_int(data.get("last_rest_game_time"))
    state.awake_minutes_since_compaction = _require_int(data["awake_minutes_since_compaction"])
    state.is_alive = _require_bool(data["is_alive"])
    return state


def _crafting_progress_to_dict(progress: CraftingProgress | None) -> dict[str, object] | None:
    """Serialize optional crafting progress."""

    if progress is None:
        return None
    return {
        "item": progress.item.name,
        "minutes_spent": progress.minutes_spent,
    }


def _crafting_progress_from_dict(data: object | None) -> CraftingProgress | None:
    """Deserialize optional crafting progress."""

    if data is None:
        return None
    progress = _require_dict(data)
    return CraftingProgress(
        item=CraftableItem[_require_str(progress["item"])],
        minutes_spent=_require_int(progress["minutes_spent"]),
    )


def _current_action_to_dict(action: CurrentAction | None) -> dict[str, object] | None:
    """Serialize an optional current-action snapshot."""

    if action is None:
        return None
    return {
        "category": action.category.name,
        "detail": action.detail,
        "completion_timestamp": action.completion_timestamp,
    }


def _current_action_from_dict(data: object | None) -> CurrentAction | None:
    """Deserialize an optional current-action snapshot."""

    if data is None:
        return None
    action = _require_dict(data)
    detail = action.get("detail")
    return CurrentAction(
        category=ActionCategory[_require_str(action["category"])],
        detail=None if detail is None else _require_str(detail),
        completion_timestamp=_require_int(action["completion_timestamp"]),
    )


def _world_state_to_dict(state: WorldState) -> dict[str, object]:
    """Serialize the shared world state snapshot."""

    return {
        "base_storage": {item.name: count for item, count in state.base_storage.items()},
        "water_supply_ml": state.water_supply_ml,
        "fire": _fire_to_dict(state.fire),
        "dirtiness_counts": {
            source.name: count for source, count in state.dirtiness_counts.items()
        },
        "placed_resting_spots": {
            villager_id: spot.name for villager_id, spot in state.placed_resting_spots.items()
        },
        "live_carcasses": [_carcass_to_dict(carcass) for carcass in state.live_carcasses],
        "next_carcass_id": state.next_carcass_id,
    }


def _world_state_from_dict(data: dict[str, object]) -> WorldState:
    """Deserialize the shared world state snapshot."""

    state = WorldState()
    state.base_storage = {
        ItemType[item_name]: _require_int(count)
        for item_name, count in _require_dict(data["base_storage"]).items()
    }
    state.water_supply_ml = _require_int(data["water_supply_ml"])
    state.fire = _fire_from_dict(_require_dict(data["fire"]))
    state.dirtiness_counts = {
        DirtinessSource[source_name]: _require_int(count)
        for source_name, count in _require_dict(data["dirtiness_counts"]).items()
    }
    state.placed_resting_spots = {
        villager_id: RestingSpotType[spot_name]
        for villager_id, spot_name in _require_dict(data["placed_resting_spots"]).items()
    }
    state.live_carcasses = [
        _carcass_from_dict(_require_dict(carcass))
        for carcass in _require_list(data["live_carcasses"])
    ]
    state.next_carcass_id = _require_int(data["next_carcass_id"])
    return state


def _fire_to_dict(fire: Fire) -> dict[str, object]:
    """Serialize one fire snapshot."""

    return {
        "lit": fire.lit,
        "fuel_queue": [_fuel_unit_to_dict(unit) for unit in fire.fuel_queue],
        "extinction_timestamp": fire.extinction_timestamp,
    }


def _fire_from_dict(data: dict[str, object]) -> Fire:
    """Deserialize one fire snapshot."""

    return Fire(
        lit=_require_bool(data["lit"]),
        fuel_queue=tuple(
            _fuel_unit_from_dict(_require_dict(unit))
            for unit in _require_list(data["fuel_queue"])
        ),
        extinction_timestamp=_optional_int(data.get("extinction_timestamp")),
    )


def _fuel_unit_to_dict(unit: FuelUnit) -> dict[str, object]:
    """Serialize one queued fuel unit."""

    return {"fuel_type": unit.fuel_type.name, "quantity": unit.quantity}


def _fuel_unit_from_dict(data: dict[str, object]) -> FuelUnit:
    """Deserialize one queued fuel unit."""

    return FuelUnit(
        fuel_type=FuelType[_require_str(data["fuel_type"])],
        quantity=_require_int(data["quantity"]),
    )


def _carcass_to_dict(carcass: Carcass) -> dict[str, object]:
    """Serialize one tracked carcass."""

    return {
        "id": carcass.id,
        "arrival_timestamp": carcass.arrival_timestamp,
    }


def _carcass_from_dict(data: dict[str, object]) -> Carcass:
    """Deserialize one tracked carcass."""

    return Carcass(
        id=_require_int(data["id"]),
        arrival_timestamp=_require_int(data["arrival_timestamp"]),
    )


def _autobalance_to_dict(multipliers: AutobalanceMultipliers) -> dict[str, object]:
    """Serialize the autobalance multiplier bundle."""

    return {
        "exploration_yield_scale": multipliers.exploration_yield_scale,
        "satiation_restore_scale": multipliers.satiation_restore_scale,
        "hydration_restore_scale": multipliers.hydration_restore_scale,
    }


def _autobalance_from_dict(data: dict[str, object]) -> AutobalanceMultipliers:
    """Deserialize the autobalance multiplier bundle."""

    return AutobalanceMultipliers(
        exploration_yield_scale=_require_float(data["exploration_yield_scale"]),
        satiation_restore_scale=_require_float(data["satiation_restore_scale"]),
        hydration_restore_scale=_require_float(data["hydration_restore_scale"]),
    )


def _scheduled_event_to_dict(event: ScheduledEvent) -> dict[str, object]:
    """Serialize one scheduled event with an explicit type tag."""

    if isinstance(event, ActionCompleteEvent):
        return {
            "type": "ActionCompleteEvent",
            "timestamp": event.timestamp,
            "sequence": event.sequence,
            "villager_id": event.villager_id,
        }
    if isinstance(event, FireExtinctionEvent):
        return {"type": "FireExtinctionEvent", "timestamp": event.timestamp, "sequence": event.sequence}
    if isinstance(event, CarcassRotEvent):
        return {
            "type": "CarcassRotEvent",
            "timestamp": event.timestamp,
            "sequence": event.sequence,
            "carcass_id": event.carcass_id,
        }
    if isinstance(event, MidnightEvent):
        return {"type": "MidnightEvent", "timestamp": event.timestamp, "sequence": event.sequence}
    return {"type": "CheckpointEvent", "timestamp": event.timestamp, "sequence": event.sequence}


def _scheduled_event_from_dict(data: dict[str, object]) -> ScheduledEvent:
    """Deserialize one scheduled event from its explicit type tag."""

    event_type = _require_str(data["type"])
    timestamp = _require_int(data["timestamp"])
    sequence = _require_int(data["sequence"])
    if event_type == "ActionCompleteEvent":
        return ActionCompleteEvent(
            timestamp=timestamp,
            sequence=sequence,
            villager_id=_require_str(data["villager_id"]),
        )
    if event_type == "FireExtinctionEvent":
        return FireExtinctionEvent(timestamp=timestamp, sequence=sequence)
    if event_type == "CarcassRotEvent":
        return CarcassRotEvent(
            timestamp=timestamp,
            sequence=sequence,
            carcass_id=_require_int(data["carcass_id"]),
        )
    if event_type == "MidnightEvent":
        return MidnightEvent(timestamp=timestamp, sequence=sequence)
    if event_type == "CheckpointEvent":
        return CheckpointEvent(timestamp=timestamp, sequence=sequence)
    raise ValueError(f"Unknown scheduled event type: {event_type}.")


def _optional_resting_spot(value: object | None) -> RestingSpotType | None:
    """Deserialize an optional resting-spot enum by member name."""

    if value is None:
        return None
    return RestingSpotType[_require_str(value)]


def _require_dict(value: object) -> dict[str, object]:
    """Require that one parsed JSON value is an object."""

    if not isinstance(value, dict):
        raise ValueError("Expected dict.")
    return {str(key): inner for key, inner in value.items()}


def _require_list(value: object) -> list[object]:
    """Require that one parsed JSON value is an array."""

    if not isinstance(value, list):
        raise ValueError("Expected list.")
    return value


def _require_str(value: object) -> str:
    """Require that one parsed JSON value is a string."""

    if not isinstance(value, str):
        raise ValueError("Expected str.")
    return value


def _optional_str(value: object | None) -> str | None:
    """Return an optional string field."""

    if value is None:
        return None
    return _require_str(value)


def _require_int(value: object) -> int:
    """Require that one parsed JSON value is an integer."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Expected int.")
    return value


def _optional_int(value: object | None) -> int | None:
    """Return an optional integer field."""

    if value is None:
        return None
    return _require_int(value)


def _require_float(value: object) -> float:
    """Require that one parsed JSON value is numeric."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected float.")
    return float(value)


def _require_bool(value: object) -> bool:
    """Require that one parsed JSON value is boolean."""

    if not isinstance(value, bool):
        raise ValueError("Expected bool.")
    return value
