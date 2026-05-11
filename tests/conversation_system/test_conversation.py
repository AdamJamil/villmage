# pyre-strict

"""Tests for conversation turn text formatting."""

import pytest

from conversation_system.conversation import ConversationSystem, format_turn_text
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
