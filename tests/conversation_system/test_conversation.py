# pyre-strict

"""Tests for conversation turn text formatting."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from conversation_system.conversation import ConversationSystem, format_turn_text
from conversation_system.types import ConversationSession
from memory_system.types import EventLogEntry, EventType, VillagerId as MemoryVillagerId
from villmage.game_types import ActionCategory, ItemType
from villmage.ai_coordinator.types import ConversationTurn
from villmage.ai_coordinator.types import (
    ConvActionType,
    ConversationTurnResult,
    TradeActionType,
    TradeItemSpec,
    TradeTurnResult,
)
from villmage.villager_state import CurrentAction, VillagerState


class _CanonVillager:
    """Minimal canon record used by conversation-system tests."""

    def __init__(self, name: str) -> None:
        """Store the authored display name."""

        self.name = name


class _CanonStub:
    """Return authored villager names from a simple id-name mapping."""

    def __init__(self, names_by_id: dict[str, str]) -> None:
        """Store the test villager-name mapping."""

        self._names_by_id = names_by_id

    def get_villager(self, villager_id: object) -> _CanonVillager:
        """Return the named test villager for the supplied id."""

        return _CanonVillager(name=self._names_by_id[str(villager_id)])


class _MemoryRecorder:
    """Collect memory log writes emitted by one resolved conversation turn."""

    def __init__(self) -> None:
        """Initialize the in-memory event collection."""

        self.events_by_villager: dict[str, list[EventLogEntry]] = {}

    def append_event(self, villager_id: MemoryVillagerId, entry: EventLogEntry) -> None:
        """Record one appended event under the villager's stable id."""

        self.events_by_villager.setdefault(str(villager_id), []).append(entry)


def _current_action(
    category: ActionCategory,
    detail: str | None = None,
) -> CurrentAction:
    """Build a minimal current-action snapshot for conversation tests."""

    return CurrentAction(category=category, detail=detail, completion_timestamp=0)


def _villager_state(
    villager_id: str,
    *,
    wakefulness: float = 50.0,
    current_action: CurrentAction | None = None,
) -> VillagerState:
    """Build one villager-state fixture with the supplied availability fields."""

    villager_state = VillagerState(villager_id)
    villager_state.wakefulness = wakefulness
    villager_state.set_current_action(current_action)
    return villager_state


def _trade_item(item: ItemType, quantity: int) -> TradeItemSpec:
    """Build one compact trade item spec for tests."""

    return TradeItemSpec(item=item, quantity=quantity)


def _trade_session(participant_ids: list[str], elapsed_game_minutes: int) -> ConversationSession:
    """Build a minimal conversation session for trade subprotocol tests."""

    return ConversationSession(
        participant_ids=list(participant_ids),
        all_participant_ids=list(participant_ids),
        full_turn_log=[],
        join_turn_index={villager_id: 0 for villager_id in participant_ids},
        elapsed_game_minutes=elapsed_game_minutes,
        last_spoke_turn={},
    )


def _loop_session(
    participant_ids: list[str],
    elapsed_game_minutes: int = 0,
) -> ConversationSession:
    """Build a minimal conversation session for turn-loop tests."""

    return ConversationSession(
        participant_ids=list(participant_ids),
        all_participant_ids=list(participant_ids),
        full_turn_log=[],
        join_turn_index={villager_id: 0 for villager_id in participant_ids},
        elapsed_game_minutes=elapsed_game_minutes,
        last_spoke_turn={},
    )


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


def test_resolve_single_turn_prompts_only_initiator_on_turn_zero() -> None:
    """Turn zero prompts only the initiator and records their turn."""

    coordinator = Mock()
    coordinator.get_conversation_turn.return_value = ConversationTurnResult(
        action=ConvActionType.RESPOND,
        resp="Hello.",
    )
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub({"initiator": "Initiator", "target": "Target"}),
    )
    session = ConversationSession(
        participant_ids=["initiator", "target"],
        all_participant_ids=["initiator", "target"],
        full_turn_log=[],
        join_turn_index={"initiator": 0, "target": 0},
        elapsed_game_minutes=0,
        last_spoke_turn={},
    )

    result = asyncio.run(system._resolve_single_turn(session, 120))

    assert result == ConversationTurnResult(action=ConvActionType.RESPOND, resp="Hello.")
    assert coordinator.get_conversation_turn.call_count == 1
    assert coordinator.get_conversation_turn.call_args.args[0] == "initiator"
    assert session.full_turn_log == [
        ConversationTurn(villager_id="initiator", text="Initiator: Hello.")
    ]
    assert session.last_spoke_turn["initiator"] == 0


