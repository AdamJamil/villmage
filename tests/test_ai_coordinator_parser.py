# pyre-strict

"""Tests for AI coordinator response parsing and failure logging."""

import json
from pathlib import Path
from typing import Callable

import pytest
from action_system.types import ActionList, ActionType, SelectedAction, ValidAction
from llm_client.types import MessageRole, PromptSegment
from villmage.ai_coordinator import parser
from villmage.ai_coordinator.parser import (
    ParseError,
    _write_failure_log,
    parse_action_selection,
    parse_conversation_turn,
    parse_join_decision,
    parse_relationship_update,
    parse_social_score,
    parse_trade_turn,
)
from villmage.ai_coordinator.types import (
    ActionSelectionResult,
    ConvActionType,
    ConversationTurnResult,
    LLMCallType,
    ParseContext,
    RelationshipUpdateResult,
    TradeActionType,
    TradeItemSpec,
    TradeTurnResult,
)
from villmage.game_types import ItemType


def _make_context(call_type: LLMCallType) -> ParseContext:
    """Return one stable parse context for parser tests."""

    return ParseContext(
        villager_id="aldric",
        call_type=call_type,
        game_time=321,
        prompt=[PromptSegment(role=MessageRole.USER, text="Prompt marker")],
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read one JSONL file into parsed line records."""

    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _make_action_list(*actions: ValidAction) -> ActionList:
    """Return one action list with the supplied actions as main entries."""

    return ActionList(main_actions=actions, crafter_recipes=())


def test_parse_join_decision_accepts_only_yes_and_no() -> None:
    """Join decisions map `yes` to True and `no` to False."""

    context = _make_context(LLMCallType.JOIN_DECISION)

    assert parse_join_decision('{"response": "yes"}', context) is True
    assert parse_join_decision('{"response": "no"}', context) is False


def test_parse_action_selection_resolves_selectable_indices() -> None:
    """Selectable menu indices resolve to the corresponding typed action."""

    action_list = _make_action_list(
        ValidAction(
            action_type=ActionType.REST,
            prompt_text="Rest",
            selectable=True,
            idx=0,
        ),
        ValidAction(
            action_type=ActionType.WASH_UP,
            prompt_text="Wash",
            selectable=True,
            idx=1,
        ),
    )
    context = _make_context(LLMCallType.ACTION_SELECTION)

    first_result = parse_action_selection('{"idx": 0, "args": {}}', action_list, context)
    second_result = parse_action_selection('{"idx": 1, "args": {}}', action_list, context)

    assert first_result.action == SelectedAction(action_type=ActionType.REST)
    assert second_result.action == SelectedAction(action_type=ActionType.WASH_UP)


def test_parse_action_selection_rejects_out_of_range_idx(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unknown action indices raise ParseError instead of selecting arbitrarily."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")
    action_list = _make_action_list(
        ValidAction(
            action_type=ActionType.REST,
            prompt_text="Rest",
            selectable=True,
            idx=0,
        ),
        ValidAction(
            action_type=ActionType.WASH_UP,
            prompt_text="Wash",
            selectable=True,
            idx=1,
        ),
    )

    with pytest.raises(ParseError):
        parse_action_selection(
            '{"idx": 99, "args": {}}',
            action_list,
            _make_context(LLMCallType.ACTION_SELECTION),
        )


def test_parse_action_selection_rejects_non_selectable_action(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Menu entries marked unavailable cannot be selected by the parser."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")
    action_list = _make_action_list(
        ValidAction(
            action_type=ActionType.REST,
            prompt_text="Rest",
            selectable=True,
            idx=0,
        ),
        ValidAction(
            action_type=ActionType.CRAFT_NEW,
            prompt_text="Craft cot (Cannot perform!)",
            selectable=False,
            idx=1,
        ),
    )

    with pytest.raises(ParseError):
        parse_action_selection(
            '{"idx": 1, "args": {}}',
            action_list,
            _make_context(LLMCallType.ACTION_SELECTION),
        )


def test_parse_action_selection_preserves_present_thoughts() -> None:
    """Non-empty thoughts are returned alongside the validated action."""

    action_list = _make_action_list(
        ValidAction(
            action_type=ActionType.REST,
            prompt_text="Rest",
            selectable=True,
            idx=0,
        )
    )

    result = parse_action_selection(
        '{"idx": 0, "args": {}, "thoughts": "need food"}',
        action_list,
        _make_context(LLMCallType.ACTION_SELECTION),
    )

    assert result == ActionSelectionResult(
        action=SelectedAction(action_type=ActionType.REST),
        thought="need food",
    )


@pytest.mark.parametrize("response", ['{"idx": 0, "args": {}}', '{"idx": 0, "args": {}, "thoughts": ""}'])
def test_parse_action_selection_uses_none_for_absent_or_empty_thoughts(
    response: str,
) -> None:
    """Missing or empty thoughts use the authored no-thought behavior."""

    action_list = _make_action_list(
        ValidAction(
            action_type=ActionType.REST,
            prompt_text="Rest",
            selectable=True,
            idx=0,
        )
    )

    result = parse_action_selection(
        response,
        action_list,
        _make_context(LLMCallType.ACTION_SELECTION),
    )

    assert result.thought is None


@pytest.mark.parametrize(
    ("idx", "args", "expected"),
    [
        (1, {}, ConversationTurnResult(action=ConvActionType.LEAVE)),
        (2, {}, ConversationTurnResult(action=ConvActionType.SILENT)),
        (
            3,
            {"resp": "hello"},
            ConversationTurnResult(action=ConvActionType.INTERACT, resp="hello"),
        ),
        (
            4,
            {"resp": "wait"},
            ConversationTurnResult(action=ConvActionType.INTERRUPT, resp="wait"),
        ),
        (
            5,
            {"resp": "go on"},
            ConversationTurnResult(action=ConvActionType.CONTINUE, resp="go on"),
        ),
        (
            6,
            {"resp": "yes"},
            ConversationTurnResult(action=ConvActionType.RESPOND, resp="yes"),
        ),
        (
            7,
            {"resp": "new topic"},
            ConversationTurnResult(action=ConvActionType.CHANGE_TOPIC, resp="new topic"),
        ),
        (
            8,
            {"resp": "nice weather"},
            ConversationTurnResult(action=ConvActionType.CASUAL, resp="nice weather"),
        ),
        (
            9,
            {"target_id": "sewalt"},
            ConversationTurnResult(action=ConvActionType.TRADE, target_id="sewalt"),
        ),
    ],
)
def test_parse_conversation_turn_covers_all_action_types(
    idx: int,
    args: dict[str, str],
    expected: object,
) -> None:
    """Every authored conversation action index resolves to the matching result."""

    result = parse_conversation_turn(
        json.dumps({"idx": idx, "args": args}),
        _make_context(LLMCallType.CONVERSATION_TURN),
    )

    assert result == expected


@pytest.mark.parametrize("idx", [3, 4, 5, 6, 7, 8])
def test_parse_conversation_turn_requires_resp_for_actions_three_through_eight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    idx: int,
) -> None:
    """Resp-required conversation actions fail hard when resp is missing."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_conversation_turn(
            json.dumps({"idx": idx, "args": {}}),
            _make_context(LLMCallType.CONVERSATION_TURN),
        )


