# pyre-strict

"""Pure data types for the AI coordinator boundary."""

from dataclasses import dataclass
from enum import IntEnum

from action_system.types import SelectedAction
from llm_client.types import PromptSegment
from villmage.game_types import GameTime, ItemType


class LLMCallType(IntEnum):
    """Diagnostic classifier for one AI coordinator LLM call."""

    ACTION_SELECTION = 1
    CONVERSATION_TURN = 2
    JOIN_DECISION = 3
    SOCIAL_SCORE = 4
    RELATIONSHIP_UPDATE = 5
    TRADE_TURN = 6


class ConvActionType(IntEnum):
    """Conversation actions available on one villager turn."""

    LEAVE = 1
    SILENT = 2
    INTERACT = 3
    INTERRUPT = 4
    CONTINUE = 5
    RESPOND = 6
    CHANGE_TOPIC = 7
    CASUAL = 8
    TRADE = 9


class TradeActionType(IntEnum):
    """Trade sub-protocol actions available on one villager turn."""

    MAKE_OFFER = 1
    REQUEST_ITEMS = 2
    CANCEL = 3
    ACCEPT = 4


@dataclass(frozen=True)
class ConversationTurn:
    """One recorded conversation turn with self-contained rendered text."""

    villager_id: str
    text: str


@dataclass(frozen=True)
class ConversationSnapshot:
    """Visibility-filtered conversation context supplied by the caller."""

    participant_ids: list[str]
    history: list[ConversationTurn]
    elapsed_game_minutes: int


@dataclass(frozen=True)
class ConversationTurnResult:
    """Validated output of one conversation-turn LLM call."""

    action: ConvActionType
    resp: str | None = None
    target_id: str | None = None


@dataclass(frozen=True)
class TradeItemSpec:
    """One resolved item-quantity pair in a trade payload."""

    item: ItemType
    quantity: int


@dataclass(frozen=True)
class TradeTurnRecord:
    """One resolved trade-history turn stored in a trade snapshot."""

    villager_id: str
    action: TradeActionType
    items: list[TradeItemSpec]
    speech: str | None = None


@dataclass(frozen=True)
class TradeSnapshot:
    """Full trade negotiation context for one prompted villager."""

    other_villager_id: str
    history: list[TradeTurnRecord]
    turn_count: int


@dataclass(frozen=True)
class TradeTurnResult:
    """Validated output of one trade-turn LLM call."""

    action: TradeActionType
    items: list[TradeItemSpec]
    speech: str | None = None


@dataclass(frozen=True)
class ActionSelectionResult:
    """Validated selected action plus an optional logged thought."""

    action: SelectedAction
    thought: str | None = None


@dataclass(frozen=True)
class RelationshipUpdateResult:
    """Validated relationship-update output for one ordered villager pair."""

    impression: str
    desc_update: str | None = None


@dataclass(frozen=True)
class RelationshipRecord:
    """Current relationship description plus recent impressions for one pair."""

    description: str
    impressions: list[str]


@dataclass(frozen=True)
class PromptPackage:
    """Assembled prompt segments and cache breakpoint indices."""

    segments: list[PromptSegment]
    breakpoints: list[int]


@dataclass(frozen=True)
class ParseContext:
    """Context bundle required to log one parse failure completely."""

    villager_id: str
    call_type: LLMCallType
    game_time: GameTime
    prompt: list[PromptSegment]


@dataclass(frozen=True)
class ParseFailureLog:
    """Append-only diagnostic record for one failed parse attempt."""

    villager_id: str
    call_type: LLMCallType
    game_time: int
    prompt: list[PromptSegment]
    raw_response: str
    parse_error: str
    is_retry: bool
