"""Model providers and routing for ONYX.

Supports local models (Ollama) and cloud models (Gemini, OpenRouter)
through a unified ``ModelProvider`` interface with automatic fallback.
"""

from __future__ import annotations

from onyx.models.interfaces import ModelCapability, ModelProvider, ModelResult
from onyx.models.router import ModelRouter

__all__ = ["ModelCapability", "ModelProvider", "ModelResult", "ModelRouter"]
