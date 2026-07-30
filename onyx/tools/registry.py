"""
tools/registry.py — Central catalog of all tools.

Tools can be registered manually or discovered automatically by
``scanner.py``.  The registry provides lookup, search, and
categorisation without exposing the underlying modules.
"""

from __future__ import annotations

import threading
from typing import Any

from onyx.tools.interfaces import Tool


class ToolRegistry:
    """Thread-safe registry of ``Tool`` instances.

    Usage:
        registry = ToolRegistry()
        registry.register(my_tool)
        tool = registry.get("open_app")
        for tool in registry.search("browser"):
            ...
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: dict[str, Tool] = {}
        self._categories: dict[str, list[str]] = {}

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, tool: Tool) -> None:
        """Add a tool to the catalog."""
        with self._lock:
            name = tool.spec.name
            self._tools[name] = tool
            cat = tool.spec.category
            self._categories.setdefault(cat, []).append(name)

    def register_many(self, tools: list[Tool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> None:
        """Remove a tool by name."""
        with self._lock:
            tool = self._tools.pop(name, None)
            if tool is not None:
                cat = tool.spec.category
                members = self._categories.get(cat, [])
                if name in members:
                    members.remove(name)

    # ── Lookup ───────────────────────────────────────────────────────────

    def get(self, name: str) -> Tool | None:
        """Return the tool with the given name, or ``None``."""
        with self._lock:
            return self._tools.get(name)

    def get_names(self) -> list[str]:
        """Return the names of all registered tools."""
        with self._lock:
            return sorted(self._tools.keys())

    def get_by_category(self, category: str) -> list[Tool]:
        """Return all tools in a given category."""
        with self._lock:
            return [self._tools[n] for n in self._categories.get(category, []) if n in self._tools]

    @property
    def categories(self) -> list[str]:
        """Return all category names that currently have tools."""
        with self._lock:
            return sorted(self._categories.keys())

    # ── Search ───────────────────────────────────────────────────────────

    def search(self, query: str) -> list[Tool]:
        """Simple case-insensitive search across tool names and descriptions."""
        q = query.lower()
        results: list[Tool] = []
        with self._lock:
            for tool in self._tools.values():
                if q in tool.spec.name.lower() or q in tool.spec.description.lower():
                    results.append(tool)
        return results

    def count(self) -> int:
        """Return the total number of registered tools."""
        with self._lock:
            return len(self._tools)
