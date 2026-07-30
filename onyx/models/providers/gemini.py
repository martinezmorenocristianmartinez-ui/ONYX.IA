"""
models/providers/gemini.py — Gemini model provider (non-live).

Standalone client for text generation via the Gemini API.
Does NOT use the Live (audio) session — that stays in ``main.py``
for backward compatibility.

Uses the ``google.genai`` SDK (already installed in the project).
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from onyx.config.manager import config
from onyx.models.interfaces import ModelCapability, ModelProvider, ModelResult


class GeminiProvider(ModelProvider):
    """Provider for Google Gemini models (text, vision, tool calling).

    Reads the API key from ``config/api_keys.json`` via ``onyx.config.manager``.
    This is the **non-live** client; the Live (audio) session in ``main.py``
    is unaffected.
    """

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        timeout: float = 30.0,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._client = None  # lazy-init on first use

    # ── ModelProvider interface ───────────────────────────────────────────

    @property
    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        api_key = config.get("gemini_api_key", "").strip()
        if not api_key:
            return False
        try:
            client = self._get_client()
            # Quick connectivity check by listing models
            client.models.list()
            return True
        except Exception:
            return False

    def capabilities(self) -> set[ModelCapability]:
        return {
            ModelCapability.TEXT_GENERATION,
            ModelCapability.TOOL_CALLING,
            ModelCapability.VISION,
            ModelCapability.STREAMING,
        }

    def reason(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResult:
        client = self._get_client()
        if client is None:
            return ModelResult(
                text="", source="none", error="Gemini API key no configurada."
            )

        t0 = time.perf_counter()
        try:
            contents = prompt
            genai_config: dict[str, Any] = {}

            if system:
                genai_config["system_instruction"] = system

            if tools:
                genai_config["tools"] = [
                    {"function_declarations": tools}
                ]

            response = client.models.generate_content(
                model=self._model,
                contents=contents,
                config=genai_config,
            )

            dur = (time.perf_counter() - t0) * 1000
            text = response.text.strip() if response.text else ""

            # Extract tool calls from the response
            tool_calls: list[dict[str, Any]] = []
            if response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if part.function_call:
                                tool_calls.append({
                                    "name": part.function_call.name,
                                    "arguments": dict(part.function_call.args),
                                })

            return ModelResult(
                text=text,
                source="gemini",
                duration_ms=dur,
                tool_calls=tool_calls,
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000
            return ModelResult(
                text="",
                source="none",
                error=str(e),
                duration_ms=dur,
            )

    def stream(
        self,
        prompt: str,
        system: str | None = None,
    ) -> Iterator[str]:
        client = self._get_client()
        if client is None:
            return

        genai_config: dict[str, Any] = {}
        if system:
            genai_config["system_instruction"] = system

        response = client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=genai_config,
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_client(self):
        if self._client is not None:
            return self._client

        api_key = config.get("gemini_api_key", "").strip()
        if not api_key:
            return None

        try:
            from google.genai import Client as GenaiClient

            self._client = GenaiClient(api_key=api_key)
            return self._client
        except Exception:
            return None
