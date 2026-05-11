# pyre-strict

"""Tests for pure AI coordinator data types."""

from action_system.types import ActionType, SelectedAction
from llm_client.types import MessageRole, PromptSegment
from villmage.ai_coordinator.types import (
    ActionSelectionResult,
    ConvActionType,
    ConversationSnapshot,
    ConversationTurn,
    ConversationTurnResult,
    LLMCallType,
    ParseContext,
    ParseFailureLog,
    PromptPackage,
    RelationshipRecord,
    RelationshipUpdateResult,
    TradeActionType,
    TradeItemSpec,
    TradeSnapshot,
    TradeTurnRecord,
    TradeTurnResult,
)
from villmage.game_types import ItemType


def _make_prompt_segment() -> PromptSegment:
    """Return one prompt segment for constructor tests."""

    return PromptSegment(role=MessageRole.USER, text="hello")


def test_llm_call_type_enum_is_complete_and_values_match_spec() -> None:
    """LLMCallType contains the exact authored members and values."""

    assert len(LLMCallType) == 6
    assert LLMCallType.ACTION_SELECTION.value == 1
    assert LLMCallType.CONVERSATION_TURN.value == 2
    assert LLMCallType.JOIN_DECISION.value == 3
    assert LLMCallType.SOCIAL_SCORE.value == 4
    assert LLMCallType.RELATIONSHIP_UPDATE.value == 5
    assert LLMCallType.TRADE_TURN.value == 6


def test_conv_action_type_enum_is_complete_and_values_match_spec() -> None:
    """ConvActionType contains the exact authored members and values."""

    assert len(ConvActionType) == 9
    assert ConvActionType.LEAVE.value == 1
    assert ConvActionType.SILENT.value == 2
    assert ConvActionType.INTERACT.value == 3
    assert ConvActionType.INTERRUPT.value == 4
    assert ConvActionType.CONTINUE.value == 5
    assert ConvActionType.RESPOND.value == 6
    assert ConvActionType.CHANGE_TOPIC.value == 7
    assert ConvActionType.CASUAL.value == 8
    assert ConvActionType.TRADE.value == 9


def test_trade_action_type_enum_is_complete_and_values_match_spec() -> None:
    """TradeActionType contains the exact authored members and values."""

    assert len(TradeActionType) == 4
    assert TradeActionType.MAKE_OFFER.value == 1
    assert TradeActionType.REQUEST_ITEMS.value == 2
    assert TradeActionType.CANCEL.value == 3
    assert TradeActionType.ACCEPT.value == 4


def test_conv_action_type_resp_boundary_matches_spec() -> None:
    """Conversation actions 3 through 8 are the exact resp-required range."""

    resp_required_actions = {
        ConvActionType(action_value) for action_value in range(3, 9)
    }

    assert resp_required_actions == {
        ConvActionType.INTERACT,
        ConvActionType.INTERRUPT,
        ConvActionType.CONTINUE,
        ConvActionType.RESPOND,
        ConvActionType.CHANGE_TOPIC,
        ConvActionType.CASUAL,
    }


def test_all_dataclasses_construct_with_minimal_valid_data() -> None:
    """Every AI coordinator dataclass accepts the minimal valid payload."""

    prompt_segment = _make_prompt_segment()
    turn = ConversationTurn(villager_id="aldric", text="Aldric: Hello.")
    snapshot = ConversationSnapshot(
        participant_ids=["aldric", "maren"],
        history=[turn],
        elapsed_game_minutes=5,
    )
    trade_item = TradeItemSpec(item=ItemType.PEACH, quantity=1)
    trade_record = TradeTurnRecord(
        villager_id="aldric",
        action=TradeActionType.CANCEL,
        items=[],
    )
    trade_snapshot = TradeSnapshot(
        other_villager_id="maren",
        history=[trade_record],
        turn_count=1,
    )
    selected_action = SelectedAction(action_type=ActionType.REST)
    action_selection = ActionSelectionResult(action=selected_action)
    relationship_update = RelationshipUpdateResult(impression="wary")
    relationship_record = RelationshipRecord(
        description="steady",
        impressions=["Helpful once."],
    )
    prompt_package = PromptPackage(segments=[prompt_segment], breakpoints=[1, 2])
    parse_context = ParseContext(
        villager_id="aldric",
        call_type=LLMCallType.ACTION_SELECTION,
        game_time=123,
        prompt=[prompt_segment],
    )
    parse_failure = ParseFailureLog(
        villager_id="aldric",
        call_type=LLMCallType.CONVERSATION_TURN,
        game_time=123,
        prompt=[prompt_segment],
        raw_response="{}",
        parse_error="bad response",
        is_retry=False,
    )

    assert snapshot.history == [turn]
    assert trade_snapshot.history == [trade_record]
    assert action_selection.action is selected_action
    assert relationship_update.impression == "wary"
    assert relationship_record.impressions == ["Helpful once."]
    assert prompt_package.breakpoints == [1, 2]
    assert parse_context.prompt == [prompt_segment]
    assert parse_failure.raw_response == "{}"
    assert ConversationTurnResult(action=ConvActionType.LEAVE).action is ConvActionType.LEAVE
    assert TradeTurnResult(action=TradeActionType.CANCEL, items=[]).action is TradeActionType.CANCEL


def test_optional_fields_default_to_none() -> None:
    """Optional AI coordinator result fields default to None when omitted."""

    conversation_result = ConversationTurnResult(action=ConvActionType.LEAVE)
    trade_result = TradeTurnResult(action=TradeActionType.CANCEL, items=[])
    action_result = ActionSelectionResult(
        action=SelectedAction(action_type=ActionType.REST)
    )
    relationship_result = RelationshipUpdateResult(impression="fine")
    trade_record = TradeTurnRecord(
        villager_id="aldric",
        action=TradeActionType.CANCEL,
        items=[],
    )

    assert conversation_result.resp is None
    assert conversation_result.target_id is None
    assert trade_result.speech is None
    assert action_result.thought is None
    assert relationship_result.desc_update is None
    assert trade_record.speech is None


def test_relationship_record_field_order_matches_spec() -> None:
    """RelationshipRecord preserves description then impressions ordering."""

    record = RelationshipRecord(description="d", impressions=["a"])

    assert record.description == "d"
    assert record.impressions == ["a"]


def test_prompt_package_named_fields_are_accessible() -> None:
    """PromptPackage exposes named segments and breakpoints fields."""

    segment = _make_prompt_segment()
    package = PromptPackage(segments=[segment], breakpoints=[1, 2])

    assert package.segments == [segment]
    assert package.breakpoints == [1, 2]


def test_parse_context_stores_all_fields() -> None:
    """ParseContext preserves all values needed for failure logging."""

    segment = _make_prompt_segment()
    context = ParseContext(
        villager_id="aldric",
        call_type=LLMCallType.TRADE_TURN,
        game_time=456,
        prompt=[segment],
    )

    assert context.villager_id == "aldric"
    assert context.call_type is LLMCallType.TRADE_TURN
    assert context.game_time == 456
    assert context.prompt == [segment]
