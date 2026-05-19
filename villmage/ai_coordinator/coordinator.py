# pyre-strict

"""Stateless orchestration layer over AI coordinator prompts and parsers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Awaitable, Callable, Protocol, TypeVar, cast

from action_system.types import ActionContext, ActionList, AutobalanceMultipliers
from character_canon.canon import CharacterCanon
from character_canon.types import VillagerCanon
from llm_client.types import CallType, LLMResponse
from llm_client.types import PromptSegment
from memory_system.memory import MemorySystem
from villmage.ai_coordinator import parser as parser_module
from villmage.ai_coordinator.parser import (
    ParseError,
    parse_action_selection,
    parse_conversation_turn,
    parse_join_decision,
    parse_relationship_update,
    parse_social_score,
    parse_trade_turn,
)
from villmage.ai_coordinator.prompts import (
    assemble_action_selection,
    assemble_conversation_turn,
    assemble_join_decision,
    assemble_relationship_update,
    assemble_social_score,
    assemble_trade_turn,
)
from villmage.ai_coordinator.types import (
    ActionSelectionResult,
    ConversationSnapshot,
    ConversationTurnResult,
    LLMCallType,
    ParseContext,
    PromptPackage,
    RelationshipRecord,
    RelationshipUpdateResult,
    TradeActionType,
    TradeSnapshot,
    TradeTurnResult,
)
from villmage.game_types import GameTime, ItemType, WorldContext
from villmage.villager_state import ComputedStats, VillagerState
from villmage.world_state import WorldState


T = TypeVar("T")


class _ActionSystemProtocol(Protocol):
    """Minimal action-system read surface required by the coordinator."""

    def get_valid_actions(self, ctx: ActionContext) -> ActionList:
        """Return the current valid action list for one villager."""


class _LLMClientProtocol(Protocol):
    """Minimal LLM client surface required by the coordinator."""

    def complete(
        self,
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> object:
        """Return a raw completion, optionally through an awaitable wrapper."""


def _inventory_items(villager_state: VillagerState) -> list[tuple[ItemType, int]]:
    """Return one villager inventory as a stable item-count list."""

    return sorted(villager_state.inventory.items(), key=lambda pair: pair[0].name)


def _other_villager_canons(
    canon: CharacterCanon,
    villager_id: str,
) -> list[VillagerCanon]:
    """Return all authored villager canons except the prompted villager."""

    return [
        villager_canon
        for villager_canon in canon.get_all_villagers()
        if villager_canon.id != villager_id
    ]


def _last_other_trade_action(
    snapshot: TradeSnapshot,
) -> TradeActionType | None:
    """Return the other villager's most recent trade action, if any."""

    for turn in reversed(snapshot.history):
        if turn.villager_id == snapshot.other_villager_id:
            return turn.action
    return None


