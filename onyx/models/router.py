"""
models/router.py — Priority-based model routing with automatic fallback.

Registers multiple ``ModelProvider`` instances and selects the best
available one for each request. Lower priority numbers are tried first.

Default providers (registered by ``ModelRouter.default()``):
  1. Ollama  (priority 10) — local, fast, no API key needed.
  2. Gemini  (priority 20) — cloud fallback for complex tasks.
"""

from __future__ import annotations

import logging
from typing import Any

from onyx.models.interfaces import ModelCapability, ModelProvider, ModelResult
from onyx.models.providers import GeminiProvider, OllamaProvider

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes reasoning requests to the best available provider.

    Providers are tried in priority order. The first one that returns
    a successful result wins. If all providers fail, the last error is
    returned.
    """

    def __init__(self) -> None:
        self._providers: list[tuple[int, ModelProvider]] = []

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, provider: ModelProvider, priority: int = 100) -> None:
        """Add a provider at the given *priority* (lower = tried first)."""
        self._providers.append((priority, provider))
        self._providers.sort(key=lambda x: x[0])

    def unregister(self, name: str) -> None:
        """Remove all providers with the given *name*."""
        self._providers = [(p, prov) for p, prov in self._providers if prov.name != name]

    # ── Routing ───────────────────────────────────────────────────────────

    def route(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        required_capability: ModelCapability | None = None,
    ) -> ModelResult:
        """Try each registered provider and return the first successful result.

        Args:
            prompt: The user message or query.
            system: Optional system instruction.
            tools: Optional tool declarations for function calling.
            required_capability: If set, only providers with this capability
                                  are eligible.

        Returns:
            A ``ModelResult``. Check ``result.ok`` to see if it succeeded.
        """
        last_error: str | None = None

        for _priority, provider in self._providers:
            # Skip providers that lack the required capability.
            if required_capability and required_capability not in provider.capabilities():
                continue

            if not provider.is_available():
                continue

            result = provider.reason(
                prompt=prompt,
                system=system,
                tools=tools,
            )
            if result.ok:
                return result
            last_error = result.error
            logger.debug(
                "Provider %s failed: %s; trying next...", provider.name, result.error
            )

        return ModelResult(
            text="",
            source="none",
            error=last_error or "Ningún proveedor de modelo disponible.",
        )

    def best_available(self) -> ModelProvider | None:
        """Return the highest-priority provider that is currently available."""
        for _priority, provider in self._providers:
            if provider.is_available():
                return provider
        return None

    @property
    def available_providers(self) -> list[str]:
        """Return names of providers that are currently reachable."""
        return [p.name for _pri, p in self._providers if p.is_available()]

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> ModelRouter:
        """Create a router pre-configured with the built-in providers.

        Priority:
          10 — Ollama (local, always tried first)
          20 — Gemini (cloud fallback)
        """
        router = cls()
        router.register(OllamaProvider(), priority=10)
        router.register(GeminiProvider(), priority=20)
        return router