def test_resolve_single_turn_removes_concurrent_leavers_and_returns_none() -> None:
    """Concurrent leaves remove both participants, append both leave turns, and end silent."""

    coordinator = Mock()
    coordinator.get_conversation_turn.side_effect = [
        ConversationTurnResult(action=ConvActionType.LEAVE),
        ConversationTurnResult(action=ConvActionType.LEAVE),
    ]
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub({"aldric": "Aldric", "maren": "Maren"}),
    )
    session = ConversationSession(
        participant_ids=["aldric", "maren"],
        all_participant_ids=["aldric", "maren"],
        full_turn_log=[ConversationTurn(villager_id="aldric", text="Earlier turn.")],
        join_turn_index={"aldric": 0, "maren": 0},
        elapsed_game_minutes=5,
        last_spoke_turn={"aldric": 0},
    )

    result = asyncio.run(system._resolve_single_turn(session, 125))

    assert result is None
    assert session.participant_ids == []
    assert session.full_turn_log[-2:] == [
        ConversationTurn(villager_id="aldric", text="Aldric leaves the conversation."),
        ConversationTurn(villager_id="maren", text="Maren leaves the conversation."),
    ]


def test_resolve_single_turn_handles_leave_before_selecting_winner() -> None:
    """A leaver is removed first and a remaining participant can still win normally."""

    coordinator = Mock()

    def _turn_for(villager_id: str, _snapshot: object, _game_time: int) -> ConversationTurnResult:
        """Return a deterministic result per prompted villager."""

        if villager_id == "aldric":
            return ConversationTurnResult(action=ConvActionType.LEAVE)
        return ConversationTurnResult(action=ConvActionType.CASUAL, resp="Maren hums softly.")

    coordinator.get_conversation_turn.side_effect = _turn_for
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub({"aldric": "Aldric", "maren": "Maren"}),
    )
    session = ConversationSession(
        participant_ids=["aldric", "maren"],
        all_participant_ids=["aldric", "maren"],
        full_turn_log=[ConversationTurn(villager_id="maren", text="Earlier turn.")],
        join_turn_index={"aldric": 0, "maren": 0},
        elapsed_game_minutes=5,
        last_spoke_turn={"maren": 0},
    )

    result = asyncio.run(system._resolve_single_turn(session, 130))

    assert result == ConversationTurnResult(
        action=ConvActionType.CASUAL,
        resp="Maren hums softly.",
    )
    assert session.participant_ids == ["maren"]
    assert session.full_turn_log[-2:] == [
        ConversationTurn(villager_id="aldric", text="Aldric leaves the conversation."),
        ConversationTurn(villager_id="maren", text="Maren hums softly."),
    ]


def test_resolve_single_turn_keeps_only_winning_turn_and_updates_winner_state() -> None:
    """Only the winning non-leave result is logged and marked as having spoken."""

    coordinator = Mock()

    def _turn_for(villager_id: str, _snapshot: object, _game_time: int) -> ConversationTurnResult:
        """Return distinct winner and loser actions."""

        if villager_id == "aldric":
            return ConversationTurnResult(action=ConvActionType.TRADE, target_id="maren")
        return ConversationTurnResult(action=ConvActionType.CONTINUE, resp="Maren keeps talking.")

    coordinator.get_conversation_turn.side_effect = _turn_for
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub({"aldric": "Aldric", "maren": "Maren"}),
    )
    session = ConversationSession(
        participant_ids=["aldric", "maren"],
        all_participant_ids=["aldric", "maren"],
        full_turn_log=[ConversationTurn(villager_id="maren", text="Earlier turn.")],
        join_turn_index={"aldric": 0, "maren": 0},
        elapsed_game_minutes=5,
        last_spoke_turn={"maren": 0},
    )

    result = asyncio.run(system._resolve_single_turn(session, 135))

    assert result == ConversationTurnResult(action=ConvActionType.TRADE, target_id="maren")
    assert session.full_turn_log[-1] == ConversationTurn(
        villager_id="aldric",
        text="Aldric asks Maren if they want to trade.",
    )
    assert len(session.full_turn_log) == 2
    assert session.last_spoke_turn == {"maren": 0, "aldric": 1}


