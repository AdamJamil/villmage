# pyre-strict

"""Tests for the AI coordinator orchestration layer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from action_system.types import ActionList, ActionType, ValidAction
from character_canon.types import Profession, VillagerCanon, VillagerId
from llm_client.types import MessageRole, PromptSegment
from memory_system.types import (
    EventLogEntry,
    EventType,
    MemoryEntry,
    RelationshipRecord as MemoryRelationshipRecord,
    VillagerMemoryContext,
)
from villmage.ai_coordinator import parser as parser_module
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.ai_coordinator.parser import ParseError, parse_join_decision
from villmage.ai_coordinator.types import (
    ActionSelectionResult,
    ConversationSnapshot,
    ConversationTurn,
    ConversationTurnResult,
    LLMCallType,
    ParseContext,
    PromptPackage,
    RelationshipUpdateResult,
    TradeActionType,
    TradeItemSpec,
    TradeSnapshot,
    TradeTurnRecord,
    TradeTurnResult,
)
from villmage.game_types import ItemType
from villmage.villager_state import VillagerState
from villmage.world_state import DirtinessSource, WorldState


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Return all JSON objects stored in one JSONL file."""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _make_context(prompt_text: str = "prompt") -> ParseContext:
    """Build one parse context for direct `_call` tests."""

    return ParseContext(
        villager_id="aldric",
        call_type=LLMCallType.JOIN_DECISION,
        game_time=123,
        prompt=[PromptSegment(role=MessageRole.USER, text=prompt_text)],
    )


def _make_package(prompt_text: str = "prompt") -> PromptPackage:
    """Build one prompt package for direct `_call` tests."""

    return PromptPackage(
        segments=[PromptSegment(role=MessageRole.USER, text=prompt_text)],
        breakpoints=[],
    )


def _make_canon(villager_id: str, name: str, bio: str) -> VillagerCanon:
    """Return one authored villager canon with distinct test strings."""

    return VillagerCanon(
        id=VillagerId(villager_id),
        name=name,
        bio=bio,
        personality=f"{name} personality",
        desires=f"{name} desires",
        profession=Profession.WOODCUTTER,
    )


def _make_memory_context() -> VillagerMemoryContext:
    """Return one memory context with distinctive prompt-visible content."""

    return VillagerMemoryContext(
        long_term_memories=[MemoryEntry(game_time=1, text="LONG MEMORY TOKEN")],
        medium_term_memories=[MemoryEntry(game_time=2, text="MEDIUM MEMORY TOKEN")],
        short_term_memories=[MemoryEntry(game_time=3, text="SHORT MEMORY TOKEN")],
        active_context_log=[
            EventLogEntry(
                game_time=4,
                type=EventType.ACTION,
                text="ACTIVE CONTEXT TOKEN",
            )
        ],
        relationships={
            VillagerId("beta"): MemoryRelationshipRecord(
                description="RELATIONSHIP BETA",
                recent_impressions=["IMPRESSION BETA"],
            ),
            VillagerId("gamma"): MemoryRelationshipRecord(
                description="RELATIONSHIP GAMMA",
                recent_impressions=["IMPRESSION GAMMA"],
            ),
            VillagerId("sewalt"): MemoryRelationshipRecord(
                description="RELATIONSHIP SEWALT",
                recent_impressions=["IMPRESSION SEWALT"],
            ),
        },
    )


def _make_select_action_state() -> VillagerState:
    """Return one villager state with visible inventory/stat content."""

    state = VillagerState("aldric")
    state.modify_inventory(ItemType.COOKED_MEAT, 2)
    state.modify_inventory(ItemType.PEACH, 1)
    state.wakefulness = 40.0
    state.satiation = 600.0
    state.hydration = 2000.0
    state.social_joy = 35.0
    state.cleanliness = 50.0
    return state


