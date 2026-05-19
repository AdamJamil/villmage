# pyre-strict

"""Tests for LLM client content assembly."""

import llm_client.client as client_module
from llm_client.client import LLMClient
from llm_client.types import LLMConfig, MessageRole, PromptSegment


def _texts(contents: list[client_module.Content]) -> list[str]:
    """Extract the single text payload from each content item."""

    return [content.parts[0].text for content in contents]


def test_init_constructs_one_model_with_configured_name() -> None:
    """LLMClient creates one GenerativeModel using the provided config."""

    captured: list[tuple[str, str]] = []

    def fake_create_generative_model(model_name: str, api_key: str) -> object:
        """Record constructor arguments and return a sentinel model."""

        captured.append((model_name, api_key))
        return object()

    original = client_module._create_generative_model
    client_module._create_generative_model = fake_create_generative_model
    try:
        LLMClient(config=LLMConfig(model="gemini-test"), api_key="secret-key")
    finally:
        client_module._create_generative_model = original

    assert captured == [("gemini-test", "secret-key")]


def test_build_contents_extracts_and_concatenates_system_segments() -> None:
    """SYSTEM segments join into one instruction and stay out of contents."""

    client = LLMClient(config=LLMConfig(), api_key="test")

    system_instruction, contents = client._build_contents(
        [
            PromptSegment(role=MessageRole.SYSTEM, text="First system. "),
            PromptSegment(role=MessageRole.USER, text="Hello"),
            PromptSegment(role=MessageRole.SYSTEM, text="Second system."),
            PromptSegment(role=MessageRole.MODEL, text="Hi there"),
        ]
    )

    assert system_instruction == "First system. Second system."
    assert [content.role for content in contents] == ["user", "model"]
    assert _texts(contents) == ["Hello", "Hi there"]


def test_build_contents_preserves_user_model_order() -> None:
    """USER and MODEL segments map to Gemini roles without reordering."""

    client = LLMClient(config=LLMConfig(), api_key="test")

    system_instruction, contents = client._build_contents(
        [
            PromptSegment(role=MessageRole.USER, text="u1"),
            PromptSegment(role=MessageRole.MODEL, text="m1"),
            PromptSegment(role=MessageRole.USER, text="u2"),
            PromptSegment(role=MessageRole.MODEL, text="m2"),
        ]
    )

    assert system_instruction == ""
    assert [content.role for content in contents] == [
        "user",
        "model",
        "user",
        "model",
    ]
    assert _texts(contents) == ["u1", "m1", "u2", "m2"]


def test_build_contents_handles_mixed_realistic_prompt() -> None:
    """A real prompt shape keeps both SYSTEM pieces and three turns."""

    client = LLMClient(config=LLMConfig(), api_key="test")

    system_instruction, contents = client._build_contents(
        [
            PromptSegment(role=MessageRole.SYSTEM, text="Static prompt.\n"),
            PromptSegment(role=MessageRole.SYSTEM, text="Backstory.\n"),
            PromptSegment(role=MessageRole.USER, text="User turn one"),
            PromptSegment(role=MessageRole.MODEL, text="Model turn one"),
            PromptSegment(role=MessageRole.USER, text="Final user turn"),
        ]
    )

    assert system_instruction == "Static prompt.\nBackstory.\n"
    assert [content.role for content in contents] == ["user", "model", "user"]
    assert _texts(contents) == [
        "User turn one",
        "Model turn one",
        "Final user turn",
    ]


def test_build_contents_without_system_segments() -> None:
    """No SYSTEM segments yields an empty instruction string."""

    client = LLMClient(config=LLMConfig(), api_key="test")

    system_instruction, contents = client._build_contents(
        [
            PromptSegment(role=MessageRole.USER, text="Question"),
            PromptSegment(role=MessageRole.MODEL, text="Answer"),
        ]
    )

    assert system_instruction == ""
    assert [content.role for content in contents] == ["user", "model"]
    assert _texts(contents) == ["Question", "Answer"]


def test_build_contents_single_user_segment() -> None:
    """A one-segment prompt still produces one content item."""

    client = LLMClient(config=LLMConfig(), api_key="test")

    system_instruction, contents = client._build_contents(
        [PromptSegment(role=MessageRole.USER, text="Only message")]
    )

    assert system_instruction == ""
    assert [content.role for content in contents] == ["user"]
    assert _texts(contents) == ["Only message"]