def test_resolve_single_turn_writes_leave_and_winner_events_to_correct_memory_logs() -> None:
    """Leave events go to present villagers and the winner goes to post-leave participants only."""

    coordinator = Mock()

    def _turn_for(villager_id: str, _snapshot: object, _game_time: int) -> ConversationTurnResult:
        """Return one leave, one winner, and one discarded lower-priority action."""

        if villager_id == "aldric":
            return ConversationTurnResult(action=ConvActionType.LEAVE)
        if villager_id == "maren":
            return ConversationTurnResult(action=ConvActionType.RESPOND, resp="I agree.")
        return ConversationTurnResult(
            action=ConvActionType.CASUAL,
            resp="Sewalt studies the rafters.",
        )

    coordinator.get_conversation_turn.side_effect = _turn_for
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub(
            {"aldric": "Aldric", "maren": "Maren", "sewalt": "Sewalt"}
        ),
    )
    session = ConversationSession(
        participant_ids=["aldric", "maren", "sewalt"],
        all_participant_ids=["aldric", "maren", "sewalt"],
        full_turn_log=[ConversationTurn(villager_id="sewalt", text="Earlier turn.")],
        join_turn_index={"aldric": 0, "maren": 0, "sewalt": 0},
        elapsed_game_minutes=5,
        last_spoke_turn={"sewalt": 0},
    )

    result = asyncio.run(system._resolve_single_turn(session, 140))

    assert result == ConversationTurnResult(action=ConvActionType.RESPOND, resp="I agree.")
    assert [entry.text for entry in memory.events_by_villager["aldric"]] == [
        "Aldric leaves the conversation."
    ]
    assert [entry.text for entry in memory.events_by_villager["maren"]] == [
        "Aldric leaves the conversation.",
        "Maren: I agree.",
    ]
    assert [entry.text for entry in memory.events_by_villager["sewalt"]] == [
        "Aldric leaves the conversation.",
        "Maren: I agree.",
    ]
    for entries in memory.events_by_villager.values():
        assert "Sewalt studies the rafters." not in [entry.text for entry in entries]


def test_resolve_single_turn_returns_none_for_all_silent_group() -> None:
    """All-silent turns append nothing and return no winner."""

    coordinator = Mock()
    coordinator.get_conversation_turn.side_effect = [
        ConversationTurnResult(action=ConvActionType.SILENT),
        ConversationTurnResult(action=ConvActionType.SILENT),
    ]
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub({"aldric": "Aldric", "maren": "Maren"}),
    )
    session = ConversationSession(
        participant_ids=["aldric", "maren"],
        all_participant_ids=["aldric", "maren"],
        full_turn_log=[ConversationTurn(villager_id="aldric", text="Earlier turn.")],
        join_turn_index={"aldric": 0, "maren": 0},
        elapsed_game_minutes=5,
        last_spoke_turn={"aldric": 0},
    )

    result = asyncio.run(system._resolve_single_turn(session, 145))

    assert result is None
    assert session.full_turn_log == [ConversationTurn(villager_id="aldric", text="Earlier turn.")]
    assert memory.events_by_villager == {}


def test_pause_for_joiners_queries_only_eligible_villagers() -> None:
    """Only awake at-base non-participants are queried for a join decision."""

    coordinator = Mock()
    coordinator.get_join_decision.return_value = False
    villager_states = {
        "initiator": _villager_state("initiator"),
        "target": _villager_state("target"),
        "joiner": _villager_state(
            "joiner",
            current_action=_current_action(ActionCategory.RESTING, "watching the fire"),
        ),
        "explorer": _villager_state(
            "explorer",
            current_action=_current_action(ActionCategory.EXPLORING),
        ),
        "hauler": _villager_state(
            "hauler",
            current_action=_current_action(ActionCategory.HAULING),
        ),
        "sleeper": _villager_state("sleeper", wakefulness=0.0),
    }
    system = ConversationSystem(
        ai_coordinator=coordinator,
        villager_states=villager_states,
    )
    session = ConversationSession(
        participant_ids=["initiator", "target"],
        all_participant_ids=["initiator", "target"],
        full_turn_log=[
            ConversationTurn(villager_id="initiator", text="First."),
            ConversationTurn(villager_id="target", text="Second."),
        ],
        join_turn_index={"initiator": 0, "target": 0},
        elapsed_game_minutes=10,
        last_spoke_turn={"initiator": 0, "target": 1},
    )

    asyncio.run(system._pause_for_joiners(session, 150))

    queried_ids = [call.args[0] for call in coordinator.get_join_decision.call_args_list]
    assert queried_ids == ["joiner"]


