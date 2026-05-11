# pyre-strict

"""Prompt assembly helpers for the AI coordinator."""

from typing import cast

from action_system.types import ActionList, ValidAction
from character_canon.canon import CharacterCanon
from character_canon.types import VillagerCanon
from llm_client.types import MessageRole, PromptSegment
from memory_system.types import (
    EventLogEntry,
    MemoryEntry,
    RelationshipRecord,
    VillagerId as MemoryVillagerId,
    VillagerMemoryContext,
)
from villmage.ai_coordinator.types import PromptPackage
from villmage.game_types import GameTime, ItemType
from villmage.villager_state import ComputedStats, HealthSubcomponent, MoodSubcomponent
from villmage.world_state import BaseSummary

_SYSTEM_PROMPT = (
    "You are a character in a scenario. Do your best to make actions in line with "
    "your character's psychology and the setting. There is no winning, only "
    "surviving and maximizing your own happiness.\n\n"
    "You will always output a JSON to interact with the world."
)
_BACKSTORY_TEXT = f"Backstory: {CharacterCanon().get_backstory().text}"
_THOUGHTS_INSTRUCTION = (
    'Record your current thoughts as {"thoughts": str (32 tokens)}. Make note '
    "anything interesting going on, or what you want to do, or else you will "
    "forget it. Omit this section if there is nothing interesting. BE EXTREMELY "
    "CONCISE; DROP PARTICLES. e.g.: ‘I’m starving! No food, need peaches.\" "
    'instead of "I am starving! I can’t find any food at base, I should probably '
    'go and get peaches now."'
)
_MOOD_STAT_NAMES: dict[MoodSubcomponent, str] = {
    MoodSubcomponent.SOCIAL_JOY: "social_joy",
    MoodSubcomponent.CONNECTEDNESS: "connectedness",
    MoodSubcomponent.CLEANLINESS: "cleanliness",
    MoodSubcomponent.BASE_CLEANLINESS: "base_cleanliness",
    MoodSubcomponent.REST: "rest",
}
_HEALTH_STAT_NAMES: dict[HealthSubcomponent, str] = {
    HealthSubcomponent.WAKEFULNESS: "wakefulness",
    HealthSubcomponent.SATIATION: "satiation",
    HealthSubcomponent.HYDRATION: "hydration",
}


def _make_segment(role: MessageRole, text: str) -> PromptSegment:
    """Return one prompt segment with the supplied role and text."""

    return PromptSegment(role=role, text=text)


def _format_own_character(own_canon: VillagerCanon) -> str:
    """Render the villager's own authored identity block."""

    return (
        f"The character you play: {own_canon.name}\n"
        f"Bio: {own_canon.bio}\n"
        f"Personality: {own_canon.personality}\n"
        f"Desires: {own_canon.desires}"
    )


def _format_other_characters(
    other_canons: list[VillagerCanon],
    relationships: dict[MemoryVillagerId, RelationshipRecord],
) -> str:
    """Render other villagers with their paired relationship state."""

    blocks: list[str] = []
    for other_canon in other_canons:
        relationship = relationships[cast(MemoryVillagerId, other_canon.id)]
        impressions = (
            "\n".join(f"- {impression}" for impression in relationship.recent_impressions)
            if relationship.recent_impressions
            else "- None."
        )
        blocks.append(
            f"{other_canon.name}'s info: {other_canon.bio}\n"
            f"Current relationship: {relationship.description}\n"
            f"Recent impressions:\n{impressions}"
        )
    return "\n\n".join(blocks) if blocks else "Other characters: None."


def _format_memory_entries(title: str, entries: list[MemoryEntry]) -> str:
    """Render one memory tier with stable numbered lines."""

    if not entries:
        return f"{title}: None."
    lines = [f"{entry.game_time}: {entry.text}" for entry in entries]
    return f"{title}:\n" + "\n".join(lines)


def _format_event_entries(entries: list[EventLogEntry]) -> str:
    """Render the active event log with timestamped lines."""

    if not entries:
        return "Active context log: None."
    lines = [f"{entry.game_time}: {entry.text}" for entry in entries]
    return "Active context log:\n" + "\n".join(lines)


def _format_memories(memory_context: VillagerMemoryContext) -> str:
    """Render all four memory tiers in required long-to-active order."""

    parts = [
        _format_memory_entries("Long-term memories", memory_context.long_term_memories),
        _format_memory_entries(
            "Medium-term memories",
            memory_context.medium_term_memories,
        ),
        _format_memory_entries("Short-term memories", memory_context.short_term_memories),
        _format_event_entries(memory_context.active_context_log),
    ]
    return "\n\n".join(parts)


def _format_item_counts(items: list[tuple[ItemType, int]]) -> str:
    """Render item-count pairs in a stable human-readable list."""

    if not items:
        return "None."
    return "\n".join(f"- {item.name}: {quantity}" for item, quantity in items)


def _format_world_state(base_summary: BaseSummary) -> str:
    """Render the prompt-visible shared camp state."""

    storage_items = sorted(base_summary.storage.items(), key=lambda pair: pair[0].name)
    resting_spots = sorted(base_summary.placed_resting_spots.items())
    fire_status = (
        f"lit with {base_summary.remaining_fuel_minutes} fuel minutes remaining"
        if base_summary.fire_lit
        else "unlit"
    )
    resting_text = (
        "\n".join(f"- {villager_id}: {spot.name}" for villager_id, spot in resting_spots)
        if resting_spots
        else "- None."
    )
    return (
        "World state summary:\n"
        f"Base items:\n{_format_item_counts(storage_items)}\n"
        f"Fire: {fire_status}\n"
        f"Water supply (mL): {base_summary.water_supply_ml}\n"
        f"Total dirtiness: {base_summary.total_dirtiness}\n"
        f"Live carcasses: {base_summary.live_carcass_count}\n"
        "Placed resting spots:\n"
        f"{resting_text}\n"
        "Villager actions: unavailable in this prompt input."
    )


