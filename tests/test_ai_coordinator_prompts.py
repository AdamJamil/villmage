# pyre-strict

"""Tests for AI coordinator prompt assembly."""

from action_system.types import ActionList, ActionType, ValidAction
from character_canon.types import Profession, VillagerCanon, VillagerId
from memory_system.types import (
    EventLogEntry,
    EventType,
    MemoryEntry,
    RelationshipRecord,
    VillagerId as MemoryVillagerId,
    VillagerMemoryContext,
)
from villmage.ai_coordinator.prompts import assemble_action_selection
from villmage.ai_coordinator.types import PromptPackage
from villmage.game_types import ItemType
from villmage.villager_state import ComputedStats, HealthSubcomponent, MoodSubcomponent
from villmage.world_state import BaseSummary

_SYSTEM_PROMPT = (
    "You are a character in a scenario. Do your best to make actions in line with "
    "your character's psychology and the setting. There is no winning, only "
    "surviving and maximizing your own happiness.\n\n"
    "You will always output a JSON to interact with the world."
)
_BACKSTORY_PREFIX = "Backstory: "
_THOUGHTS_INSTRUCTION = (
    'Record your current thoughts as {"thoughts": str (32 tokens)}. Make note '
    "anything interesting going on, or what you want to do, or else you will "
    "forget it. Omit this section if there is nothing interesting. BE EXTREMELY "
    "CONCISE; DROP PARTICLES. e.g.: ‘I’m starving! No food, need peaches.\" "
    'instead of "I am starving! I can’t find any food at base, I should probably '
    'go and get peaches now."'
)


def _make_canon(villager_id: str, name: str) -> VillagerCanon:
    """Build a minimal villager canon record for prompt tests."""

    return VillagerCanon(
        id=VillagerId(villager_id),
        name=name,
        bio=f"{name} bio",
        personality=f"{name} personality",
        desires=f"{name} desires",
        profession=Profession.BUILDER,
    )


def _make_memory_context() -> VillagerMemoryContext:
    """Build one memory context with distinct tier markers."""

    return VillagerMemoryContext(
        long_term_memories=[MemoryEntry(game_time=1, text="long-term marker")],
        medium_term_memories=[MemoryEntry(game_time=2, text="medium-term marker")],
        short_term_memories=[MemoryEntry(game_time=3, text="short-term marker")],
        active_context_log=[
            EventLogEntry(
                game_time=4,
                type=EventType.ACTION,
                text="active-context marker",
            )
        ],
        relationships={
            MemoryVillagerId("beta"): RelationshipRecord(
                description="beta default relationship",
                recent_impressions=["beta impression"],
            ),
            MemoryVillagerId("gamma"): RelationshipRecord(
                description="gamma special relationship",
                recent_impressions=["gamma impression"],
            ),
            MemoryVillagerId("delta"): RelationshipRecord(
                description="delta default relationship",
                recent_impressions=["delta impression"],
            ),
        },
    )


def _make_base_summary() -> BaseSummary:
    """Build a minimal base summary fixture."""

    return BaseSummary(
        storage={ItemType.PEACH: 2},
        water_supply_ml=3000,
        fire_lit=True,
        remaining_fuel_minutes=15,
        total_dirtiness=7,
        live_carcass_count=1,
        placed_resting_spots={},
    )


def _make_computed_stats() -> ComputedStats:
    """Build a fully populated computed-stats fixture."""

    return ComputedStats(
        well_being=0.5,
        mood=0.6,
        health=0.7,
        safety=0.8,
        wakefulness_pct=0.95,
        satiation_pct=0.92,
        hydration_pct=0.93,
        social_joy_pct=0.4,
        connectedness_pct=0.5,
        cleanliness_pct=0.6,
        base_cleanliness=0.7,
        rest_hours_since=2.0,
        dominant_mood_input=MoodSubcomponent.CONNECTEDNESS,
        dominant_health_input=HealthSubcomponent.HYDRATION,
    )


def _make_action_list(action_text: str) -> ActionList:
    """Build one action list with a distinctive selectable action."""

    action = ValidAction(
        action_type=ActionType.REST,
        prompt_text=action_text,
        selectable=True,
        idx=1,
    )
    return ActionList(main_actions=(action,), crafter_recipes=())


def _make_package(
    game_time: int = 1234,
    action_text: str = "rest marker",
) -> PromptPackage:
    """Assemble a standard action-selection prompt package."""

    own_canon = _make_canon("alpha", "Alpha")
    other_canons = [
        _make_canon("beta", "Beta"),
        _make_canon("gamma", "Gamma"),
        _make_canon("delta", "Delta"),
    ]
    return assemble_action_selection(
        own_canon=own_canon,
        other_canons=other_canons,
        memory_context=_make_memory_context(),
        base_summary=_make_base_summary(),
        computed_stats=_make_computed_stats(),
        inventory_items=[(ItemType.STICK, 3)],
        action_list=_make_action_list(action_text),
        game_time=game_time,
    )