def test_pause_for_joiners_uses_explicit_opening_excerpt_snapshot() -> None:
    """Join-decision snapshots always use the first two logged turns only."""

    coordinator = Mock()
    coordinator.get_join_decision.return_value = False
    joiner_state = _villager_state(
        "joiner",
        current_action=_current_action(ActionCategory.RESTING, "gathering sticks"),
    )
    system = ConversationSystem(
        ai_coordinator=coordinator,
        villager_states={"joiner": joiner_state},
    )
    full_turn_log = [
        ConversationTurn(villager_id="alpha", text="Turn 0."),
        ConversationTurn(villager_id="beta", text="Turn 1."),
        ConversationTurn(villager_id="gamma", text="Turn 2."),
    ]
    session = ConversationSession(
        participant_ids=["alpha", "beta"],
        all_participant_ids=["alpha", "beta"],
        full_turn_log=full_turn_log,
        join_turn_index={"alpha": 0, "beta": 0},
        elapsed_game_minutes=10,
        last_spoke_turn={"alpha": 0, "beta": 1},
    )

    asyncio.run(system._pause_for_joiners(session, 155))

    snapshot = coordinator.get_join_decision.call_args.args[2]
    assert snapshot.history == full_turn_log[:2]


def test_pause_for_joiners_adds_joiners_atomically_without_last_spoke_entry() -> None:
    """Accepted joiners update both rosters and join index without a last-spoke value."""

    coordinator = Mock()

    def _join_decision(
        villager_id: str,
        _description: str,
        _snapshot: object,
        _game_time: int,
    ) -> bool:
        """Return a deterministic join result per villager."""

        return villager_id == "joiner"

    coordinator.get_join_decision.side_effect = _join_decision
    system = ConversationSystem(
        ai_coordinator=coordinator,
        villager_states={
            "joiner": _villager_state("joiner"),
            "non_joiner": _villager_state("non_joiner"),
        },
    )
    session = ConversationSession(
        participant_ids=["initiator", "target"],
        all_participant_ids=["initiator", "target"],
        full_turn_log=[
            ConversationTurn(villager_id="initiator", text="First."),
            ConversationTurn(villager_id="target", text="Second."),
        ],
        join_turn_index={"initiator": 0, "target": 0},
        elapsed_game_minutes=10,
        last_spoke_turn={"initiator": 0, "target": 1},
    )

    asyncio.run(system._pause_for_joiners(session, 160))

    assert session.participant_ids == ["initiator", "target", "joiner"]
    assert session.all_participant_ids == ["initiator", "target", "joiner"]
    assert session.join_turn_index["joiner"] == len(session.full_turn_log)
    assert "joiner" not in session.last_spoke_turn
    assert "non_joiner" not in session.participant_ids
    assert "non_joiner" not in session.all_participant_ids


def test_pause_for_joiners_keeps_all_parallel_joiners() -> None:
    """All accepted joiners from one parallel batch are retained."""

    coordinator = Mock()

    async def _join_decision(
        villager_id: str,
        _description: str,
        _snapshot: object,
        _game_time: int,
    ) -> bool:
        """Yield once to exercise parallel join aggregation."""

        await asyncio.sleep(0)
        return villager_id in {"joiner_a", "joiner_b"}

    coordinator.get_join_decision.side_effect = _join_decision
    system = ConversationSystem(
        ai_coordinator=coordinator,
        villager_states={
            "joiner_a": _villager_state("joiner_a"),
            "joiner_b": _villager_state("joiner_b"),
        },
    )
    session = ConversationSession(
        participant_ids=["initiator", "target"],
        all_participant_ids=["initiator", "target"],
        full_turn_log=[
            ConversationTurn(villager_id="initiator", text="First."),
            ConversationTurn(villager_id="target", text="Second."),
        ],
        join_turn_index={"initiator": 0, "target": 0},
        elapsed_game_minutes=10,
        last_spoke_turn={"initiator": 0, "target": 1},
    )

    asyncio.run(system._pause_for_joiners(session, 165))

    assert session.participant_ids == ["initiator", "target", "joiner_a", "joiner_b"]
    assert session.all_participant_ids == ["initiator", "target", "joiner_a", "joiner_b"]