def test_parse_conversation_turn_requires_target_id_for_trade(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Trade conversation actions require a concrete target villager id."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_conversation_turn(
            '{"idx": 9, "args": {}}',
            _make_context(LLMCallType.CONVERSATION_TURN),
        )


def test_parse_trade_turn_make_offer_happy_path() -> None:
    """Valid offers resolve item specs from the args payload."""

    result = parse_trade_turn(
        '{"idx": 1, "args": {"1": {"name": "peach", "quantity": 2}}}',
        inventory_items=[(ItemType.PEACH, 3)],
        last_other_action=None,
        ctx=_make_context(LLMCallType.TRADE_TURN),
    )

    assert result == TradeTurnResult(
        action=TradeActionType.MAKE_OFFER,
        items=[TradeItemSpec(item=ItemType.PEACH, quantity=2)],
    )


def test_parse_trade_turn_rejects_empty_make_offer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Offers without any items are always invalid."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_trade_turn(
            '{"idx": 1, "args": {}}',
            inventory_items=[(ItemType.PEACH, 3)],
            last_other_action=None,
            ctx=_make_context(LLMCallType.TRADE_TURN),
        )


def test_parse_trade_turn_rejects_make_offer_that_exceeds_inventory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Offer quantities cannot exceed the acting villager inventory."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_trade_turn(
            '{"idx": 1, "args": {"1": {"name": "peach", "quantity": 3}}}',
            inventory_items=[(ItemType.PEACH, 2)],
            last_other_action=None,
            ctx=_make_context(LLMCallType.TRADE_TURN),
        )


