# pyre-strict

"""Runtime client helpers for assembling Gemini prompt content."""

from dataclasses import dataclass
from typing import Final

from llm_client.types import LLMConfig, MessageRole, PromptSegment

try:
    import google.generativeai as _google_generativeai
except ImportError:
    _google_generativeai = None


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


def _create_generative_model(model_name: str, api_key: str) -> object:
    """Create a Gemini GenerativeModel or a local fallback stub."""

    if _google_generativeai is None:
        return _FallbackGenerativeModel(model_name=model_name, api_key=api_key)

    _google_generativeai.configure(api_key=api_key)
    return _google_generativeai.GenerativeModel(model_name=model_name)


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