def test_run_trade_subprotocol_completes_when_partner_accepts_initiator_offer() -> None:
    """Partner acceptance completes the trade and swaps both sides' last offers."""

    coordinator = Mock()
    coordinator.get_trade_turn.side_effect = [
        TradeTurnResult(
            action=TradeActionType.MAKE_OFFER,
            items=[_trade_item(ItemType.PEACH, 2)],
        ),
        TradeTurnResult(action=TradeActionType.ACCEPT, items=[]),
    ]
    memory = _MemoryRecorder()
    initiator_state = _villager_state("initiator")
    partner_state = _villager_state("partner")
    initiator_state.modify_inventory(ItemType.PEACH, 3)
    partner_state.modify_inventory = Mock(wraps=partner_state.modify_inventory)
    initiator_state.modify_inventory = Mock(wraps=initiator_state.modify_inventory)
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub(
            {"initiator": "Initiator", "partner": "Partner", "bystander": "Bystander"}
        ),
        villager_states={
            "initiator": initiator_state,
            "partner": partner_state,
            "bystander": _villager_state("bystander"),
        },
    )
    session = _trade_session(["initiator", "partner", "bystander"], elapsed_game_minutes=10)

    asyncio.run(system._run_trade_subprotocol(session, "initiator", "partner", 200))

    assert session.active_trade is None
    assert session.elapsed_game_minutes == 10
    assert initiator_state.inventory[ItemType.PEACH] == 1
    assert partner_state.inventory[ItemType.PEACH] == 2
    assert initiator_state.modify_inventory.call_count == 1
    assert partner_state.modify_inventory.call_count == 1
    assert [entry.type for entry in memory.events_by_villager["bystander"]] == [
        EventType.TRADE,
        EventType.TRADE,
    ]
    assert memory.events_by_villager["bystander"][-1].text == (
        "Partner and Initiator complete the trade. "
        "Partner receives 2 PEACH. "
        "Initiator receives nothing."
    )


def test_run_trade_subprotocol_completes_when_initiator_accepts_partner_offer() -> None:
    """Initiator acceptance uses the partner's last offer and the initiator's own last offer."""

    coordinator = Mock()
    coordinator.get_trade_turn.side_effect = [
        TradeTurnResult(
            action=TradeActionType.MAKE_OFFER,
            items=[_trade_item(ItemType.LOG, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.MAKE_OFFER,
            items=[_trade_item(ItemType.COOKED_MEAT, 2)],
        ),
        TradeTurnResult(action=TradeActionType.ACCEPT, items=[]),
    ]
    initiator_state = _villager_state("initiator")
    partner_state = _villager_state("partner")
    initiator_state.modify_inventory(ItemType.LOG, 1)
    partner_state.modify_inventory(ItemType.COOKED_MEAT, 2)
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=_MemoryRecorder(),
        canon=_CanonStub({"initiator": "Initiator", "partner": "Partner"}),
        villager_states={
            "initiator": initiator_state,
            "partner": partner_state,
        },
    )
    session = _trade_session(["initiator", "partner"], elapsed_game_minutes=15)

    asyncio.run(system._run_trade_subprotocol(session, "initiator", "partner", 205))

    assert session.elapsed_game_minutes == 15
    assert initiator_state.inventory[ItemType.LOG] == 0
    assert initiator_state.inventory[ItemType.COOKED_MEAT] == 2
    assert partner_state.inventory[ItemType.COOKED_MEAT] == 0
    assert partner_state.inventory[ItemType.LOG] == 1


def test_run_trade_subprotocol_treats_accept_after_cancel_as_no_op_then_cancels_on_turn_six() -> None:
    """Invalid ACCEPT does not append history and still advances toward the six-turn cancel cap."""

    coordinator = Mock()
    coordinator.get_trade_turn.side_effect = [
        TradeTurnResult(action=TradeActionType.CANCEL, items=[]),
        TradeTurnResult(action=TradeActionType.ACCEPT, items=[]),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.STICK, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.PEACH, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.LOG, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.COOKED_MEAT, 1)],
        ),
    ]
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub(
            {"initiator": "Initiator", "partner": "Partner", "bystander": "Bystander"}
        ),
        villager_states={
            "initiator": _villager_state("initiator"),
            "partner": _villager_state("partner"),
            "bystander": _villager_state("bystander"),
        },
    )
    session = _trade_session(["initiator", "partner", "bystander"], elapsed_game_minutes=20)

    asyncio.run(system._run_trade_subprotocol(session, "initiator", "partner", 210))

    assert session.active_trade is None
    assert session.elapsed_game_minutes == 20
    assert coordinator.get_trade_turn.call_count == 6
    bystander_texts = [entry.text for entry in memory.events_by_villager["bystander"]]
    assert len(bystander_texts) == 6
    assert bystander_texts[0] == "Initiator cancels the trade."
    assert bystander_texts[-1] == "Initiator and Partner end the trade without an exchange."
    assert all("accepts" not in text for text in bystander_texts)