class AICoordinator:
    """Assemble prompts, invoke the LLM, and retry once on parse failures."""

    _canon: CharacterCanon
    _villager_states: dict[str, VillagerState]
    _world_state: WorldState
    _action_system: _ActionSystemProtocol
    _memory_system: MemorySystem
    _llm_client: _LLMClientProtocol

    def __init__(
        self,
        canon: CharacterCanon,
        villager_states: dict[str, VillagerState],
        world_state: WorldState,
        action_system: _ActionSystemProtocol,
        memory_system: MemorySystem,
        llm_client: _LLMClientProtocol,
    ) -> None:
        """Store read-only references to the subsystems used for prompt assembly."""

        self._canon = canon
        self._villager_states = villager_states
        self._world_state = world_state
        self._action_system = action_system
        self._memory_system = memory_system
        self._llm_client = llm_client

    def _call(
        self,
        package: PromptPackage,
        parse_fn: Callable[[str, ParseContext], T],
        ctx: ParseContext,
    ) -> T:
        """Invoke the LLM, retry once on ParseError, and return the parsed value."""

        response = self._complete_text(package, ctx.call_type)
        try:
            return parse_fn(response, ctx)
        except ParseError:
            retry_response = self._complete_text(package, ctx.call_type)
            with parser_module.retry_logging(True):
                return parse_fn(retry_response, ctx)

    def _complete_text(
        self,
        package: PromptPackage,
        call_type: LLMCallType,
    ) -> str:
        """Run one LLM completion and normalize the result to raw response text."""

        completion = self._llm_client.complete(
            package.segments,
            self._llm_call_type(call_type),
        )
        resolved = self._resolve_completion(completion)
        if isinstance(resolved, LLMResponse):
            return resolved.text
        if isinstance(resolved, str):
            return resolved
        raise TypeError(f"Unsupported LLM completion result: {type(resolved)!r}.")

    def _resolve_completion(self, completion: object) -> object:
        """Await one completion result when the client returns a coroutine."""

        if inspect.isawaitable(completion):
            return asyncio.run(cast(Awaitable[object], completion))
        return completion

    @staticmethod
    def _llm_call_type(call_type: LLMCallType) -> CallType:
        """Map AI coordinator call types onto the LLM client's temperature buckets."""

        if call_type is LLMCallType.ACTION_SELECTION:
            return CallType.ACTION_SELECTION
        if call_type is LLMCallType.RELATIONSHIP_UPDATE:
            return CallType.RELATIONSHIP_UPDATE
        return CallType.CONVERSATION_TURN

    def _world_context(self, game_time: GameTime) -> WorldContext:
        """Build one shared world-context snapshot for villager stat computation."""

        return WorldContext(
            base_calories=self._world_state.get_total_edible_calories(),
            total_fuel_minutes=self._world_state.get_total_fuel_minutes(game_time),
            villager_count=len(self._villager_states),
            total_dirtiness=self._world_state.get_total_dirtiness(),
            current_game_time=game_time,
        )

    def _computed_stats(
        self,
        villager_id: str,
        game_time: GameTime,
    ) -> ComputedStats:
        """Compute current derived stats for one villager."""

        return self._villager_states[villager_id].compute_stats(
            self._world_context(game_time)
        )

    def select_action(
        self,
        villager_id: str,
        game_time: GameTime,
    ) -> ActionSelectionResult:
        """Return one validated action selection and optional thought."""

        villager_state = self._villager_states[villager_id]
        memory_context = self._memory_system.get_memory_context(villager_id)
        action_list = self._action_system.get_valid_actions(
            ActionContext(
                villager_id=villager_id,
                canon=self._canon,
                vs=villager_state,
                all_states=self._villager_states,
                ws=self._world_state,
                multipliers=AutobalanceMultipliers(),
            )
        )
        package = assemble_action_selection(
            own_canon=self._canon.get_villager(villager_id),
            other_canons=_other_villager_canons(self._canon, villager_id),
            memory_context=memory_context,
            base_summary=self._world_state.get_base_summary(game_time),
            computed_stats=self._computed_stats(villager_id, game_time),
            inventory_items=_inventory_items(villager_state),
            action_list=action_list,
            game_time=game_time,
        )
        ctx = ParseContext(
            villager_id=villager_id,
            call_type=LLMCallType.ACTION_SELECTION,
            game_time=game_time,
            prompt=package.segments,
        )
        return self._call(
            package,
            lambda response, parse_ctx: parse_action_selection(
                response,
                action_list,
                parse_ctx,
            ),
            ctx,
        )

    def get_conversation_turn(
        self,
        villager_id: str,
        snapshot: ConversationSnapshot,
        game_time: GameTime,
    ) -> ConversationTurnResult:
        """Return one validated conversation-turn decision for the villager."""

        villager_state = self._villager_states[villager_id]
        package = assemble_conversation_turn(
            own_canon=self._canon.get_villager(villager_id),
            other_canons=_other_villager_canons(self._canon, villager_id),
            memory_context=self._memory_system.get_memory_context(villager_id),
            computed_stats=self._computed_stats(villager_id, game_time),
            inventory_items=_inventory_items(villager_state),
            snapshot=snapshot,
            game_time=game_time,
        )
        ctx = ParseContext(
            villager_id=villager_id,
            call_type=LLMCallType.CONVERSATION_TURN,
            game_time=game_time,
            prompt=package.segments,
        )
        return self._call(package, parse_conversation_turn, ctx)

    def get_trade_turn(
        self,
        villager_id: str,
        snapshot: TradeSnapshot,
        game_time: GameTime,
    ) -> TradeTurnResult:
        """Return one validated trade-turn decision for the villager."""

        villager_state = self._villager_states[villager_id]
        inventory_items = _inventory_items(villager_state)
        package = assemble_trade_turn(
            own_canon=self._canon.get_villager(villager_id),
            inventory_items=inventory_items,
            snapshot=snapshot,
        )
        ctx = ParseContext(
            villager_id=villager_id,
            call_type=LLMCallType.TRADE_TURN,
            game_time=game_time,
            prompt=package.segments,
        )
        last_other_action = _last_other_trade_action(snapshot)
        return self._call(
            package,
            lambda response, parse_ctx: parse_trade_turn(
                response,
                inventory_items,
                last_other_action,
                parse_ctx,
            ),
            ctx,
        )

    def get_join_decision(
        self,
        villager_id: str,
        current_action_description: str,
        snapshot: ConversationSnapshot,
        game_time: GameTime,
    ) -> bool:
        """Return whether the villager chooses to join the provided conversation."""

        package = assemble_join_decision(
            own_canon=self._canon.get_villager(villager_id),
            current_action_description=current_action_description,
            snapshot=snapshot,
        )
        ctx = ParseContext(
            villager_id=villager_id,
            call_type=LLMCallType.JOIN_DECISION,
            game_time=game_time,
            prompt=package.segments,
        )
        return self._call(package, parse_join_decision, ctx)

    def get_social_score(
        self,
        villager_id: str,
        snapshot: ConversationSnapshot,
        game_time: GameTime,
    ) -> int:
        """Return the villager's 0-10 social satisfaction score."""

        package = assemble_social_score(
            own_canon=self._canon.get_villager(villager_id),
            snapshot=snapshot,
        )
        ctx = ParseContext(
            villager_id=villager_id,
            call_type=LLMCallType.SOCIAL_SCORE,
            game_time=game_time,
            prompt=package.segments,
        )
        return self._call(package, parse_social_score, ctx)

    def get_relationship_update(
        self,
        speaker_id: str,
        subject_id: str,
        snapshot: ConversationSnapshot,
        game_time: GameTime,
    ) -> RelationshipUpdateResult:
        """Return the speaker's updated directional impression of the subject."""

        memory_record = self._memory_system.get_relationship_record(
            speaker_id,
            subject_id,
        )
        package = assemble_relationship_update(
            speaker_canon=self._canon.get_villager(speaker_id),
            subject_canon=self._canon.get_villager(subject_id),
            relationship=RelationshipRecord(
                description=memory_record.description,
                impressions=list(memory_record.recent_impressions),
            ),
            snapshot=snapshot,
        )
        ctx = ParseContext(
            villager_id=speaker_id,
            call_type=LLMCallType.RELATIONSHIP_UPDATE,
            game_time=game_time,
            prompt=package.segments,
        )
        return self._call(package, parse_relationship_update, ctx)