def _mood_stat_value(
    computed_stats: ComputedStats,
    subcomponent: MoodSubcomponent,
) -> float:
    """Return the numeric value for one mood subcomponent."""

    if subcomponent is MoodSubcomponent.SOCIAL_JOY:
        return computed_stats.social_joy_pct
    if subcomponent is MoodSubcomponent.CONNECTEDNESS:
        return computed_stats.connectedness_pct
    if subcomponent is MoodSubcomponent.CLEANLINESS:
        return computed_stats.cleanliness_pct
    if subcomponent is MoodSubcomponent.BASE_CLEANLINESS:
        return computed_stats.base_cleanliness
    return computed_stats.rest_hours_since


def _health_stat_value(
    computed_stats: ComputedStats,
    subcomponent: HealthSubcomponent,
) -> float:
    """Return the numeric value for one health subcomponent."""

    if subcomponent is HealthSubcomponent.WAKEFULNESS:
        return computed_stats.wakefulness_pct
    if subcomponent is HealthSubcomponent.SATIATION:
        return computed_stats.satiation_pct
    return computed_stats.hydration_pct


def _format_stat_descriptions(computed_stats: ComputedStats) -> str:
    """Render the stat names implied by the authored inclusion rules."""

    mood_name = _MOOD_STAT_NAMES[computed_stats.dominant_mood_input]
    health_name = _HEALTH_STAT_NAMES[computed_stats.dominant_health_input]
    stat_lines = [
        f"- well_being: {computed_stats.well_being:.2f}",
        f"- mood: {computed_stats.mood:.2f}",
        f"- health: {computed_stats.health:.2f}",
        f"- safety: {computed_stats.safety:.2f}",
        f"- {mood_name}: "
        f"{_mood_stat_value(computed_stats, computed_stats.dominant_mood_input):.2f}",
        f"- {health_name}: "
        f"{_health_stat_value(computed_stats, computed_stats.dominant_health_input):.2f}",
    ]
    if computed_stats.satiation_pct < 0.90:
        stat_lines.append(f"- satiation: {computed_stats.satiation_pct:.2f}")
    if computed_stats.hydration_pct < 0.50:
        stat_lines.append(f"- hydration: {computed_stats.hydration_pct:.2f}")
    if computed_stats.wakefulness_pct < 0.50:
        stat_lines.append(f"- wakefulness: {computed_stats.wakefulness_pct:.2f}")
    return "\n".join(stat_lines)


def _format_villager_state(
    inventory_items: list[tuple[ItemType, int]],
    computed_stats: ComputedStats,
) -> str:
    """Render live per-villager inventory and stat state."""

    return (
        "Villager state:\n"
        f"Inventory:\n{_format_item_counts(inventory_items)}\n"
        "Stat descriptions:\n"
        f"{_format_stat_descriptions(computed_stats)}"
    )


def _format_action_section(
    title: str,
    actions: tuple[ValidAction, ...],
) -> str:
    """Render one action-menu section, preserving supplied order."""

    if not actions:
        return f"{title}:\n- None."
    lines = []
    for action in actions:
        prefix = f"[{action.idx}] " if action.idx is not None else ""
        lines.append(f"- {prefix}{action.prompt_text}")
    return f"{title}:\n" + "\n".join(lines)


def _format_action_list(action_list: ActionList) -> str:
    """Render the full valid-action menu for selection."""

    parts = [
        _format_action_section("Valid actions", action_list.main_actions),
        _format_action_section("Crafter recipes", action_list.crafter_recipes),
    ]
    return "\n\n".join(parts)


def assemble_action_selection(
    own_canon: VillagerCanon,
    other_canons: list[VillagerCanon],
    memory_context: VillagerMemoryContext,
    base_summary: BaseSummary,
    computed_stats: ComputedStats,
    inventory_items: list[tuple[ItemType, int]],
    action_list: ActionList,
    game_time: GameTime,
) -> PromptPackage:
    """Render the action-selection prompt in REQ-224 segment order."""

    segments = [
        _make_segment(MessageRole.SYSTEM, _SYSTEM_PROMPT),
        _make_segment(MessageRole.USER, _BACKSTORY_TEXT),
        _make_segment(MessageRole.USER, _format_own_character(own_canon)),
        _make_segment(
            MessageRole.USER,
            _format_other_characters(other_canons, memory_context.relationships),
        ),
        _make_segment(MessageRole.USER, _format_memories(memory_context)),
        _make_segment(MessageRole.USER, _format_world_state(base_summary)),
        _make_segment(
            MessageRole.USER,
            _format_villager_state(inventory_items, computed_stats),
        ),
        _make_segment(MessageRole.USER, _format_action_list(action_list)),
        _make_segment(MessageRole.USER, _THOUGHTS_INSTRUCTION),
        _make_segment(MessageRole.USER, f"Timestamp: {game_time}"),
    ]
    return PromptPackage(segments=segments, breakpoints=[3, 4])