def test_run_trade_subprotocol_treats_accept_with_no_prior_partner_offer_as_no_op() -> None:
    """An initial ACCEPT with empty history is ignored and the trade continues normally."""

    coordinator = Mock()
    coordinator.get_trade_turn.side_effect = [
        TradeTurnResult(action=TradeActionType.ACCEPT, items=[]),
        TradeTurnResult(
            action=TradeActionType.MAKE_OFFER,
            items=[_trade_item(ItemType.PEACH, 1)],
        ),
        TradeTurnResult(action=TradeActionType.ACCEPT, items=[]),
    ]
    initiator_state = _villager_state("initiator")
    partner_state = _villager_state("partner")
    partner_state.modify_inventory(ItemType.PEACH, 1)
    memory = _MemoryRecorder()
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub({"initiator": "Initiator", "partner": "Partner"}),
        villager_states={
            "initiator": initiator_state,
            "partner": partner_state,
        },
    )
    session = _trade_session(["initiator", "partner"], elapsed_game_minutes=25)

    asyncio.run(system._run_trade_subprotocol(session, "initiator", "partner", 215))

    assert session.elapsed_game_minutes == 25
    assert initiator_state.inventory[ItemType.PEACH] == 1
    assert [entry.text for entry in memory.events_by_villager["initiator"]] == [
        "Partner offers 1 PEACH.",
        "Initiator and Partner complete the trade. Initiator receives 1 PEACH. Partner receives nothing.",
    ]


def test_run_trade_subprotocol_cancels_after_exactly_six_turns_without_acceptance() -> None:
    """Six non-completing turns end the trade with a shared cancellation event and no transfer."""

    coordinator = Mock()
    coordinator.get_trade_turn.side_effect = [
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.PEACH, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.LOG, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.STICK, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.COOKED_MEAT, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.LEAVES, 1)],
        ),
        TradeTurnResult(
            action=TradeActionType.REQUEST_ITEMS,
            items=[_trade_item(ItemType.RAW_HIDE, 1)],
        ),
    ]
    memory = _MemoryRecorder()
    initiator_state = _villager_state("initiator")
    partner_state = _villager_state("partner")
    initiator_state.modify_inventory(ItemType.PEACH, 2)
    partner_state.modify_inventory(ItemType.LOG, 2)
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub(
            {"initiator": "Initiator", "partner": "Partner", "bystander": "Bystander"}
        ),
        villager_states={
            "initiator": initiator_state,
            "partner": partner_state,
            "bystander": _villager_state("bystander"),
        },
    )
    session = _trade_session(["initiator", "partner", "bystander"], elapsed_game_minutes=30)

    asyncio.run(system._run_trade_subprotocol(session, "initiator", "partner", 220))

    assert session.active_trade is None
    assert session.elapsed_game_minutes == 30
    assert initiator_state.inventory[ItemType.PEACH] == 2
    assert partner_state.inventory[ItemType.LOG] == 2
    for villager_id in ["initiator", "partner", "bystander"]:
        assert memory.events_by_villager[villager_id][-1].text == (
            "Initiator and Partner end the trade without an exchange."
        )


