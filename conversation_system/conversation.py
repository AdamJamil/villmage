# pyre-strict

"""Conversation-system orchestration entry points and pure helpers."""

from conversation_system.types import ConversationSession
from villmage.ai_coordinator.types import ConvActionType, ConversationTurnResult


_ACTION_PRIORITY: dict[ConvActionType, int] = {
    ConvActionType.INTERACT: 0,
    ConvActionType.TRADE: 1,
    ConvActionType.INTERRUPT: 2,
    ConvActionType.CONTINUE: 3,
    ConvActionType.RESPOND: 4,
    ConvActionType.CHANGE_TOPIC: 5,
    ConvActionType.CASUAL: 6,
    ConvActionType.SILENT: 7,
}


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
    """Conversation-system orchestration shell."""

    def _select_winner(
        self,
        responses: dict[str, ConversationTurnResult],
        session: ConversationSession,
    ) -> ConversationTurnResult | None:
        """Return the winning non-LEAVE response for one turn."""

        if not responses:
            return None

        if len(responses) == 1:
            return next(iter(responses.values()))

        non_silent_responses = {
            villager_id: result
            for villager_id, result in responses.items()
            if result.action is not ConvActionType.SILENT
        }
        if not non_silent_responses:
            return None

        return min(
            non_silent_responses.items(),
            key=lambda item: self._winner_sort_key(item[0], item[1], session),
        )[1]

    def _winner_sort_key(
        self,
        villager_id: str,
        result: ConversationTurnResult,
        session: ConversationSession,
    ) -> tuple[int, int, int, int]:
        """Build the deterministic ordering key for winner selection."""

        last_spoke_turn = session.last_spoke_turn.get(villager_id)
        recency_group = 0 if last_spoke_turn is None else 1
        recency_value = -1 if last_spoke_turn is None else last_spoke_turn
        return (
            _ACTION_PRIORITY[result.action],
            recency_group,
            recency_value,
            result.action.value,
        )
