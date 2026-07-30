"""
config/manager.py — Configuration manager for ONYX.

Reads from config/api_keys.json and provides a unified typed interface
for the entire project. Thread-safe. Cached in memory.

Does NOT replace existing config loading in main.py, ui.py, or
memory/config_manager.py — those continue to work as before.
New code should use this module instead of reading JSON files directly.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


def _get_project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


_CONFIG_FILENAME = "api_keys.json"


class ConfigManager:
    """Unified access to ONYX configuration values.

    Reads from config/api_keys.json and caches values in memory.
    Thread-safe for concurrent access from tools, agents, and UI.

    Basic usage:
        from onyx.config.manager import config
        api_key = config.get("gemini_api_key")
        theme = config.get("onyx_theme", "gold")
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = (config_dir or _get_project_root() / "config").resolve()
        self._lock = threading.RLock()
        self._cache: dict[str, Any] = {}
        self._loaded = False

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Return a config value by key, or *default* if missing."""
        self._ensure_loaded()
        with self._lock:
            return self._cache.get(key, default)

    def get_all(self) -> dict[str, Any]:
        """Return a shallow copy of all loaded config values."""
        self._ensure_loaded()
        with self._lock:
            return dict(self._cache)

    def reload(self) -> None:
        """Force a fresh read from disk on the next ``get()`` call."""
        with self._lock:
            self._cache = self._load()
            self._loaded = True

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        """Read config/api_keys.json and return its contents as a dict."""
        cfg: dict[str, Any] = {}
        path = self._config_dir / _CONFIG_FILENAME
        if path.exists():
            try:
                cfg.update(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        return cfg

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            with self._lock:
                if not self._loaded:
                    self._cache = self._load()
                    self._loaded = True


# Singleton instance — importable from any module.
config = ConfigManager()
