# pyre-strict

"""Tests for conversation turn text formatting."""

import pytest

from conversation_system.conversation import ConversationSystem, format_turn_text
from conversation_system.types import ConversationSession
from villmage.ai_coordinator.types import ConvActionType, ConversationTurnResult


@pytest.mark.parametrize(
    ("action", "response"),
    [
        (ConvActionType.INTERRUPT, "Hold on."),
        (ConvActionType.CONTINUE, "Go on."),
        (ConvActionType.RESPOND, "I agree."),
        (ConvActionType.CHANGE_TOPIC, "What about the mill?"),
    ],
)
def test_speech_actions_include_name_prefix(
    action: ConvActionType,
    response: str,
) -> None:
    """Speech actions render as speaker-prefixed dialogue."""

    result = ConversationTurnResult(action=action, resp=response)

    assert format_turn_text(result, "Maren") == f"Maren: {response}"


@pytest.mark.parametrize(
    ("action", "response"),
    [
        (ConvActionType.INTERACT, "Maren nods toward the market stalls."),
        (ConvActionType.CASUAL, "Maren idly watches the clouds drift by."),
    ],
)
def test_interact_and_casual_return_response_verbatim(
    action: ConvActionType,
    response: str,
) -> None:
    """Third-person actions pass through without a name prefix."""

    result = ConversationTurnResult(action=action, resp=response)

    assert format_turn_text(result, "Maren") == response


def test_trade_uses_target_name() -> None:
    """Trade initiation names both the speaker and trade target."""

    result = ConversationTurnResult(action=ConvActionType.TRADE, target_id="aldric")

    assert (
        format_turn_text(result, "Maren", target_name="Aldric")
        == "Maren asks Aldric if they want to trade."
    )


def test_leave_ignores_response_text() -> None:
    """Leave renders the fixed departure sentence regardless of resp."""

    result = ConversationTurnResult(
        action=ConvActionType.LEAVE,
        resp="this should be ignored",
    )

    assert format_turn_text(result, "Maren") == "Maren leaves the conversation."


def test_trade_without_target_name_raises() -> None:
    """Trade formatting requires the caller to provide a target name."""

    result = ConversationTurnResult(action=ConvActionType.TRADE, target_id="aldric")

    with pytest.raises(ValueError, match="target_name"):
        format_turn_text(result, "Maren")


def test_conversation_system_shell_constructs() -> None:
    """The placeholder conversation system class is importable and constructible."""

    assert isinstance(ConversationSystem(), ConversationSystem)


def _make_session(last_spoke_turn: dict[str, int]) -> ConversationSession:
    """Build a minimal conversation session for winner-selection tests."""

    return ConversationSession(
        participant_ids=[],
        all_participant_ids=[],
        full_turn_log=[],
        join_turn_index={},
        elapsed_game_minutes=0,
        last_spoke_turn=last_spoke_turn,
    )


@pytest.mark.parametrize(
    ("winner_action", "loser_action"),
    [
        (ConvActionType.INTERACT, ConvActionType.TRADE),
        (ConvActionType.INTERACT, ConvActionType.CASUAL),
        (ConvActionType.TRADE, ConvActionType.INTERRUPT),
        (ConvActionType.INTERRUPT, ConvActionType.CONTINUE),
        (ConvActionType.RESPOND, ConvActionType.SILENT),
    ],
)
def test_select_winner_uses_priority_order(
    winner_action: ConvActionType,
    loser_action: ConvActionType,
) -> None:
    """Higher-priority actions beat lower-priority actions."""

    system = ConversationSystem()
    session = _make_session({"winner": 2, "loser": 1})
    responses = {
        "winner": ConversationTurnResult(action=winner_action, resp="winner"),
        "loser": ConversationTurnResult(action=loser_action, resp="loser"),
    }

    assert system._select_winner(responses, session) == responses["winner"]


def test_select_winner_prefers_single_response_even_if_silent() -> None:
    """A lone response wins directly, including a lone SILENT action."""

    system = ConversationSystem()
    session = _make_session({})
    response = ConversationTurnResult(action=ConvActionType.SILENT)

    assert system._select_winner({"maren": response}, session) is response


def test_select_winner_prefers_never_spoken_participant() -> None:
    """Absent last-spoke data beats any recorded prior turn."""

    system = ConversationSystem()
    session = _make_session({"speaker": 3})
    responses = {
        "newcomer": ConversationTurnResult(action=ConvActionType.RESPOND, resp="fresh"),
        "speaker": ConversationTurnResult(action=ConvActionType.RESPOND, resp="old"),
    }

    assert system._select_winner(responses, session) == responses["newcomer"]


def test_select_winner_prefers_lower_last_spoke_turn() -> None:
    """Among equal actions, the less-recent speaker wins."""

    system = ConversationSystem()
    session = _make_session({"earlier": 1, "later": 4})
    responses = {
        "earlier": ConversationTurnResult(action=ConvActionType.RESPOND, resp="first"),
        "later": ConversationTurnResult(action=ConvActionType.RESPOND, resp="second"),
    }

    assert system._select_winner(responses, session) == responses["earlier"]


def test_winner_sort_key_uses_enum_order_as_final_fallback() -> None:
    """Action enum values are the final comparison when earlier fields tie."""

    system = ConversationSystem()
    session = _make_session({"aldric": 2, "maren": 2})
    interact_key = system._winner_sort_key(
        "aldric",
        ConversationTurnResult(action=ConvActionType.INTERACT, resp="hi"),
        session,
    )
    trade_key = system._winner_sort_key(
        "maren",
        ConversationTurnResult(action=ConvActionType.TRADE, target_id="aldric"),
        session,
    )

    assert interact_key < trade_key


def test_select_winner_returns_none_for_empty_responses() -> None:
    """An empty response set has no winner."""

    system = ConversationSystem()

    assert system._select_winner({}, _make_session({})) is None


def test_select_winner_returns_none_for_all_silent_group() -> None:
    """Multiple SILENT responses produce no winning action."""

    system = ConversationSystem()
    responses = {
        "aldric": ConversationTurnResult(action=ConvActionType.SILENT),
        "maren": ConversationTurnResult(action=ConvActionType.SILENT),
    }

    assert system._select_winner(responses, _make_session({})) is None