def _make_coordinator(
    *,
    llm_side_effect: object,
) -> tuple[AICoordinator, Mock, Mock, Mock]:
    """Build one coordinator and return it with the main dependency mocks."""

    canon = Mock()
    own_canon = _make_canon("aldric", "Aldric", "OWN BIO TOKEN")
    other_canons = [
        _make_canon("beta", "Beta", "OTHER BIO TOKEN BETA"),
        _make_canon("gamma", "Gamma", "OTHER BIO TOKEN GAMMA"),
        _make_canon("sewalt", "Sewalt", "OTHER BIO TOKEN SEWALT"),
    ]
    canon.get_villager.side_effect = lambda villager_id: {
        "aldric": own_canon,
        "beta": other_canons[0],
        "gamma": other_canons[1],
        "sewalt": other_canons[2],
    }[str(villager_id)]
    canon.get_all_villagers.return_value = (own_canon, *other_canons)

    villager_state = _make_select_action_state()
    villager_states = {"aldric": villager_state, "beta": VillagerState("beta")}

    world_state = WorldState()
    world_state.modify_base_item(ItemType.PEACH, 5)
    world_state.modify_base_item(ItemType.STICK, 2)
    world_state.modify_water(750)
    world_state.update_cleanliness_source(DirtinessSource.MEAT_SCRAPS, 2)

    action_system = Mock()
    action_system.get_valid_actions.return_value = ActionList(
        main_actions=(
            ValidAction(
                action_type=ActionType.REST,
                prompt_text="ACTION LIST TOKEN",
                selectable=True,
                idx=0,
            ),
        ),
        crafter_recipes=(),
    )

    memory_system = Mock()
    memory_system.get_memory_context.return_value = _make_memory_context()
    memory_system.get_relationship_record.return_value = MemoryRelationshipRecord(
        description="KNOWN SUBJECT",
        recent_impressions=["OLDER IMPRESSION"],
    )

    llm_client = Mock()
    llm_client.complete.side_effect = llm_side_effect

    return (
        AICoordinator(
            canon=canon,
            villager_states=villager_states,
            world_state=world_state,
            action_system=action_system,
            memory_system=memory_system,
            llm_client=llm_client,
        ),
        llm_client,
        memory_system,
        canon,
    )


def test_call_success_path() -> None:
    """`_call` returns the parsed value after one successful completion."""

    coordinator, llm_client, _, _ = _make_coordinator(
        llm_side_effect=['{"response": "yes"}']
    )

    result = coordinator._call(_make_package(), parse_join_decision, _make_context())

    assert result is True
    assert llm_client.complete.call_count == 1


def test_call_first_failure_retry_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`_call` retries once with the same prompt when the first parse fails."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser_module, "_FAILURE_LOG_PATH", log_path)
    coordinator, llm_client, _, _ = _make_coordinator(
        llm_side_effect=['{"response": "maybe"}', '{"response": "yes"}']
    )

    result = coordinator._call(_make_package("same prompt"), parse_join_decision, _make_context("same prompt"))

    assert result is True
    assert llm_client.complete.call_count == 2
    first_prompt = llm_client.complete.call_args_list[0].args[0]
    second_prompt = llm_client.complete.call_args_list[1].args[0]
    assert first_prompt == second_prompt

    records = _read_jsonl(log_path)
    assert len(records) == 1
    assert records[0]["is_retry"] is False


def test_call_both_failures_crashes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`_call` re-raises ParseError after the retry also fails."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser_module, "_FAILURE_LOG_PATH", log_path)
    coordinator, llm_client, _, _ = _make_coordinator(
        llm_side_effect=['{"response": "maybe"}', '{"response": "still maybe"}']
    )

    with pytest.raises(ParseError):
        coordinator._call(_make_package(), parse_join_decision, _make_context())

    assert llm_client.complete.call_count == 2
    records = _read_jsonl(log_path)
    assert len(records) == 2
    assert records[0]["is_retry"] is False
    assert records[1]["is_retry"] is True


def test_select_action_reads_all_subsystems() -> None:
    """`select_action` includes prompt-visible content from every input subsystem."""

    coordinator, llm_client, _, _ = _make_coordinator(
        llm_side_effect=['{"idx": 0, "args": {}}']
    )

    coordinator.select_action("aldric", 120)

    prompt_segments = llm_client.complete.call_args.args[0]
    prompt_text = "\n".join(segment.text for segment in prompt_segments)
    assert "OWN BIO TOKEN" in prompt_text
    assert "OTHER BIO TOKEN BETA" in prompt_text
    assert "ACTIVE CONTEXT TOKEN" in prompt_text
    assert "Base items:" in prompt_text
    assert "- PEACH: 5" in prompt_text
    assert "Stat descriptions:" in prompt_text
    assert "- well_being:" in prompt_text
    assert "COOKED_MEAT" in prompt_text
    assert "ACTION LIST TOKEN" in prompt_text


def test_select_action_returns_thought() -> None:
    """`select_action` returns the parsed thought when the LLM provides one."""

    coordinator, _, _, _ = _make_coordinator(
        llm_side_effect=['{"idx": 0, "args": {}, "thoughts": "need sleep"}']
    )

    result = coordinator.select_action("aldric", 120)

    assert result.thought == "need sleep"


