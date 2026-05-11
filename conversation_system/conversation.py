# pyre-strict

"""Conversation-system orchestration entry points and pure helpers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Awaitable, Protocol, cast

from character_canon.types import VillagerCanon, VillagerId as CanonVillagerId
from conversation_system.types import ActiveTrade, ConversationSession
from memory_system.types import EventLogEntry, EventType, VillagerId as MemoryVillagerId
from villmage.game_types import ActionCategory, ItemType
from villmage.ai_coordinator.types import (
    ConvActionType,
    ConversationSnapshot,
    ConversationTurn,
    ConversationTurnResult,
    TradeActionType,
    TradeItemSpec,
    TradeSnapshot,
    TradeTurnRecord,
    TradeTurnResult,
)
from villmage.villager_state import VillagerState


class _AICoordinatorProtocol(Protocol):
    """Minimal AI coordinator surface required by ConversationSystem."""

    def get_conversation_turn(
        self,
        villager_id: str,
        snapshot: ConversationSnapshot,
        game_time: int,
    ) -> ConversationTurnResult | Awaitable[ConversationTurnResult]:
        """Return one villager's conversation-turn decision."""

    def get_join_decision(
        self,
        villager_id: str,
        current_action_description: str,
        snapshot: ConversationSnapshot,
        game_time: int,
    ) -> bool | Awaitable[bool]:
        """Return whether one villager chooses to join an active conversation."""

    def get_trade_turn(
        self,
        villager_id: str,
        snapshot: TradeSnapshot,
        game_time: int,
    ) -> TradeTurnResult | Awaitable[TradeTurnResult]:
        """Return one villager's trade-turn decision."""


class _MemorySystemProtocol(Protocol):
    """Minimal memory-system surface required by ConversationSystem."""

    def append_event(
        self,
        villager_id: MemoryVillagerId,
        entry: EventLogEntry,
    ) -> None:
        """Append one event to one villager's memory log."""