def test_run_trade_subprotocol_honors_explicit_cancel_without_inventory_transfer() -> None:
    """Either side can cancel immediately, ending the trade without exchanging items."""

    coordinator = Mock()
    coordinator.get_trade_turn.side_effect = [
        TradeTurnResult(
            action=TradeActionType.MAKE_OFFER,
            items=[_trade_item(ItemType.PEACH, 1)],
        ),
        TradeTurnResult(action=TradeActionType.CANCEL, items=[]),
    ]
    memory = _MemoryRecorder()
    initiator_state = _villager_state("initiator")
    partner_state = _villager_state("partner")
    initiator_state.modify_inventory(ItemType.PEACH, 1)
    system = ConversationSystem(
        ai_coordinator=coordinator,
        memory_system=memory,
        canon=_CanonStub({"initiator": "Initiator", "partner": "Partner"}),
        villager_states={
            "initiator": initiator_state,
            "partner": partner_state,
        },
    )
    session = _trade_session(["initiator", "partner"], elapsed_game_minutes=35)

    asyncio.run(system._run_trade_subprotocol(session, "initiator", "partner", 225))

    assert session.elapsed_game_minutes == 35
    assert initiator_state.inventory[ItemType.PEACH] == 1
    assert partner_state.inventory == {}
    assert [entry.text for entry in memory.events_by_villager["partner"]] == [
        "Initiator offers 1 PEACH.",
        "Partner cancels the trade.",
        "Initiator and Partner end the trade without an exchange.",
    ]


def test_run_turn_loop_stops_when_participants_drop_to_one() -> None:
    """The loop exits immediately after a turn leaves one participant remaining."""

    system = ConversationSystem()
    session = _loop_session(["alpha", "beta"])
    resolve_call_count = 0

    async def _resolve(_session: ConversationSession, _game_time: int) -> ConversationTurnResult | None:
        """Drop to one participant on the first resolved turn."""

        nonlocal resolve_call_count
        resolve_call_count += 1
        session.participant_ids = ["beta"]
        return None

    setattr(system, "_resolve_single_turn", _resolve)

    asyncio.run(system._run_turn_loop(session, 300))

    assert resolve_call_count == 1
    assert session.elapsed_game_minutes == 5


def test_run_turn_loop_stops_at_exactly_sixty_minutes_without_turn_thirteen() -> None:
    """Twelve turns consume the full hour and the loop does not start a thirteenth."""

    system = ConversationSystem()
    session = _loop_session(["alpha", "beta"])
    resolve_call_count = 0
    pause_call_count = 0

    async def _resolve(_session: ConversationSession, _game_time: int) -> ConversationTurnResult | None:
        """Append one logged turn each time and keep the roster active."""

        nonlocal resolve_call_count
        resolve_call_count += 1
        session.full_turn_log.append(
            ConversationTurn(
                villager_id="alpha",
                text=f"Turn {resolve_call_count}.",
            )
        )
        return None

    async def _pause(_session: ConversationSession, _game_time: int) -> None:
        """Record one join-pause invocation without mutating the session."""

        nonlocal pause_call_count
        pause_call_count += 1

    setattr(system, "_resolve_single_turn", _resolve)
    setattr(system, "_pause_for_joiners", _pause)

    asyncio.run(system._run_turn_loop(session, 305))

    assert resolve_call_count == 12
    assert session.elapsed_game_minutes == 60
    assert pause_call_count == 1


def test_run_turn_loop_exits_cleanly_when_both_end_conditions_become_true() -> None:
    """The loop handles simultaneous roster and time termination in one return path."""

    system = ConversationSystem()
    session = _loop_session(["alpha", "beta"], elapsed_game_minutes=55)
    resolve_call_count = 0

    async def _resolve(_session: ConversationSession, _game_time: int) -> ConversationTurnResult | None:
        """Force the final participant drop on the turn that reaches sixty minutes."""

        nonlocal resolve_call_count
        resolve_call_count += 1
        session.participant_ids = ["alpha"]
        return None

    setattr(system, "_resolve_single_turn", _resolve)

    asyncio.run(system._run_turn_loop(session, 310))

    assert resolve_call_count == 1
    assert session.participant_ids == ["alpha"]
    assert session.elapsed_game_minutes == 60