def test_assemble_action_selection_returns_exactly_ten_segments() -> None:
    """The action-selection prompt preserves the exact 10-segment contract."""

    package = _make_package()

    assert len(package.segments) == 10


def test_assemble_action_selection_breakpoints_match_group_boundaries() -> None:
    """Breakpoints land after segment 4 and after segment 5."""

    package = _make_package()

    assert package.breakpoints == [3, 4]


def test_static_content_precedes_dynamic_content() -> None:
    """Fully static prompt segments appear strictly before dynamic ones."""

    package = _make_package()
    texts = [segment.text for segment in package.segments]
    system_index = texts.index(_SYSTEM_PROMPT)
    backstory_index = next(
        index for index, text in enumerate(texts) if text.startswith(_BACKSTORY_PREFIX)
    )
    own_index = next(
        index
        for index, text in enumerate(texts)
        if text.startswith("The character you play: Alpha")
    )
    action_index = next(
        index
        for index, text in enumerate(texts)
        if "Valid actions:" in text and "rest marker" in text
    )
    timestamp_index = texts.index("Timestamp: 1234")

    assert max(system_index, backstory_index, own_index) < min(action_index, timestamp_index)


def test_other_character_blocks_do_not_leak_past_first_breakpoint() -> None:
    """Other-character names appear only in the pre-breakpoint relationship block."""

    package = _make_package()
    first_breakpoint = package.breakpoints[0]
    pre_breakpoint_text = "\n".join(
        segment.text for segment in package.segments[: first_breakpoint + 1]
    )
    post_breakpoint_text = "\n".join(
        segment.text for segment in package.segments[first_breakpoint + 1 :]
    )

    for name in ("Beta", "Gamma", "Delta"):
        assert name in pre_breakpoint_text
        assert name not in post_breakpoint_text


def test_memory_tiers_appear_in_long_to_active_order_between_breakpoints() -> None:
    """All memory tiers stay in the memory group and preserve authored ordering."""

    package = _make_package()
    memory_text = package.segments[package.breakpoints[0] + 1].text
    markers = [
        "long-term marker",
        "medium-term marker",
        "short-term marker",
        "active-context marker",
    ]

    assert package.breakpoints[0] < 4 <= package.breakpoints[1]
    assert [memory_text.index(marker) for marker in markers] == sorted(
        memory_text.index(marker) for marker in markers
    )


def test_dynamic_only_fields_appear_after_both_breakpoints() -> None:
    """Changing timestamp or action list content does not affect cached prefixes."""

    package = _make_package(game_time=8888, action_text="specific action marker")
    package_two = _make_package(game_time=9999, action_text="replacement action marker")
    second_breakpoint = package.breakpoints[1]
    timestamp_index = next(
        index
        for index, segment in enumerate(package.segments)
        if segment.text == "Timestamp: 8888"
    )
    action_index = next(
        index
        for index, segment in enumerate(package.segments)
        if "specific action marker" in segment.text
    )

    assert timestamp_index > second_breakpoint
    assert action_index > second_breakpoint
    assert [segment.text for segment in package.segments[: second_breakpoint + 1]] == [
        segment.text for segment in package_two.segments[: second_breakpoint + 1]
    ]


def test_thoughts_instruction_is_static_late_and_literal() -> None:
    """The thoughts prompt is fixed text between the second breakpoint and timestamp."""

    package = _make_package()
    texts = [segment.text for segment in package.segments]
    thoughts_index = texts.index(_THOUGHTS_INSTRUCTION)
    timestamp_index = texts.index("Timestamp: 1234")

    assert package.breakpoints[1] < thoughts_index < timestamp_index


def test_relationship_description_is_paired_with_matching_bio_before_breakpoint() -> None:
    """Relationship text stays adjacent to the matching villager bio block."""

    package = _make_package()
    first_breakpoint = package.breakpoints[0]
    relevant_texts = [
        segment.text for segment in package.segments[: first_breakpoint + 1]
    ]
    gamma_segment_index = next(
        index
        for index, text in enumerate(relevant_texts)
        if "Gamma's info: Gamma bio" in text
    )
    relationship_segment_index = next(
        index
        for index, text in enumerate(relevant_texts)
        if "gamma special relationship" in text
    )

    assert abs(gamma_segment_index - relationship_segment_index) <= 1
