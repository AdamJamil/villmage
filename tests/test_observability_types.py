# pyre-strict

"""Tests for observability schema types and persistence helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from memory_system.types import EventLogEntry, EventType, MemoryEntry, RelationshipRecord
from observability.types import (
    CheckpointRecord,
    DeltaKind,
    DeltaRecord,
    FieldChange,
    VillagerMemoryCheckpoint,
    append_delta,
    load_checkpoint,
    save_checkpoint,
)
from villmage.autobalance import AutobalanceMultipliers
from villmage.events import ActionCompleteEvent, CheckpointEvent
from villmage.game_types import ActionCategory, CraftableItem, ItemType, RestingSpotType
from villmage.villager_state import CraftingProgress, CurrentAction, VillagerState
from villmage.world_state import DirtinessSource, FuelType, WorldState


def _build_villager_state(villager_id: str) -> VillagerState:
    """Build one non-trivial villager-state fixture."""

    state = VillagerState(villager_id)
    state.wakefulness = 72.5
    state.satiation = 1100.0
    state.hydration = 4200.0
    state.social_joy = 61.0
    state.connectedness = 54.0
    state.cleanliness = 80.0
    state.inventory = {
        ItemType.PEACH: 2,
        ItemType.LOG: 1,
    }
    state.sleep_spot_claim = RestingSpotType.COT
    state.crafting_in_progress = CraftingProgress(
        item=CraftableItem.SATCHEL,
        minutes_spent=120,
    )
    state.cooking_paused = True
    state.current_action = CurrentAction(
        category=ActionCategory.CRAFTING,
        detail="Making a satchel.",
        completion_timestamp=480,
    )
    state.last_rest_game_time = 300
    state.awake_minutes_since_compaction = 75
    state.is_alive = True
    return state


def _build_world_state() -> WorldState:
    """Build one non-trivial world-state fixture."""

    state = WorldState()
    state.modify_base_item(ItemType.PEACH, 5)
    state.modify_base_item(ItemType.FIREWOOD, 3)
    state.modify_water(12_000)
    state.add_fire_fuel(FuelType.FIREWOOD, 2, current_time=360)
    state.add_fire_fuel(FuelType.STICK, 3, current_time=360)
    state.light_fire(current_time=360)
    state.update_cleanliness_source(DirtinessSource.MEAT_SCRAPS, 2)
    state.place_resting_spot("aldric", RestingSpotType.BED_ROLL)
    state.add_carcass(390)
    state.add_carcass(405)
    return state


def _build_memory_checkpoint(villager_id: str) -> VillagerMemoryCheckpoint:
    """Build one non-trivial memory-checkpoint fixture."""

    return VillagerMemoryCheckpoint(
        villager_id=villager_id,
        short_term_memories=[MemoryEntry(game_time=370, text="Short memory.")],
        medium_term_memories=[MemoryEntry(game_time=1440, text="Medium memory.")],
        long_term_memories=[MemoryEntry(game_time=2880, text="Long memory.")],
        active_context_log=[
            EventLogEntry(
                game_time=365,
                type=EventType.ACTION,
                text="Aldric gathered wood.",
            )
        ],
        relationships={
            "maren": RelationshipRecord(
                description="Trustworthy and calm.",
                recent_impressions=["Shared water.", "Offered help."],
            )
        },
        last_long_term_compaction_day=2,
    )


def _build_checkpoint_record(game_time: int) -> CheckpointRecord:
    """Build one checkpoint record with nested state across all fields."""

    second_villager = _build_villager_state("maren")
    second_villager.inventory = {ItemType.COOKED_MEAT: 1}
    second_villager.current_action = CurrentAction(
        category=ActionCategory.RESTING,
        detail=None,
        completion_timestamp=game_time + 30,
    )
    return CheckpointRecord(
        game_time=game_time,
        villager_states=[
            _build_villager_state("aldric"),
            second_villager,
        ],
        world_state=_build_world_state(),
        memory_state=[
            _build_memory_checkpoint("aldric"),
            _build_memory_checkpoint("maren"),
        ],
        autobalance=AutobalanceMultipliers(
            exploration_yield_scale=1.2,
            satiation_restore_scale=0.9,
            hydration_restore_scale=1.1,
        ),
        event_heap=[
            ActionCompleteEvent(timestamp=game_time + 15, sequence=1, villager_id="aldric"),
            CheckpointEvent(timestamp=game_time + 180, sequence=2),
        ],
    )


def _checkpoint_json(record: CheckpointRecord) -> dict[str, object]:
    """Return a stable comparable JSON form for one checkpoint record."""

    return record.to_dict()


def test_delta_kind_values_match_spec() -> None:
    """DeltaKind preserves the authored enum values."""

    assert DeltaKind.VILLAGER_STATS.value == 1
    assert DeltaKind.VILLAGER_INV.value == 2
    assert DeltaKind.WORLD_STATE.value == 3
    assert DeltaKind.MEMORY_UPDATE.value == 4


def test_append_delta_round_trips_each_variant(tmp_path: Path) -> None:
    """Each delta variant should serialize and deserialize without data loss."""

    records = [
        DeltaRecord(
            game_time=360,
            kind=DeltaKind.VILLAGER_STATS,
            villager_id="aldric",
            changes=[
                FieldChange("wakefulness", "100", "85"),
                FieldChange("health", "0.8", "0.6"),
            ],
        ),
        DeltaRecord(
            game_time=420,
            kind=DeltaKind.VILLAGER_INV,
            villager_id="maren",
            changes=[FieldChange("PEACH", "0", "3")],
        ),
        DeltaRecord(
            game_time=450,
            kind=DeltaKind.WORLD_STATE,
            changes=[FieldChange("fire.lit", "false", "true")],
        ),
        DeltaRecord(
            game_time=500,
            kind=DeltaKind.MEMORY_UPDATE,
            villager_id="aldric",
            memory_kind="short_term",
            content="Condensed memory text.",
            subject_id=None,
        ),
    ]

    for record in records:
        append_delta(tmp_path, record)

    delta_path = tmp_path / "state_deltas.jsonl"
    parsed_records = [
        DeltaRecord.from_dict(json.loads(line))
        for line in delta_path.read_text(encoding="utf-8").splitlines()
    ]

    assert parsed_records == records


def test_append_delta_omits_irrelevant_optional_fields(tmp_path: Path) -> None:
    """Serialized delta lines should omit payload keys from other variants."""

    stats_record = DeltaRecord(
        game_time=360,
        kind=DeltaKind.VILLAGER_STATS,
        villager_id="aldric",
        changes=[FieldChange("wakefulness", "100", "85")],
    )
    memory_record = DeltaRecord(
        game_time=500,
        kind=DeltaKind.MEMORY_UPDATE,
        villager_id="aldric",
        memory_kind="impression",
        content="A good impression.",
        subject_id="maren",
    )

    append_delta(tmp_path, stats_record)
    append_delta(tmp_path, memory_record)

    lines = (tmp_path / "state_deltas.jsonl").read_text(encoding="utf-8").splitlines()
    stats_data = json.loads(lines[0])
    memory_data = json.loads(lines[1])

    assert "memory_kind" not in stats_data
    assert "content" not in stats_data
    assert "subject_id" not in stats_data
    assert "changes" not in memory_data


def test_append_delta_accumulates_newline_terminated_lines(tmp_path: Path) -> None:
    """append_delta should preserve call order and JSONL framing."""

    records = [
        DeltaRecord(
            game_time=10,
            kind=DeltaKind.WORLD_STATE,
            changes=[FieldChange("water_supply_ml", "0", "1000")],
        ),
        DeltaRecord(
            game_time=20,
            kind=DeltaKind.VILLAGER_INV,
            villager_id="aldric",
            changes=[FieldChange("PEACH", "1", "2")],
        ),
        DeltaRecord(
            game_time=30,
            kind=DeltaKind.MEMORY_UPDATE,
            villager_id="aldric",
            memory_kind="short_term",
            content="Short memory.",
        ),
    ]

    for record in records:
        append_delta(tmp_path, record)

    raw_text = (tmp_path / "state_deltas.jsonl").read_text(encoding="utf-8")
    lines = raw_text.splitlines()

    assert raw_text.endswith("\n")
    assert len(lines) == 3
    assert [DeltaRecord.from_dict(json.loads(line)) for line in lines] == records


def test_save_checkpoint_uses_zero_padded_filename(tmp_path: Path) -> None:
    """save_checkpoint should write the load-bearing zero-padded filename."""

    save_checkpoint(tmp_path, _build_checkpoint_record(360))
    save_checkpoint(tmp_path, _build_checkpoint_record(1440))

    assert (tmp_path / "checkpoints" / "00360.json").exists()
    assert (tmp_path / "checkpoints" / "01440.json").exists()


def test_load_checkpoint_round_trips_nested_state(tmp_path: Path) -> None:
    """save_checkpoint and load_checkpoint should preserve the full nested state."""

    record = _build_checkpoint_record(540)

    save_checkpoint(tmp_path, record)
    loaded = load_checkpoint(tmp_path, 540)

    assert _checkpoint_json(loaded) == _checkpoint_json(record)


def test_checkpoint_filenames_sort_lexicographically_in_time_order(tmp_path: Path) -> None:
    """Zero padding should make a simple directory sort chronological."""

    for game_time in [360, 540, 1440, 10080]:
        save_checkpoint(tmp_path, _build_checkpoint_record(game_time))

    filenames = sorted(os.listdir(tmp_path / "checkpoints"))

    assert filenames == ["00360.json", "00540.json", "01440.json", "10080.json"]
