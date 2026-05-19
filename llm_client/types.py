# pyre-strict

"""Pure data types for the LLM client subsystem."""

from dataclasses import dataclass
from enum import IntEnum


class MessageRole(IntEnum):
    """Role of a prompt segment in an LLM request."""

    SYSTEM = 1
    USER = 2
    MODEL = 3


class CallType(IntEnum):
    """Purpose of an LLM call."""

    ACTION_SELECTION = 1
    CONVERSATION_TURN = 2
    MEMORY_COMPACTION = 3
    RELATIONSHIP_UPDATE = 4


@dataclass(frozen=True)
class PromptSegment:
    """One ordered segment of an LLM prompt."""

    role: MessageRole
    text: str


@dataclass(frozen=True)
class LLMResponse:
    """Raw text completion and token counts returned by the LLM."""

    text: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMConfig:
    """Construction-time configuration for the LLM client."""

    model: str = "gemini-2.5-flash"
    max_output_tokens: int = 2048
    max_retries: int = 10
