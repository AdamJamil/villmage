# pyre-strict

"""Tests for LLM client content assembly."""

import asyncio
from dataclasses import dataclass
import logging
from typing import Awaitable, TypeVar

import pytest

import llm_client.client as client_module
from llm_client.client import LLMClient
from llm_client.types import CallType, LLMConfig, MessageRole, PromptSegment


_T = TypeVar("_T")


def _texts(contents: list[client_module.Content]) -> list[str]:
    """Extract the single text payload from each content item."""

    return [content.parts[0].text for content in contents]


class _FakeHTTPError(Exception):
    """HTTP-style exception with a status code."""

    def __init__(self, status_code: int) -> None:
        """Store the failing HTTP status code."""

        super().__init__(f"status={status_code}")
        self.status_code = status_code


@dataclass(frozen=True)
class _FakeUsageMetadata:
    """Usage metadata stub returned by the mocked Gemini SDK."""

    input_token_count: int
    output_token_count: int


@dataclass(frozen=True)
class _FakeGenerateContentResponse:
    """GenerateContentResponse stub used by complete() tests."""

    text: str
    usage_metadata: _FakeUsageMetadata


class _FakeModel:
    """Scriptable model stub for retry tests."""

    def __init__(self, outcomes: list[object]) -> None:
        """Store scripted results or exceptions."""

        self._outcomes = outcomes
        self.call_count = 0
        self.generation_configs: list[object | None] = []
        self.requests: list[client_module.GenerateContentRequest] = []

    def generate_content(
        self,
        request: client_module.GenerateContentRequest,
        *,
        generation_config: object | None = None,
    ) -> object:
        """Return the next scripted result or raise the next scripted error."""

        self.call_count += 1
        self.requests.append(request)
        self.generation_configs.append(generation_config)
        outcome = self._outcomes[self.call_count - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _make_client(fake_model: _FakeModel, max_retries: int = 10) -> LLMClient:
    """Construct an LLMClient whose SDK model is fully mocked."""

    captured: list[tuple[str, str]] = []

    def fake_create_generative_model(model_name: str, api_key: str) -> object:
        """Record constructor inputs and return the supplied fake model."""

        captured.append((model_name, api_key))
        return fake_model

    original = client_module._create_generative_model
    client_module._create_generative_model = fake_create_generative_model
    try:
        client = LLMClient(
            config=LLMConfig(model="gemini-test", max_retries=max_retries),
            api_key="secret-key",
        )
    finally:
        client_module._create_generative_model = original

    assert captured == [("gemini-test", "secret-key")]
    return client


def _run_async(coroutine: Awaitable[_T]) -> _T:
    """Run one async call in tests without requiring pytest-trio."""

    return asyncio.run(coroutine)


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


def test_submit_with_retry_recovers_from_transient_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two 429 responses are retried before a later success returns."""

    fake_model = _FakeModel(
        [
            _FakeHTTPError(429),
            _FakeHTTPError(429),
            "success",
        ]
    )
    client = _make_client(fake_model)
    waits: list[float] = []

    def fake_sleep(duration: float) -> None:
        """Record each backoff duration instead of sleeping."""

        waits.append(duration)

    monkeypatch.setattr(client_module.time, "sleep", fake_sleep)

    response = client._submit_with_retry(
        client_module.GenerateContentRequest(),
        temperature=0.7,
    )

    assert response == "success"
    assert fake_model.call_count == 3
    assert waits == [1.0, 2.0]
    assert fake_model.generation_configs == [
        {"temperature": 0.7},
        {"temperature": 0.7},
        {"temperature": 0.7},
    ]


def test_submit_with_retry_raises_immediately_on_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 400 is not retried and propagates immediately."""

    fake_model = _FakeModel([_FakeHTTPError(400)])
    client = _make_client(fake_model)
    waits: list[float] = []

    def fake_sleep(duration: float) -> None:
        """Fail the test if backoff is used for a 400."""

        waits.append(duration)

    monkeypatch.setattr(client_module.time, "sleep", fake_sleep)

    with pytest.raises(_FakeHTTPError):
        client._submit_with_retry(
            client_module.GenerateContentRequest(),
            temperature=0.2,
        )

    assert fake_model.call_count == 1
    assert waits == []


def test_submit_with_retry_raises_immediately_on_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 403 is not retried and propagates immediately."""

    fake_model = _FakeModel([_FakeHTTPError(403)])
    client = _make_client(fake_model)
    waits: list[float] = []

    def fake_sleep(duration: float) -> None:
        """Fail the test if backoff is used for a 403."""

        waits.append(duration)

    monkeypatch.setattr(client_module.time, "sleep", fake_sleep)

    with pytest.raises(_FakeHTTPError):
        client._submit_with_retry(
            client_module.GenerateContentRequest(),
            temperature=0.2,
        )

    assert fake_model.call_count == 1
    assert waits == []


def test_submit_with_retry_raises_after_max_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent 500 failures stop after the configured retry budget."""

    fake_model = _FakeModel([_FakeHTTPError(500)] * 4)
    client = _make_client(fake_model, max_retries=3)
    waits: list[float] = []

    def fake_sleep(duration: float) -> None:
        """Record retry backoff durations."""

        waits.append(duration)

    monkeypatch.setattr(client_module.time, "sleep", fake_sleep)

    with pytest.raises(_FakeHTTPError):
        client._submit_with_retry(
            client_module.GenerateContentRequest(),
            temperature=1.0,
        )

    assert fake_model.call_count == 4
    assert waits == [1.0, 2.0, 4.0]


def test_submit_with_retry_uses_capped_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backoff doubles each retry attempt and stops growing past 60 seconds."""

    outcomes: list[object] = [_FakeHTTPError(500)] * 7
    outcomes.append("success")
    fake_model = _FakeModel(outcomes)
    client = _make_client(fake_model, max_retries=7)
    waits: list[float] = []

    def fake_sleep(duration: float) -> None:
        """Record retry backoff durations."""

        waits.append(duration)

    monkeypatch.setattr(client_module.time, "sleep", fake_sleep)

    response = client._submit_with_retry(
        client_module.GenerateContentRequest(),
        temperature=0.4,
    )

    assert response == "success"
    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]


def test_submit_with_retry_retries_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport failures are retried like 5xx responses."""

    fake_model = _FakeModel([TimeoutError("timeout"), "success"])
    client = _make_client(fake_model, max_retries=2)
    waits: list[float] = []

    def fake_sleep(duration: float) -> None:
        """Record retry backoff durations."""

        waits.append(duration)

    monkeypatch.setattr(client_module.time, "sleep", fake_sleep)

    response = client._submit_with_retry(
        client_module.GenerateContentRequest(),
        temperature=1.0,
    )

    assert response == "success"
    assert fake_model.call_count == 2
    assert waits == [1.0]


def test_submit_with_retry_logs_each_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each transient failure log includes attempt number, error, and wait."""

    fake_model = _FakeModel([_FakeHTTPError(429), _FakeHTTPError(500), "success"])
    client = _make_client(fake_model)

    def fake_sleep(duration: float) -> None:
        """Skip real sleeps during retry logging tests."""

        del duration

    monkeypatch.setattr(client_module.time, "sleep", fake_sleep)
    caplog.set_level(logging.WARNING, logger=client_module.__name__)

    response = client._submit_with_retry(
        client_module.GenerateContentRequest(),
        temperature=0.7,
    )

    assert response == "success"
    assert len(caplog.records) == 2
    first_message = caplog.records[0].getMessage()
    second_message = caplog.records[1].getMessage()
    assert "attempt 1" in first_message
    assert "429" in first_message or "_FakeHTTPError" in first_message
    assert "wait=1.0s" in first_message
    assert "attempt 2" in second_message
    assert "500" in second_message or "_FakeHTTPError" in second_message
    assert "wait=2.0s" in second_message


@pytest.mark.parametrize(
    ("call_type", "expected_temperature"),
    [
        (CallType.ACTION_SELECTION, 0.7),
        (CallType.CONVERSATION_TURN, 1.0),
        (CallType.MEMORY_COMPACTION, 0.2),
        (CallType.RELATIONSHIP_UPDATE, 0.4),
    ],
)
def test_complete_uses_expected_temperature(
    monkeypatch: pytest.MonkeyPatch,
    call_type: CallType,
    expected_temperature: float,
) -> None:
    """complete() selects the correct temperature for each call type."""

    client = LLMClient(config=LLMConfig(model="gemini-test"), api_key="test")
    captured_temperatures: list[float] = []

    def fake_submit_with_retry(
        request: client_module.GenerateContentRequest,
        temperature: float,
    ) -> object:
        """Record the selected temperature and return a fake SDK response."""

        del request
        captured_temperatures.append(temperature)
        return _FakeGenerateContentResponse(
            text="ok",
            usage_metadata=_FakeUsageMetadata(
                input_token_count=1,
                output_token_count=2,
            ),
        )

    monkeypatch.setattr(client, "_submit_with_retry", fake_submit_with_retry)

    response = _run_async(
        client.complete(
            [PromptSegment(role=MessageRole.USER, text="hello")],
            call_type,
        )
    )

    assert response.text == "ok"
    assert captured_temperatures == [expected_temperature]


def test_complete_returns_raw_text_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    """complete() preserves Gemini response text exactly as returned."""

    client = LLMClient(config=LLMConfig(model="gemini-test"), api_key="test")
    raw_text = "  padded text\n"

    def fake_submit_with_retry(
        request: client_module.GenerateContentRequest,
        temperature: float,
    ) -> object:
        """Return a response with intentionally unnormalized whitespace."""

        del request, temperature
        return _FakeGenerateContentResponse(
            text=raw_text,
            usage_metadata=_FakeUsageMetadata(
                input_token_count=11,
                output_token_count=7,
            ),
        )

    monkeypatch.setattr(client, "_submit_with_retry", fake_submit_with_retry)

    response = _run_async(
        client.complete(
            [PromptSegment(role=MessageRole.USER, text="hello")],
            CallType.CONVERSATION_TURN,
        )
    )

    assert response.text == raw_text


def test_complete_returns_usage_token_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """complete() forwards Gemini usage metadata without modification."""

    client = LLMClient(config=LLMConfig(model="gemini-test"), api_key="test")

    def fake_submit_with_retry(
        request: client_module.GenerateContentRequest,
        temperature: float,
    ) -> object:
        """Return a response with known usage metadata values."""

        del request, temperature
        return _FakeGenerateContentResponse(
            text="tokens",
            usage_metadata=_FakeUsageMetadata(
                input_token_count=123,
                output_token_count=45,
            ),
        )

    monkeypatch.setattr(client, "_submit_with_retry", fake_submit_with_retry)

    response = _run_async(
        client.complete(
            [PromptSegment(role=MessageRole.USER, text="hello")],
            CallType.MEMORY_COMPACTION,
        )
    )

    assert response.input_tokens == 123
    assert response.output_tokens == 45


def test_complete_async_smoke() -> None:
    """complete() composes request assembly, submission, and unwrapping."""

    fake_model = _FakeModel(
        [
            _FakeGenerateContentResponse(
                text="final text",
                usage_metadata=_FakeUsageMetadata(
                    input_token_count=321,
                    output_token_count=54,
                ),
            )
        ]
    )
    client = _make_client(fake_model)

    response = _run_async(
        client.complete(
            [
                PromptSegment(role=MessageRole.SYSTEM, text="system one "),
                PromptSegment(role=MessageRole.SYSTEM, text="system two"),
                PromptSegment(role=MessageRole.USER, text="first user"),
                PromptSegment(role=MessageRole.MODEL, text="first model"),
                PromptSegment(role=MessageRole.USER, text="final user"),
            ],
            CallType.ACTION_SELECTION,
        )
    )

    assert response.text == "final text"
    assert response.input_tokens == 321
    assert response.output_tokens == 54
    assert fake_model.call_count == 1
    assert fake_model.generation_configs == [{"temperature": 0.7}]
    assert len(fake_model.requests) == 1
    request = fake_model.requests[0]
    assert request.model == "gemini-test"
    assert request.system_instruction == "system one system two"
    assert request.contents is not None
    assert [content.role for content in request.contents] == ["user", "model", "user"]
    assert _texts(request.contents) == ["first user", "first model", "final user"]