def test_parse_trade_turn_accept_is_valid_only_after_make_offer() -> None:
    """Accept returns an empty-item trade result when the prior action was an offer."""

    result = parse_trade_turn(
        '{"idx": 4, "args": {}}',
        inventory_items=[],
        last_other_action=TradeActionType.MAKE_OFFER,
        ctx=_make_context(LLMCallType.TRADE_TURN),
    )

    assert result == TradeTurnResult(action=TradeActionType.ACCEPT, items=[])


@pytest.mark.parametrize(
    "last_other_action",
    [TradeActionType.REQUEST_ITEMS, TradeActionType.CANCEL, None],
)
def test_parse_trade_turn_rejects_accept_when_offer_not_pending(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    last_other_action: TradeActionType | None,
) -> None:
    """ACCEPT is invalid unless the other villager most recently made an offer."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_trade_turn(
            '{"idx": 4, "args": {}}',
            inventory_items=[],
            last_other_action=last_other_action,
            ctx=_make_context(LLMCallType.TRADE_TURN),
        )


def test_parse_trade_turn_cancel_preserves_optional_speech() -> None:
    """Cancel carries optional speech when present and returns None when omitted."""

    spoken_result = parse_trade_turn(
        '{"idx": 3, "args": {}, "speech": "not interested"}',
        inventory_items=[],
        last_other_action=None,
        ctx=_make_context(LLMCallType.TRADE_TURN),
    )
    silent_result = parse_trade_turn(
        '{"idx": 3, "args": {}}',
        inventory_items=[],
        last_other_action=None,
        ctx=_make_context(LLMCallType.TRADE_TURN),
    )

    assert spoken_result == TradeTurnResult(
        action=TradeActionType.CANCEL,
        items=[],
        speech="not interested",
    )
    assert silent_result == TradeTurnResult(action=TradeActionType.CANCEL, items=[])


@pytest.mark.parametrize(
    "response",
    ['{"response": "maybe"}', '{"response": ""}', "{}", "not json"],
)
def test_parse_join_decision_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Ambiguous or malformed join responses raise ParseError."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)

    with pytest.raises(ParseError):
        parse_join_decision(response, _make_context(LLMCallType.JOIN_DECISION))


@pytest.mark.parametrize("value", [0, 5, 10])
def test_parse_social_score_accepts_full_valid_range(value: int) -> None:
    """Boundary and middle social scores remain valid."""

    context = _make_context(LLMCallType.SOCIAL_SCORE)

    assert parse_social_score(f'{{"val": {value}}}', context) == value


@pytest.mark.parametrize("response", ['{"val": -1}', '{"val": 11}'])
def test_parse_social_score_rejects_out_of_range_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Raw social scores outside 0 through 10 are parse failures."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_social_score(response, _make_context(LLMCallType.SOCIAL_SCORE))


@pytest.mark.parametrize("response", ['{"val": "high"}', '{"val": 7.5}'])
def test_parse_social_score_rejects_non_integer_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Non-integer social scores are rejected instead of coerced."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_social_score(response, _make_context(LLMCallType.SOCIAL_SCORE))


def test_parse_relationship_update_parses_full_response() -> None:
    """Both relationship fields are forwarded when present."""

    context = _make_context(LLMCallType.RELATIONSHIP_UPDATE)

    assert parse_relationship_update(
        '{"impression": "wary", "desc": "Hid food."}',
        context,
    ) == RelationshipUpdateResult(impression="wary", desc_update="Hid food.")


def test_parse_relationship_update_uses_none_when_desc_is_absent() -> None:
    """Missing desc means keep the existing description unchanged."""

    context = _make_context(LLMCallType.RELATIONSHIP_UPDATE)

    assert parse_relationship_update('{"impression": "fine"}', context) == (
        RelationshipUpdateResult(impression="fine", desc_update=None)
    )


@pytest.mark.parametrize(
    "response",
    ['{"impression": ""}', '{"impression": null}', "{}"],
)
def test_parse_relationship_update_requires_non_empty_impression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Missing or empty impressions are hard parse failures."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_relationship_update(
            response,
            _make_context(LLMCallType.RELATIONSHIP_UPDATE),
        )


@pytest.mark.parametrize(
    ("call_type", "parse_fn", "response"),
    [
        (LLMCallType.JOIN_DECISION, parse_join_decision, '{"response": "maybe"}'),
        (LLMCallType.SOCIAL_SCORE, parse_social_score, '{"val": 11}'),
        (
            LLMCallType.RELATIONSHIP_UPDATE,
            parse_relationship_update,
            '{"impression": ""}',
        ),
    ],
)
def test_parse_error_writes_complete_failure_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    call_type: LLMCallType,
    parse_fn: Callable[[str, ParseContext], object],
    response: str,
) -> None:
    """Each parser failure appends one complete diagnostic record."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)
    context = _make_context(call_type)

    with pytest.raises(ParseError):
        parse_fn(response, context)

    assert log_path.exists()
    records = _read_jsonl(log_path)
    assert len(records) == 1
    record = records[0]
    assert record["villager_id"] == context.villager_id
    assert record["call_type"] == context.call_type
    assert record["raw_response"] == response
    assert record["parse_error"] != ""
    assert record["is_retry"] is False


