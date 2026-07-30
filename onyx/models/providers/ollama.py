"""
models/providers/ollama.py — Ollama model provider.

Wraps the existing ``core/llm_router.py`` functions and extends them
with tool-calling support (mirroring ``actions/local_brain.py``).

Does NOT modify ``core/llm_router.py`` or ``actions/local_brain.py``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Iterator

from onyx.models.interfaces import ModelCapability, ModelProvider, ModelResult

OLLAMA_HOST = "http://localhost:11434"

# Preferred local models, ordered by capability (best first).
_PREFERRED_MODELS = (
    "qwen2.5:7b",
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    "llama3.2:3b",
    "llama3.2:1b",
    "phi3:mini",
    "gemma2:2b",
)


class OllamaProvider(ModelProvider):
    """Provider that talks to a local Ollama server via its REST API.

    Uses only the Python standard library (``urllib``) so it has zero
    extra dependencies beyond what ONYX already needs.
    """

    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    # ── ModelProvider interface ───────────────────────────────────────────

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        return _local_available(self._host)

    def capabilities(self) -> set[ModelCapability]:
        return {ModelCapability.TEXT_GENERATION, ModelCapability.TOOL_CALLING}

    def reason(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResult:
        model = self._model or pick_local_model(self._host)
        if not model:
            return ModelResult(
                text="",
                source="none",
                error="Ollama no disponible o sin modelos instalados.",
            )

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 8192,
            },
        }
        if tools:
            payload["tools"] = [_to_ollama_tool(t) for t in tools]

        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                f"{self._host}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())

            message = data.get("message", {}) or {}
            text = (message.get("content") or "").strip()
            tool_calls = _extract_tool_calls(message)
            dur = (time.perf_counter() - t0) * 1000

            return ModelResult(
                text=text,
                source="ollama",
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
        model = self._model or pick_local_model(self._host)
        if not model:
            return

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.3, "num_ctx": 8192},
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            for line in resp:
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = ((chunk.get("message") or {}).get("content") or "")
                    if token:
                        yield token
                except json.JSONDecodeError:
                    continue


# ── Internal helpers (mirror core/llm_router.py) ─────────────────────


def _local_available(host: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def _list_models(host: str, timeout: float = 3.0) -> list[str]:
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def pick_local_model(host: str) -> str | None:
    installed = _list_models(host)
    if not installed:
        return None
    installed_set = set(installed)
    for pref in _PREFERRED_MODELS:
        if pref in installed_set:
            return pref
    for pref in _PREFERRED_MODELS:
        base = pref.split(":")[0]
        for inst in installed:
            if inst.startswith(base):
                return inst
    return installed[0]


def _to_ollama_tool(tool_decl: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool_decl["name"],
            "description": tool_decl.get("description", ""),
            "parameters": tool_decl.get("parameters", {}),
        },
    }


def _extract_tool_calls(message: dict) -> list[dict]:
    calls = message.get("tool_calls", [])
    results: list[dict] = []
    for tc in calls:
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        results.append({"name": fn.get("name", ""), "arguments": args})
    return results
