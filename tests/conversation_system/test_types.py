# pyre-strict

"""Tests for conversation-system state types."""

from conversation_system.types import ActiveTrade, ConversationSession
from villmage.ai_coordinator.types import (
    ConversationSnapshot,
    ConversationTurn,
    TradeActionType,
    TradeTurnRecord,
)


def test_snapshot_for_initiator_returns_full_turn_log() -> None:
    """An initial participant sees the complete history."""

    first_turn = ConversationTurn(villager_id="aldric", text="Aldric: Hello.")
    second_turn = ConversationTurn(villager_id="maren", text="Maren: Hi.")
    session = ConversationSession(
        participant_ids=["aldric", "maren"],
        all_participant_ids=["aldric", "maren"],
        full_turn_log=[first_turn, second_turn],
        join_turn_index={"aldric": 0, "maren": 0},
        elapsed_game_minutes=10,
        last_spoke_turn={"aldric": 0, "maren": 1},
    )

    snapshot = session.snapshot_for("aldric")

    assert snapshot == ConversationSnapshot(
        participant_ids=["aldric", "maren"],
        history=[first_turn, second_turn],
        elapsed_game_minutes=10,
    )


def test_snapshot_for_late_joiner_excludes_earlier_turns() -> None:
    """A late joiner only sees turns from their join index onward."""

    first_turn = ConversationTurn(villager_id="aldric", text="Aldric: Hello.")
    second_turn = ConversationTurn(villager_id="maren", text="Maren: Hi.")
    third_turn = ConversationTurn(villager_id="sela", text="Sela: Mind if I join?")
    session = ConversationSession(
        participant_ids=["aldric", "maren", "sela"],
        all_participant_ids=["aldric", "maren", "sela"],
        full_turn_log=[first_turn, second_turn, third_turn],
        join_turn_index={"aldric": 0, "maren": 0, "sela": 2},
        elapsed_game_minutes=15,
        last_spoke_turn={"aldric": 0, "maren": 1, "sela": 2},
    )

    snapshot = session.snapshot_for("sela")

    assert snapshot.history == [third_turn]
    assert first_turn not in snapshot.history
    assert second_turn not in snapshot.history


def test_snapshot_for_empty_turn_log_returns_empty_history() -> None:
    """An empty conversation log yields an empty snapshot history."""

    session = ConversationSession(
        participant_ids=["aldric", "maren"],
        all_participant_ids=["aldric", "maren"],
        full_turn_log=[],
        join_turn_index={"aldric": 0, "maren": 0},
        elapsed_game_minutes=0,
        last_spoke_turn={},
    )

    snapshot = session.snapshot_for("aldric")

    assert snapshot.history == []


def test_conversation_session_construction_preserves_fields() -> None:
    """ConversationSession stores provided fields and defaults active_trade to None."""

    session = ConversationSession(
        participant_ids=["aldric", "maren"],
        all_participant_ids=["aldric", "maren"],
        full_turn_log=[],
        join_turn_index={"aldric": 0, "maren": 0},
        elapsed_game_minutes=0,
        last_spoke_turn={},
    )

    assert session.participant_ids == ["aldric", "maren"]
    assert session.all_participant_ids == ["aldric", "maren"]
    assert session.join_turn_index == {"aldric": 0, "maren": 0}
    assert session.active_trade is None


def test_active_trade_turn_count_parity_matches_turn_owner_spec() -> None:
    """Trade turn ownership alternates by turn_count parity."""

    trade = ActiveTrade(
        initiator_id="aldric",
        partner_id="maren",
        history=[
            TradeTurnRecord(
                villager_id="aldric",
                action=TradeActionType.MAKE_OFFER,
                items=[],
            )
        ],
        turn_count=0,
    )

    def whose_turn(active_trade: ActiveTrade) -> str:
        """Derive the current actor from the authored parity rule."""

        if active_trade.turn_count % 2 == 0:
            return active_trade.initiator_id
        return active_trade.partner_id

    assert whose_turn(trade) == "aldric"

    trade.turn_count = 1
    assert whose_turn(trade) == "maren"

    trade.turn_count = 2
    assert whose_turn(trade) == "aldric"