def test_failure_log_appends_instead_of_overwriting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Multiple parse failures preserve every JSONL line."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)
    context = _make_context(LLMCallType.JOIN_DECISION)

    for response in ['{"response": "maybe"}', "{}"]:
        with pytest.raises(ParseError):
            parse_join_decision(response, context)

    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


def test_new_parsers_write_failure_logs_with_correct_call_types(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Each newly added parser appends a failure log with its own call type."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)

    with pytest.raises(ParseError):
        parse_action_selection(
            '{"idx": 9, "args": {}}',
            _make_action_list(
                ValidAction(
                    action_type=ActionType.REST,
                    prompt_text="Rest",
                    selectable=True,
                    idx=0,
                )
            ),
            _make_context(LLMCallType.ACTION_SELECTION),
        )

    action_records = _read_jsonl(log_path)
    assert len(action_records) == 1
    assert action_records[-1]["call_type"] == LLMCallType.ACTION_SELECTION

    with pytest.raises(ParseError):
        parse_conversation_turn(
            '{"idx": 9, "args": {}}',
            _make_context(LLMCallType.CONVERSATION_TURN),
        )

    conversation_records = _read_jsonl(log_path)
    assert len(conversation_records) == 2
    assert conversation_records[-1]["call_type"] == LLMCallType.CONVERSATION_TURN

    with pytest.raises(ParseError):
        parse_trade_turn(
            '{"idx": 4, "args": {}}',
            inventory_items=[],
            last_other_action=None,
            ctx=_make_context(LLMCallType.TRADE_TURN),
        )

    trade_records = _read_jsonl(log_path)
    assert len(trade_records) == 3
    assert trade_records[-1]["call_type"] == LLMCallType.TRADE_TURN


def test_write_failure_log_preserves_retry_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The retry marker is written verbatim to disk."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)
    context = _make_context(LLMCallType.SOCIAL_SCORE)

    _write_failure_log(
        context,
        raw_response='{"val": 12}',
        parse_error="Field `val` must be between 0 and 10.",
        is_retry=True,
    )

    records = _read_jsonl(log_path)
    assert len(records) == 1
    assert records[0]["is_retry"] is True