class _CharacterCanonProtocol(Protocol):
    """Minimal character-canon surface required by ConversationSystem."""

    def get_villager(self, villager_id: CanonVillagerId) -> VillagerCanon:
        """Return the authored canon record for one villager."""


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

    _ai_coordinator: _AICoordinatorProtocol | None
    _memory_system: _MemorySystemProtocol | None
    _canon: _CharacterCanonProtocol | None
    _villager_states: dict[str, VillagerState] | None

    def __init__(
        self,
        ai_coordinator: _AICoordinatorProtocol | None = None,
        memory_system: _MemorySystemProtocol | None = None,
        canon: _CharacterCanonProtocol | None = None,
        villager_states: dict[str, VillagerState] | None = None,
    ) -> None:
        """Store the conversation-system dependencies used during orchestration."""

        self._ai_coordinator = ai_coordinator
        self._memory_system = memory_system
        self._canon = canon
        self._villager_states = villager_states

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

    async def _resolve_single_turn(
        self,
        session: ConversationSession,
        game_time: int,
    ) -> ConversationTurnResult | None:
        """Resolve one full conversation turn and write its memory effects."""

        prompt_ids = (
            [session.participant_ids[0]]
            if len(session.full_turn_log) == 0
            else list(session.participant_ids)
        )
        responses = await self._prompt_turn_responses(prompt_ids, session, game_time)

        for villager_id in prompt_ids:
            result = responses[villager_id]
            if result.action is not ConvActionType.LEAVE:
                continue

            leave_turn = ConversationTurn(
                villager_id=villager_id,
                text=format_turn_text(result, self._villager_name(villager_id)),
            )
            present_participant_ids = list(session.participant_ids)
            session.participant_ids.remove(villager_id)
            session.full_turn_log.append(leave_turn)
            self._write_turn_to_memory(present_participant_ids, leave_turn, game_time)

        remaining_responses = {
            villager_id: result
            for villager_id, result in responses.items()
            if result.action is not ConvActionType.LEAVE
        }
        winner = self._select_winner(remaining_responses, session)
        if winner is None:
            return None

        winner_id = self._winner_id(remaining_responses, winner)
        turn = ConversationTurn(
            villager_id=winner_id,
            text=format_turn_text(
                winner,
                self._villager_name(winner_id),
                self._villager_name(winner.target_id) if winner.target_id is not None else None,
            ),
        )
        session.full_turn_log.append(turn)
        session.last_spoke_turn[winner_id] = len(session.full_turn_log) - 1
        self._write_turn_to_memory(session.participant_ids, turn, game_time)
        return winner

    async def _prompt_turn_responses(
        self,
        participant_ids: list[str],
        session: ConversationSession,
        game_time: int,
    ) -> dict[str, ConversationTurnResult]:
        """Prompt the selected participants and return their turn results by id."""

        response_pairs = await asyncio.gather(
            *[
                self._prompt_single_participant(villager_id, session, game_time)
                for villager_id in participant_ids
            ]
        )
        return dict(response_pairs)

    async def _prompt_single_participant(
        self,
        villager_id: str,
        session: ConversationSession,
        game_time: int,
    ) -> tuple[str, ConversationTurnResult]:
        """Prompt one participant for their next conversation turn."""

        ai_coordinator = self._require_ai_coordinator()
        snapshot = session.snapshot_for(villager_id)
        result_object = ai_coordinator.get_conversation_turn(
            villager_id,
            snapshot,
            game_time,
        )
        result = cast(
            ConversationTurnResult,
            await self._resolve_maybe_awaitable(result_object),
        )
        return (villager_id, result)

    async def _pause_for_joiners(
        self,
        session: ConversationSession,
        game_time: int,
    ) -> None:
        """Query eligible bystanders in parallel and atomically add all joiners."""

        eligible_ids = self._eligible_joiner_ids(session)
        if not eligible_ids:
            return

        snapshot = ConversationSnapshot(
            participant_ids=list(session.participant_ids),
            history=session.full_turn_log[:2],
            elapsed_game_minutes=session.elapsed_game_minutes,
        )
        decision_pairs = await asyncio.gather(
            *[
                self._get_join_decision(villager_id, snapshot, game_time)
                for villager_id in eligible_ids
            ]
        )
        join_turn_index = len(session.full_turn_log)
        joiner_ids = [
            villager_id for villager_id, should_join in decision_pairs if should_join
        ]
        for villager_id in joiner_ids:
            session.participant_ids.append(villager_id)
            session.all_participant_ids.append(villager_id)
            session.join_turn_index[villager_id] = join_turn_index

    async def _run_turn_loop(
        self,
        session: ConversationSession,
        game_time: int,
    ) -> None:
        """Resolve conversation turns until a roster or time end condition is met."""

        has_paused_for_joiners = False
        while True:
            result = await self._resolve_single_turn(session, game_time)
            session.elapsed_game_minutes += 5
            if self._should_end_turn_loop(session):
                return
            if not has_paused_for_joiners and len(session.full_turn_log) == 2:
                await self._pause_for_joiners(session, game_time)
                has_paused_for_joiners = True
            if result is not None and result.action is ConvActionType.TRADE:
                trade_partner_id = result.target_id
                if trade_partner_id is None:
                    raise ValueError("TRADE turn result requires target_id.")
                winner_id = session.full_turn_log[-1].villager_id
                await self._run_trade_subprotocol(
                    session,
                    trade_initiator_id=winner_id,
                    trade_partner_id=trade_partner_id,
                    game_time=game_time,
                )

    async def _get_join_decision(
        self,
        villager_id: str,
        snapshot: ConversationSnapshot,
        game_time: int,
    ) -> tuple[str, bool]:
        """Return one eligible villager's join decision."""

        ai_coordinator = self._require_ai_coordinator()
        decision_object = ai_coordinator.get_join_decision(
            villager_id,
            self._current_action_description(villager_id),
            snapshot,
            game_time,
        )
        decision = cast(bool, await self._resolve_maybe_awaitable(decision_object))
        return (villager_id, decision)

    def _eligible_joiner_ids(self, session: ConversationSession) -> list[str]:
        """Return all current bystanders eligible for a turn-two join query."""

        villager_states = self._require_villager_states()
        return [
            villager_id
            for villager_id, villager_state in villager_states.items()
            if self._can_query_joiner(villager_id, villager_state, session)
        ]

    def _can_query_joiner(
        self,
        villager_id: str,
        villager_state: VillagerState,
        session: ConversationSession,
    ) -> bool:
        """Return whether one villager meets the authored join-query filter."""

        if villager_id in session.participant_ids or villager_state.wakefulness <= 0:
            return False
        current_action = villager_state.current_action
        if current_action is None:
            return True
        return current_action.category not in {
            ActionCategory.EXPLORING,
            ActionCategory.HAULING,
        }

    def _current_action_description(self, villager_id: str) -> str:
        """Return a prompt-ready description of one villager's current activity."""

        villager_state = self._require_villager_states()[villager_id]
        current_action = villager_state.current_action
        if current_action is None:
            return "idle at base"
        if current_action.detail is not None:
            return current_action.detail
        return current_action.category.name.lower().replace("_", " ")

    @staticmethod
    def _should_end_turn_loop(session: ConversationSession) -> bool:
        """Return whether the conversation loop must stop after the latest turn."""

        return len(session.participant_ids) <= 1 or session.elapsed_game_minutes >= 60

    def _write_turn_to_memory(
        self,
        participant_ids: list[str],
        turn: ConversationTurn,
        game_time: int,
    ) -> None:
        """Write one resolved conversation turn to each supplied participant log."""

        memory_system = self._require_memory_system()
        entry = EventLogEntry(
            game_time=game_time,
            type=EventType.CONVO_TURN,
            text=turn.text,
        )
        for participant_id in participant_ids:
            memory_system.append_event(MemoryVillagerId(participant_id), entry)

    async def _run_trade_subprotocol(
        self,
        session: ConversationSession,
        trade_initiator_id: str,
        trade_partner_id: str,
        game_time: int,
    ) -> None:
        """Run one complete trade negotiation without consuming game time."""

        active_trade = ActiveTrade(
            initiator_id=trade_initiator_id,
            partner_id=trade_partner_id,
            history=[],
            turn_count=0,
        )
        session.active_trade = active_trade
        while True:
            if active_trade.turn_count == 6:
                self._write_trade_memory_entry(
                    session.participant_ids,
                    self._trade_cancellation_text(
                        active_trade.initiator_id,
                        active_trade.partner_id,
                    ),
                    game_time,
                )
                session.active_trade = None
                return

            turn_villager_id = self._trade_turn_villager_id(active_trade)
            trade_result = await self._prompt_trade_turn(
                turn_villager_id,
                active_trade,
                game_time,
            )

            if trade_result.action is TradeActionType.ACCEPT:
                counterpart_id = self._trade_counterpart_id(active_trade, turn_villager_id)
                counterpart_offer = self._latest_offer_from(
                    active_trade.history,
                    counterpart_id,
                )
                if counterpart_offer is None:
                    active_trade.turn_count += 1
                    continue
                own_offer = self._latest_offer_from(active_trade.history, turn_villager_id)
                self._transfer_trade_items(
                    acceptor_id=turn_villager_id,
                    counterpart_id=counterpart_id,
                    acceptor_offer=own_offer.items if own_offer is not None else [],
                    counterpart_offer=counterpart_offer.items,
                )
                self._write_trade_memory_entry(
                    session.participant_ids,
                    self._trade_completion_text(
                        acceptor_id=turn_villager_id,
                        counterpart_id=counterpart_id,
                        acceptor_offer=own_offer.items if own_offer is not None else [],
                        counterpart_offer=counterpart_offer.items,
                    ),
                    game_time,
                )
                session.active_trade = None
                return

            trade_record = TradeTurnRecord(
                villager_id=turn_villager_id,
                action=trade_result.action,
                items=trade_result.items,
                speech=trade_result.speech,
            )
            active_trade.history.append(trade_record)
            active_trade.turn_count += 1
            self._write_trade_memory_entry(
                session.participant_ids,
                self._trade_turn_text(trade_record),
                game_time,
            )
            if (
                trade_result.action is TradeActionType.CANCEL
                and len(active_trade.history) > 1
            ):
                self._write_trade_memory_entry(
                    session.participant_ids,
                    self._trade_cancellation_text(
                        active_trade.initiator_id,
                        active_trade.partner_id,
                    ),
                    game_time,
                )
                session.active_trade = None
                return

    async def _prompt_trade_turn(
        self,
        villager_id: str,
        active_trade: ActiveTrade,
        game_time: int,
    ) -> TradeTurnResult:
        """Prompt one villager for a trade-turn result."""

        ai_coordinator = self._require_ai_coordinator()
        result_object = ai_coordinator.get_trade_turn(
            villager_id,
            TradeSnapshot(
                other_villager_id=self._trade_counterpart_id(active_trade, villager_id),
                history=active_trade.history,
                turn_count=active_trade.turn_count,
            ),
            game_time,
        )
        result = cast(
            TradeTurnResult,
            await self._resolve_maybe_awaitable(result_object),
        )
        return result

    @staticmethod
    def _trade_turn_villager_id(active_trade: ActiveTrade) -> str:
        """Return whose trade turn it is from turn-count parity."""

        if active_trade.turn_count % 2 == 0:
            return active_trade.initiator_id
        return active_trade.partner_id

    @staticmethod
    def _trade_counterpart_id(active_trade: ActiveTrade, villager_id: str) -> str:
        """Return the other participant in the active trade."""

        if villager_id == active_trade.initiator_id:
            return active_trade.partner_id
        return active_trade.initiator_id

    @staticmethod
    def _latest_offer_from(
        history: list[TradeTurnRecord],
        villager_id: str,
    ) -> TradeTurnRecord | None:
        """Return one villager's most recent `MAKE_OFFER` record, if any."""

        for record in reversed(history):
            if (
                record.villager_id == villager_id
                and record.action is TradeActionType.MAKE_OFFER
            ):
                return record
        return None

    def _transfer_trade_items(
        self,
        acceptor_id: str,
        counterpart_id: str,
        acceptor_offer: list[TradeItemSpec],
        counterpart_offer: list[TradeItemSpec],
    ) -> None:
        """Apply both inventory exchanges after validating all required removals."""

        villager_states = self._require_villager_states()
        acceptor_state = villager_states[acceptor_id]
        counterpart_state = villager_states[counterpart_id]
        acceptor_deltas = self._net_trade_deltas(
            offered_items=acceptor_offer,
            received_items=counterpart_offer,
        )
        counterpart_deltas = self._net_trade_deltas(
            offered_items=counterpart_offer,
            received_items=acceptor_offer,
        )
        self._validate_trade_deltas(acceptor_state, acceptor_deltas)
        self._validate_trade_deltas(counterpart_state, counterpart_deltas)
        self._apply_inventory_deltas(acceptor_state, acceptor_deltas)
        self._apply_inventory_deltas(counterpart_state, counterpart_deltas)

    @staticmethod
    def _net_trade_deltas(
        offered_items: list[TradeItemSpec],
        received_items: list[TradeItemSpec],
    ) -> dict[ItemType, int]:
        """Collapse one side's offered and received items into net per-item deltas."""

        deltas: dict[ItemType, int] = {}
        for item_spec in offered_items:
            deltas[item_spec.item] = deltas.get(item_spec.item, 0) - item_spec.quantity
        for item_spec in received_items:
            deltas[item_spec.item] = deltas.get(item_spec.item, 0) + item_spec.quantity
        return deltas

    @staticmethod
    def _validate_trade_deltas(
        villager_state: VillagerState,
        deltas: dict[ItemType, int],
    ) -> None:
        """Ensure applying the supplied deltas will not make counts negative."""

        for item, delta in deltas.items():
            if delta >= 0:
                continue
            if villager_state.inventory.get(item, 0) + delta < 0:
                raise ValueError(f"Inventory count for {item!r} cannot be negative.")

    @staticmethod
    def _apply_inventory_deltas(
        villager_state: VillagerState,
        deltas: dict[ItemType, int],
    ) -> None:
        """Apply one villager's validated item deltas."""

        for item, delta in deltas.items():
            if delta == 0:
                continue
            villager_state.modify_inventory(item, delta)

    def _write_trade_memory_entry(
        self,
        participant_ids: list[str],
        text: str,
        game_time: int,
    ) -> None:
        """Append one trade event to every current conversation participant log."""

        memory_system = self._require_memory_system()
        entry = EventLogEntry(game_time=game_time, type=EventType.TRADE, text=text)
        for participant_id in participant_ids:
            memory_system.append_event(MemoryVillagerId(participant_id), entry)

    def _trade_turn_text(self, trade_record: TradeTurnRecord) -> str:
        """Render one logged trade-turn record into self-contained text."""

        villager_name = self._villager_name(trade_record.villager_id)
        action_text = self._trade_action_text(trade_record)
        if trade_record.speech is None:
            return f"{villager_name} {action_text}"
        return f'{villager_name} {action_text} They say, "{trade_record.speech}"'

    @staticmethod
    def _trade_action_text(trade_record: TradeTurnRecord) -> str:
        """Render the non-speech portion of one trade action."""

        if trade_record.action is TradeActionType.MAKE_OFFER:
            return f"offers {ConversationSystem._format_trade_items(trade_record.items)}."
        if trade_record.action is TradeActionType.REQUEST_ITEMS:
            return (
                f"requests {ConversationSystem._format_trade_items(trade_record.items)}."
            )
        if trade_record.action is TradeActionType.CANCEL:
            return "cancels the trade."
        return "accepts the trade."

    def _trade_completion_text(
        self,
        acceptor_id: str,
        counterpart_id: str,
        acceptor_offer: list[TradeItemSpec],
        counterpart_offer: list[TradeItemSpec],
    ) -> str:
        """Render the completion event for one successful trade."""

        acceptor_name = self._villager_name(acceptor_id)
        counterpart_name = self._villager_name(counterpart_id)
        return (
            f"{acceptor_name} and {counterpart_name} complete the trade. "
            f"{acceptor_name} receives {self._format_trade_items(counterpart_offer)}. "
            f"{counterpart_name} receives {self._format_trade_items(acceptor_offer)}."
        )

    def _trade_cancellation_text(self, initiator_id: str, partner_id: str) -> str:
        """Render the shared trade-cancelled event text."""

        initiator_name = self._villager_name(initiator_id)
        partner_name = self._villager_name(partner_id)
        return f"{initiator_name} and {partner_name} end the trade without an exchange."

    @staticmethod
    def _format_trade_items(items: list[TradeItemSpec]) -> str:
        """Render one item list as a compact comma-separated quantity string."""

        if len(items) == 0:
            return "nothing"
        return ", ".join(f"{item.quantity} {item.item.name}" for item in items)

    @staticmethod
    def _winner_id(
        responses: dict[str, ConversationTurnResult],
        winner: ConversationTurnResult,
    ) -> str:
        """Return the villager id whose response object won the turn."""

        for villager_id, result in responses.items():
            if result is winner:
                return villager_id
        raise ValueError("Winner must come from the supplied response map.")

    def _villager_name(self, villager_id: str) -> str:
        """Return the authored villager name when canon is available."""

        canon = self._canon
        if canon is None:
            return villager_id
        return canon.get_villager(CanonVillagerId(villager_id)).name

    async def _resolve_maybe_awaitable(
        self,
        value: (
            Awaitable[ConversationTurnResult]
            | Awaitable[TradeTurnResult]
            | Awaitable[bool]
            | ConversationTurnResult
            | TradeTurnResult
            | bool
        ),
    ) -> ConversationTurnResult | TradeTurnResult | bool:
        """Await asynchronous dependency results while preserving sync call support."""

        if inspect.isawaitable(value):
            return await cast(
                Awaitable[ConversationTurnResult | TradeTurnResult | bool],
                value,
            )
        return cast(ConversationTurnResult | TradeTurnResult | bool, value)

    def _require_ai_coordinator(self) -> _AICoordinatorProtocol:
        """Return the configured AI coordinator or fail fast."""

        if self._ai_coordinator is None:
            raise RuntimeError("ConversationSystem requires ai_coordinator.")
        return self._ai_coordinator

    def _require_memory_system(self) -> _MemorySystemProtocol:
        """Return the configured memory system or fail fast."""

        if self._memory_system is None:
            raise RuntimeError("ConversationSystem requires memory_system.")
        return self._memory_system

    def _require_villager_states(self) -> dict[str, VillagerState]:
        """Return the configured villager-state map or fail fast."""

        if self._villager_states is None:
            raise RuntimeError("ConversationSystem requires villager_states.")
        return self._villager_states
