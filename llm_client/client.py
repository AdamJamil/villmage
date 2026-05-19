# pyre-strict

"""Runtime client helpers for assembling Gemini prompt content."""

from dataclasses import dataclass
import logging
import time
from typing import Final, Protocol, cast

from llm_client.types import LLMConfig, MessageRole, PromptSegment

try:
    import google.generativeai as _google_generativeai
except ImportError:
    _google_generativeai = None

try:
    from google.ai.generativelanguage import GenerateContentRequest
except ImportError:
    @dataclass(frozen=True)
    class GenerateContentRequest:
        """Fallback request stub used when Gemini request types are unavailable."""

        payload: object | None = None


_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True)
class Part:
    """A single text part in Gemini content."""

    text: str


@dataclass(frozen=True)
class Content:
    """One Gemini conversation turn with a role and text parts."""

    role: str
    parts: list[Part]


@dataclass(frozen=True)
class _FallbackGenerativeModel:
    """Minimal stand-in used when the Gemini SDK is unavailable."""

    model_name: str
    api_key: str

    def generate_content(
        self,
        request: GenerateContentRequest,
        *,
        generation_config: object | None = None,
    ) -> object:
        """Raise because request submission requires the real Gemini SDK."""

        del request, generation_config
        raise RuntimeError("google.generativeai is not installed")


class _GenerativeModelProtocol(Protocol):
    """Subset of the Gemini model surface used by LLMClient."""

    def generate_content(
        self,
        request: GenerateContentRequest,
        *,
        generation_config: object | None = None,
    ) -> object:
        """Submit one request and return the SDK response."""


def _create_generative_model(
    model_name: str,
    api_key: str,
) -> _GenerativeModelProtocol:
    """Create a Gemini GenerativeModel or a local fallback stub."""

    if _google_generativeai is None:
        return _FallbackGenerativeModel(model_name=model_name, api_key=api_key)

    _google_generativeai.configure(api_key=api_key)
    return cast(
        _GenerativeModelProtocol,
        _google_generativeai.GenerativeModel(model_name=model_name),
    )


def _status_code_from_error(error: BaseException) -> int | None:
    """Extract an HTTP status code from a Gemini or transport exception."""

    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    return None


def _is_transient_network_error(error: BaseException) -> bool:
    """Return whether the error looks like a transient transport failure."""

    return isinstance(error, (ConnectionError, TimeoutError))


def _is_retryable_error(error: BaseException) -> bool:
    """Return whether the error should be retried."""

    if _is_transient_network_error(error):
        return True

    status_code = _status_code_from_error(error)
    if status_code is None:
        return False

    return status_code == 429 or 500 <= status_code <= 599


def _is_immediate_error(error: BaseException) -> bool:
    """Return whether the error should be raised without retry."""

    status_code = _status_code_from_error(error)
    return status_code in {400, 403}


def _backoff_seconds(attempt_number: int) -> float:
    """Compute the capped exponential backoff for a failed attempt."""

    return min(float(2 ** (attempt_number - 1)), 60.0)


def _error_indicator(error: BaseException) -> str:
    """Build a compact log label for the failure kind."""

    status_code = _status_code_from_error(error)
    if status_code is None:
        return type(error).__name__
    return f"{type(error).__name__}(status={status_code})"


def _log_failed_attempt(error: BaseException, attempt_number: int, wait: float) -> None:
    """Log one failed submission attempt."""

    _LOGGER.warning(
        "LLM request failed on attempt %d with %s; wait=%.1fs",
        attempt_number,
        _error_indicator(error),
        wait,
    )


class LLMClient:
    """Thin prompt-shaping wrapper around one Gemini model instance."""

    _ROLE_NAMES: Final[dict[MessageRole, str]] = {
        MessageRole.USER: "user",
        MessageRole.MODEL: "model",
    }

    def __init__(self, config: LLMConfig, api_key: str) -> None:
        """Create one shared GenerativeModel for the configured model name."""

        self._config = config
        self._model = _create_generative_model(
            model_name=config.model,
            api_key=api_key,
        )

    def _build_contents(
        self,
        segments: list[PromptSegment],
    ) -> tuple[str, list[Content]]:
        """Split SYSTEM text out and preserve USER/MODEL turns in order."""

        system_segments: list[str] = []
        contents: list[Content] = []

        for segment in segments:
            if segment.role is MessageRole.SYSTEM:
                system_segments.append(segment.text)
                continue

            contents.append(
                Content(
                    role=self._ROLE_NAMES[segment.role],
                    parts=[Part(text=segment.text)],
                )
            )

        return ("".join(system_segments), contents)

    def _submit_with_retry(
        self,
        request: GenerateContentRequest,
        temperature: float,
    ) -> object:
        """Submit a request and retry transient failures with capped backoff."""

        generation_config: dict[str, float] = {"temperature": temperature}

        for attempt_number in range(1, self._config.max_retries + 2):
            try:
                return self._model.generate_content(
                    request,
                    generation_config=generation_config,
                )
            except BaseException as error:
                if _is_immediate_error(error):
                    _log_failed_attempt(error, attempt_number, 0.0)
                    raise

                if not _is_retryable_error(error):
                    _log_failed_attempt(error, attempt_number, 0.0)
                    raise

                if attempt_number > self._config.max_retries:
                    _log_failed_attempt(error, attempt_number, 0.0)
                    raise

                wait_seconds = _backoff_seconds(attempt_number)
                _log_failed_attempt(error, attempt_number, wait_seconds)
                time.sleep(wait_seconds)
