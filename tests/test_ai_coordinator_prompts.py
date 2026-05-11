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
from villmage.ai_coordinator.prompts import (
    assemble_action_selection,
    assemble_conversation_turn,
    assemble_join_decision,
    assemble_relationship_update,
    assemble_social_score,
    assemble_trade_turn,
)
from villmage.ai_coordinator.types import (
    ConversationSnapshot,
    ConversationTurn,
    PromptPackage,
    RelationshipRecord as CoordinatorRelationshipRecord,
    TradeActionType,
    TradeItemSpec,
    TradeSnapshot,
    TradeTurnRecord,
)
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


def _all_segment_text(package: PromptPackage) -> str:
    """Join all prompt segments for content assertions."""

    return "\n".join(segment.text for segment in package.segments)


def _make_conversation_snapshot(history_texts: list[str]) -> ConversationSnapshot:
    """Build a conversation snapshot with stable participant data."""

    history = [
        ConversationTurn(villager_id=f"villager-{index}", text=text)
        for index, text in enumerate(history_texts)
    ]
    return ConversationSnapshot(
        participant_ids=["alpha", "beta"],
        history=history,
        elapsed_game_minutes=12,
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


def test_assemble_conversation_turn_includes_inventory_and_stats() -> None:
    """Conversation prompts expose live condition and holdings."""

    package = assemble_conversation_turn(
        own_canon=_make_canon("alpha", "Alpha"),
        other_canons=[_make_canon("beta", "Beta")],
        memory_context=_make_memory_context(),
        computed_stats=_make_computed_stats(),
        inventory_items=[(ItemType.PEACH, 3)],
        snapshot=_make_conversation_snapshot(["Beta: Need food?"]),
        game_time=222,
    )
    text = _all_segment_text(package)

    assert "PEACH: 3" in text
    assert "connectedness: 0.50" in text


def test_assemble_conversation_turn_includes_supplied_history() -> None:
    """Conversation prompts include the exact pre-filtered history they receive."""

    first_turn = "Aldric: Hello there."
    second_turn = "Sewalt: Need anything?"
    package = assemble_conversation_turn(
        own_canon=_make_canon("alpha", "Alpha"),
        other_canons=[_make_canon("beta", "Beta")],
        memory_context=_make_memory_context(),
        computed_stats=_make_computed_stats(),
        inventory_items=[],
        snapshot=_make_conversation_snapshot([first_turn, second_turn]),
        game_time=333,
    )
    text = _all_segment_text(package)

    assert first_turn in text
    assert second_turn in text


def test_assemble_trade_turn_includes_inventory_and_history() -> None:
    """Trade prompts show own inventory and prior negotiation turns."""

    package = assemble_trade_turn(
        own_canon=_make_canon("alpha", "Alpha"),
        inventory_items=[(ItemType.COOKED_MEAT, 2)],
        snapshot=TradeSnapshot(
            other_villager_id="beta",
            history=[
                TradeTurnRecord(
                    villager_id="beta",
                    action=TradeActionType.MAKE_OFFER,
                    items=[TradeItemSpec(item=ItemType.PEACH, quantity=1)],
                    speech="I can trade this peach.",
                )
            ],
            turn_count=1,
        ),
    )
    text = _all_segment_text(package)

    assert "2 COOKED_MEAT" in text
    assert "I can trade this peach." in text


def test_assemble_join_decision_uses_provided_history_verbatim() -> None:
    """Join-decision prompts pass through the supplied history without slicing."""

    first_turn = "Aldric: We found berries."
    second_turn = "Sewalt: Bring them here."
    package = assemble_join_decision(
        own_canon=_make_canon("gamma", "Gamma"),
        current_action_description="watching the fire",
        snapshot=_make_conversation_snapshot([first_turn, second_turn]),
    )
    text = _all_segment_text(package)

    assert first_turn in text
    assert second_turn in text
    assert text.count(first_turn) == 1
    assert text.count(second_turn) == 1


def test_assemble_join_decision_handles_empty_history() -> None:
    """Join-decision prompts tolerate an empty caller-supplied history."""

    package = assemble_join_decision(
        own_canon=_make_canon("gamma", "Gamma"),
        current_action_description="gathering sticks",
        snapshot=_make_conversation_snapshot([]),
    )
    text = _all_segment_text(package)

    assert "Conversation history: None." in text


def test_assemble_join_decision_includes_current_action() -> None:
    """Join-decision prompts include the villager's current work."""

    package = assemble_join_decision(
        own_canon=_make_canon("gamma", "Gamma"),
        current_action_description="gathering sticks",
        snapshot=_make_conversation_snapshot(["Alpha: Want help?"]),
    )

    assert "gathering sticks" in _all_segment_text(package)


def test_assemble_social_score_requests_zero_to_ten_value() -> None:
    """Social-score prompts specify the required numeric scale."""

    package = assemble_social_score(
        own_canon=_make_canon("alpha", "Alpha"),
        snapshot=_make_conversation_snapshot(["Beta: Good to see you."]),
    )
    text = _all_segment_text(package)

    assert "0-10" in text
    assert "val" in text


def test_assemble_relationship_update_depends_on_speaker_subject_order() -> None:
    """Relationship prompts preserve speaker-subject directionality."""

    relationship = CoordinatorRelationshipRecord(
        description="steady ally",
        impressions=["Shared food recently."],
    )
    snapshot = _make_conversation_snapshot(["Aldric: You did well today."])
    package = assemble_relationship_update(
        speaker_canon=_make_canon("aldric", "Aldric"),
        subject_canon=_make_canon("sewalt", "Sewalt"),
        relationship=relationship,
        snapshot=snapshot,
    )
    swapped_package = assemble_relationship_update(
        speaker_canon=_make_canon("sewalt", "Sewalt"),
        subject_canon=_make_canon("aldric", "Aldric"),
        relationship=relationship,
        snapshot=snapshot,
    )
    text = _all_segment_text(package)

    assert "You are Aldric. Update your view of Sewalt" in text
    assert package != swapped_package


def test_assemble_relationship_update_includes_relationship_fields() -> None:
    """Relationship prompts include description and all recent impressions."""

    relationship = CoordinatorRelationshipRecord(
        description="Suspicious but useful.",
        impressions=[
            "He kept his promise.",
            "He watched me carefully.",
            "He shared the fire.",
        ],
    )
    package = assemble_relationship_update(
        speaker_canon=_make_canon("aldric", "Aldric"),
        subject_canon=_make_canon("sewalt", "Sewalt"),
        relationship=relationship,
        snapshot=_make_conversation_snapshot(["Sewalt: Sit by the fire."]),
    )
    text = _all_segment_text(package)

    assert "Suspicious but useful." in text
    assert "He kept his promise." in text
    assert "He watched me carefully." in text
    assert "He shared the fire." in text


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
