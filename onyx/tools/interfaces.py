"""
tools/interfaces.py — Abstract tool interface.

Every tool (whether from ``actions/``, a built-in, or a plugin)
implements ``Tool`` so that the registry and executor can treat
them uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    """Immutable metadata describing a tool."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema dict
    category: str = "general"
    idempotent: bool = False
    timeout: float = 30.0


@dataclass
class ToolResult:
    """Result of a single ``execute()`` call."""

    success: bool
    output: str
    error: str | None = None
    duration_ms: float = 0.0
    from_cache: bool = False


class Tool(ABC):
    """Abstract interface for an executable tool."""

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the tool's metadata (name, description, parameters, …)."""

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> ToolResult:
        """Run the tool with the given parameters and return a result."""
