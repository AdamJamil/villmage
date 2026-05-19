# pyre-strict

"""Mutable in-flight state types for the conversation system."""

from dataclasses import dataclass

from villmage.ai_coordinator.types import (
    ConversationSnapshot,
    ConversationTurn,
    TradeTurnRecord,
)


@dataclass
class ActiveTrade:
    """In-progress trade sub-protocol state for one conversation session."""

    initiator_id: str
    partner_id: str
    history: list[TradeTurnRecord]
    turn_count: int


@dataclass
class ConversationSession:
    """Full mutable state for one in-progress conversation."""

    participant_ids: list[str]
    all_participant_ids: list[str]
    full_turn_log: list[ConversationTurn]
    join_turn_index: dict[str, int]
    elapsed_game_minutes: int
    last_spoke_turn: dict[str, int]
    active_trade: ActiveTrade | None = None

    def snapshot_for(self, villager_id: str) -> ConversationSnapshot:
        """Return the caller-visible conversation snapshot for one villager."""

        return ConversationSnapshot(
            participant_ids=self.participant_ids,
            history=self.full_turn_log[self.join_turn_index[villager_id] :],
            elapsed_game_minutes=self.elapsed_game_minutes,
        )
