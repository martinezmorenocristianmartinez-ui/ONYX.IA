"""
models/interfaces.py — Abstract interfaces for LLM providers.

All model providers (Ollama, Gemini, OpenRouter, etc.) implement
``ModelProvider`` so that the Brain can reason with any backend
without knowing the implementation details.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Iterator


class ModelCapability(Enum):
    """Capabilities a provider may support."""

    TEXT_GENERATION = auto()
    TOOL_CALLING = auto()
    STREAMING = auto()
    VISION = auto()
    AUDIO = auto()
    EMBEDDINGS = auto()


@dataclass
class ModelResult:
    """Result of a single ``reason()`` call."""

    text: str
    source: str  # "ollama" | "gemini" | "openrouter" | "none"
    error: str | None = None
    duration_ms: float = 0.0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.error is None


class ModelProvider(ABC):
    """Abstract interface for an LLM provider.

    Each provider wraps a specific backend (Ollama, Gemini, …)
    and exposes a uniform ``reason()`` method.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. ``"ollama"``)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the backend is reachable right now."""

    @abstractmethod
    def capabilities(self) -> set[ModelCapability]:
        """Return the set of capabilities this provider supports."""

    @abstractmethod
    def reason(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResult:
        """Send a prompt and return the model response.

        Args:
            prompt: The user message or query.
            system: Optional system instruction.
            tools: Optional list of tool declarations (OpenAI/function-calling format).

        Returns:
            A ``ModelResult`` with text, optional tool_calls, and timing info.
        """

    @abstractmethod
    def stream(
        self,
        prompt: str,
        system: str | None = None,
    ) -> Iterator[str]:
        """Yield tokens one by one for streaming use cases."""