def test_run_turn_loop_counts_silent_turns_toward_elapsed_minutes() -> None:
    """Elapsed game time advances by five minutes even when a turn is silent."""

    system = ConversationSystem()
    session = _loop_session(["alpha", "beta"])
    resolve_call_count = 0

    async def _resolve(_session: ConversationSession, _game_time: int) -> ConversationTurnResult | None:
        """Return one silent turn, then one final voiced turn."""

        nonlocal resolve_call_count
        resolve_call_count += 1
        if resolve_call_count == 1:
            return None
        session.full_turn_log.append(ConversationTurn(villager_id="beta", text="Beta: Done."))
        session.participant_ids = ["beta"]
        return ConversationTurnResult(action=ConvActionType.RESPOND, resp="Done.")

    setattr(system, "_resolve_single_turn", _resolve)

    asyncio.run(system._run_turn_loop(session, 315))

    assert resolve_call_count == 2
    assert session.elapsed_game_minutes == 10
    assert session.full_turn_log == [ConversationTurn(villager_id="beta", text="Beta: Done.")]


def test_run_turn_loop_pauses_for_joiners_once_after_second_logged_turn_and_resumes() -> None:
    """The join pause fires exactly once at log length two and the loop then continues."""

    system = ConversationSystem()
    session = _loop_session(["alpha", "beta"])
    resolve_call_count = 0
    pause_log_lengths: list[int] = []

    async def _resolve(_session: ConversationSession, _game_time: int) -> ConversationTurnResult | None:
        """Append three logged turns, ending after the third."""

        nonlocal resolve_call_count
        resolve_call_count += 1
        session.full_turn_log.append(
            ConversationTurn(villager_id="alpha", text=f"Turn {resolve_call_count}.")
        )
        if resolve_call_count == 3:
            session.participant_ids = ["alpha"]
        return ConversationTurnResult(action=ConvActionType.RESPOND, resp="spoken")

    async def _pause(_session: ConversationSession, _game_time: int) -> None:
        """Record the log length at the moment the join pause is triggered."""

        pause_log_lengths.append(len(session.full_turn_log))

    setattr(system, "_resolve_single_turn", _resolve)
    setattr(system, "_pause_for_joiners", _pause)

    asyncio.run(system._run_turn_loop(session, 320))

    assert resolve_call_count == 3
    assert pause_log_lengths == [2]
    assert session.elapsed_game_minutes == 15


def test_run_turn_loop_suspends_for_trade_then_resumes_without_trade_time_cost() -> None:
    """A trade result triggers the subprotocol with winner-target ids and then conversation continues."""

    system = ConversationSystem()
    session = _loop_session(["initiator", "partner"])
    resolve_call_count = 0
    trade_calls: list[tuple[str, str, int]] = []

    async def _resolve(_session: ConversationSession, _game_time: int) -> ConversationTurnResult | None:
        """Produce a normal turn, then a trade, then one final post-trade turn."""

        nonlocal resolve_call_count
        resolve_call_count += 1
        if resolve_call_count == 1:
            session.full_turn_log.append(ConversationTurn(villager_id="initiator", text="First."))
            return ConversationTurnResult(action=ConvActionType.RESPOND, resp="First.")
        if resolve_call_count == 2:
            session.full_turn_log.append(
                ConversationTurn(villager_id="initiator", text="Initiator asks Partner if they want to trade.")
            )
            return ConversationTurnResult(
                action=ConvActionType.TRADE,
                target_id="partner",
            )
        session.full_turn_log.append(ConversationTurn(villager_id="partner", text="After trade."))
        session.participant_ids = ["partner"]
        return ConversationTurnResult(action=ConvActionType.RESPOND, resp="After trade.")

    async def _trade(
        _session: ConversationSession,
        trade_initiator_id: str,
        trade_partner_id: str,
        game_time: int,
    ) -> None:
        """Record one invoked trade subprotocol call without mutating elapsed time."""

        trade_calls.append((trade_initiator_id, trade_partner_id, game_time))

    async def _pause(_session: ConversationSession, _game_time: int) -> None:
        """Leave join-pause behavior inert for the trade-loop test."""

        return None

    setattr(system, "_resolve_single_turn", _resolve)
    setattr(system, "_run_trade_subprotocol", _trade)
    setattr(system, "_pause_for_joiners", _pause)

    asyncio.run(system._run_turn_loop(session, 325))

    assert resolve_call_count == 3
    assert trade_calls == [("initiator", "partner", 325)]
    assert session.elapsed_game_minutes == 15
