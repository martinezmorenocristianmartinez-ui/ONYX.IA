"""Tools registry and execution for ONYX.

Wraps all existing ``actions/`` modules behind a unified ``Tool``
interface so the Brain can discover, inspect, and execute any tool
without knowing its implementation details.
"""

from __future__ import annotations

from onyx.tools.interfaces import Tool, ToolResult, ToolSpec
from onyx.tools.registry import ToolRegistry
from onyx.tools.executor import ToolExecutor

__all__ = ["Tool", "ToolResult", "ToolSpec", "ToolRegistry", "ToolExecutor"]
