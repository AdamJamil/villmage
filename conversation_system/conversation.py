# pyre-strict

"""Conversation-system orchestration entry points and pure helpers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Awaitable, Protocol, cast

from character_canon.types import VillagerCanon, VillagerId as CanonVillagerId
from conversation_system.types import ConversationSession
from memory_system.types import EventLogEntry, EventType, VillagerId as MemoryVillagerId
from villmage.ai_coordinator.types import (
    ConvActionType,
    ConversationSnapshot,
    ConversationTurn,
    ConversationTurnResult,
)


class _AICoordinatorProtocol(Protocol):
    """Minimal AI coordinator surface required by ConversationSystem."""

    def get_conversation_turn(
        self,
        villager_id: str,
        snapshot: ConversationSnapshot,
        game_time: int,
    ) -> ConversationTurnResult | Awaitable[ConversationTurnResult]:
        """Return one villager's conversation-turn decision."""


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

    def __init__(
        self,
        ai_coordinator: _AICoordinatorProtocol | None = None,
        memory_system: _MemorySystemProtocol | None = None,
        canon: _CharacterCanonProtocol | None = None,
    ) -> None:
        """Store the conversation-system dependencies used during orchestration."""

        self._ai_coordinator = ai_coordinator
        self._memory_system = memory_system
        self._canon = canon

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
        if inspect.isawaitable(result_object):
            result = await cast(Awaitable[ConversationTurnResult], result_object)
        else:
            result = cast(ConversationTurnResult, result_object)
        return (villager_id, result)

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
