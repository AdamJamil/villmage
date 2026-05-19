# pyre-strict

"""Conversation-system orchestration entry points and pure helpers."""

from villmage.ai_coordinator.types import ConvActionType, ConversationTurnResult


def format_turn_text(
    result: ConversationTurnResult,
    villager_name: str,
    target_name: str | None = None,
) -> str:
    """Render one resolved conversation turn into its logged text."""

    if result.action in {
        ConvActionType.INTERRUPT,
        ConvActionType.CONTINUE,
        ConvActionType.RESPOND,
        ConvActionType.CHANGE_TOPIC,
    }:
        response = result.resp
        if response is None:
            raise ValueError("Speech actions require resp text.")
        return f"{villager_name}: {response}"

    if result.action in {ConvActionType.INTERACT, ConvActionType.CASUAL}:
        response = result.resp
        if response is None:
            raise ValueError("Interaction actions require resp text.")
        return response

    if result.action is ConvActionType.TRADE:
        if target_name is None:
            raise ValueError("TRADE requires target_name.")
        return f"{villager_name} asks {target_name} if they want to trade."

    if result.action is ConvActionType.LEAVE:
        return f"{villager_name} leaves the conversation."

    raise ValueError(f"Unsupported conversation action: {result.action!r}")


class ConversationSystem:
    """Placeholder conversation-system shell for incremental implementation."""

