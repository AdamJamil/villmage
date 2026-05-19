# pyre-strict

"""Tests for pure LLM client data types."""

from dataclasses import FrozenInstanceError

import pytest

from llm_client.types import CallType, LLMConfig, LLMResponse, MessageRole, PromptSegment


def test_message_role_values_match_spec() -> None:
    """MessageRole values match the thrift spec exactly."""

    assert MessageRole.SYSTEM.value == 1
    assert MessageRole.USER.value == 2
    assert MessageRole.MODEL.value == 3


def test_call_type_values_match_spec() -> None:
    """CallType values match the thrift spec exactly."""

    assert CallType.ACTION_SELECTION.value == 1
    assert CallType.CONVERSATION_TURN.value == 2
    assert CallType.MEMORY_COMPACTION.value == 3
    assert CallType.RELATIONSHIP_UPDATE.value == 4


def test_prompt_segment_construction() -> None:
    """PromptSegment stores all supplied fields."""

    segment = PromptSegment(role=MessageRole.USER, text="hello")

    assert segment.role is MessageRole.USER
    assert segment.text == "hello"


def test_llm_response_construction() -> None:
    """LLMResponse stores all supplied fields."""

    response = LLMResponse(text="result", input_tokens=123, output_tokens=45)

    assert response.text == "result"
    assert response.input_tokens == 123
    assert response.output_tokens == 45


def test_llm_config_defaults_match_spec() -> None:
    """LLMConfig default values match the spec exactly."""

    config = LLMConfig()

    assert config.model == "gemini-2.5-flash"
    assert config.max_output_tokens == 2048
    assert config.max_retries == 10


def test_llm_config_overrides() -> None:
    """LLMConfig accepts overrides for all fields."""

    config = LLMConfig(
        model="gemini-2.5-pro",
        max_output_tokens=4096,
        max_retries=3,
    )

    assert config.model == "gemini-2.5-pro"
    assert config.max_output_tokens == 4096
    assert config.max_retries == 3


def test_prompt_segment_is_frozen() -> None:
    """PromptSegment rejects field reassignment."""

    segment = PromptSegment(role=MessageRole.SYSTEM, text="system")

    with pytest.raises(FrozenInstanceError):
        segment.text = "mutated"


def test_llm_response_is_frozen() -> None:
    """LLMResponse rejects field reassignment."""

    response = LLMResponse(text="raw", input_tokens=1, output_tokens=2)

    with pytest.raises(FrozenInstanceError):
        response.text = "mutated"


def test_llm_config_is_frozen() -> None:
    """LLMConfig rejects field reassignment."""

    config = LLMConfig()

    with pytest.raises(FrozenInstanceError):
        config.max_retries = 0