def test_select_action_thought_absent_is_none() -> None:
    """`select_action` preserves absence of the `thoughts` key as None."""

    coordinator, _, _, _ = _make_coordinator(
        llm_side_effect=['{"idx": 0, "args": {}}']
    )

    result = coordinator.select_action("aldric", 120)

    assert result.thought is None


def test_get_relationship_update_reads_correct_ordered_pair() -> None:
    """Relationship lookup uses speaker-subject ordering, never the reverse."""

    coordinator, _, memory_system, _ = _make_coordinator(
        llm_side_effect=['{"impression": "warier"}']
    )
    snapshot = ConversationSnapshot(
        participant_ids=["aldric", "sewalt"],
        history=[ConversationTurn(villager_id="aldric", text="Aldric speaks.")],
        elapsed_game_minutes=10,
    )

    coordinator.get_relationship_update("aldric", "sewalt", snapshot, 120)

    memory_system.get_relationship_record.assert_called_once_with("aldric", "sewalt")


def test_public_methods_return_declared_types() -> None:
    """Each public method returns the type declared by the coordinator interface."""

    coordinator, _, _, canon = _make_coordinator(
        llm_side_effect=[
            '{"idx": 0, "args": {}}',
            '{"idx": 1, "args": {}}',
            '{"idx": 3, "args": {}}',
            '{"response": "yes"}',
            '{"val": 7}',
            '{"impression": "steady"}',
        ]
    )
    canon.get_villager.side_effect = lambda villager_id: {
        "aldric": _make_canon("aldric", "Aldric", "OWN BIO TOKEN"),
        "beta": _make_canon("beta", "Beta", "OTHER BIO TOKEN BETA"),
        "gamma": _make_canon("gamma", "Gamma", "OTHER BIO TOKEN GAMMA"),
        "sewalt": _make_canon("sewalt", "Sewalt", "SEWALT BIO"),
    }[str(villager_id)]
    snapshot = ConversationSnapshot(
        participant_ids=["aldric", "sewalt"],
        history=[
            ConversationTurn(villager_id="aldric", text="Turn one."),
            ConversationTurn(villager_id="sewalt", text="Turn two."),
        ],
        elapsed_game_minutes=12,
    )
    trade_snapshot = TradeSnapshot(
        other_villager_id="sewalt",
        history=[
            TradeTurnRecord(
                villager_id="sewalt",
                action=TradeActionType.MAKE_OFFER,
                items=[TradeItemSpec(item=ItemType.PEACH, quantity=1)],
            )
        ],
        turn_count=1,
    )

    action_result = coordinator.select_action("aldric", 100)
    conversation_result = coordinator.get_conversation_turn("aldric", snapshot, 100)
    trade_result = coordinator.get_trade_turn("aldric", trade_snapshot, 100)
    join_result = coordinator.get_join_decision("aldric", "resting", snapshot, 100)
    social_result = coordinator.get_social_score("aldric", snapshot, 100)
    relationship_result = coordinator.get_relationship_update(
        "aldric",
        "sewalt",
        snapshot,
        100,
    )

    assert isinstance(action_result, ActionSelectionResult)
    assert isinstance(conversation_result, ConversationTurnResult)
    assert isinstance(trade_result, TradeTurnResult)
    assert isinstance(join_result, bool)
    assert isinstance(social_result, int)
    assert isinstance(relationship_result, RelationshipUpdateResult)


def test_get_join_decision_uses_pre_sliced_snapshot() -> None:
    """`get_join_decision` uses the caller-supplied history verbatim."""

    coordinator, llm_client, _, _ = _make_coordinator(
        llm_side_effect=['{"response": "yes"}']
    )
    snapshot = ConversationSnapshot(
        participant_ids=["aldric", "beta"],
        history=[
            ConversationTurn(villager_id="aldric", text="FIRST TURN TOKEN"),
            ConversationTurn(villager_id="beta", text="SECOND TURN TOKEN"),
        ],
        elapsed_game_minutes=2,
    )

    coordinator.get_join_decision("aldric", "resting", snapshot, 90)

    prompt_text = "\n".join(
        segment.text for segment in llm_client.complete.call_args.args[0]
    )
    assert "FIRST TURN TOKEN" in prompt_text
    assert "SECOND TURN TOKEN" in prompt_text
