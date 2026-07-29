"""
plugin_loader.py — Dynamic plugin loading with hot-reload for ONYX.
Detects new/modified tools, reloads modules without full reconnect,
and provides safe import isolation.
"""
import importlib
import json
import logging
import sys
import time
import traceback
from pathlib import Path
from threading import Lock, Thread

ACTIONS_DIR = Path(__file__).resolve().parent
CUSTOM_TOOLS_PATH = ACTIONS_DIR / "custom_tools.json"
RELOAD_INTERVAL = 5.0

logger = logging.getLogger("plugin_loader")


class PluginLoader:
    def __init__(self, on_tools_changed=None):
        self._lock = Lock()
        self._known_tools: dict[str, dict] = {}
        self._loaded_modules: dict[str, object] = {}
        self._on_tools_changed = on_tools_changed
        self._running = False
        self._thread = None
        self._last_mtime = 0.0
        self._load_known()

    def _load_known(self):
        if not CUSTOM_TOOLS_PATH.exists():
            return
        try:
            data = json.loads(CUSTOM_TOOLS_PATH.read_text(encoding="utf-8"))
            for entry in data:
                name = entry.get("name", "")
                if name:
                    self._known_tools[name] = entry
        except Exception:
            pass

    def get_new_tools(self, current_names: set[str]) -> list[dict]:
        new = []
        for name, entry in self._known_tools.items():
            if name not in current_names:
                new.append(entry)
        return new

    def load_plugin(self, name: str) -> tuple[bool, object | str]:
        """Import a tool module safely. Returns (success, module_or_error)."""
        try:
            # Check if already loaded
            if name in self._loaded_modules:
                return True, self._loaded_modules[name]

            # Try direct import
            module_path = f"actions.{name}"
            if module_path in sys.modules:
                module = importlib.reload(sys.modules[module_path])
            else:
                module = importlib.import_module(module_path)

            # Verify the expected function exists
            if hasattr(module, name):
                func = getattr(module, name)
                if callable(func):
                    self._loaded_modules[name] = module
                    return True, module
                else:
                    return False, f"'{name}' in module is not callable"
            else:
                return False, f"Module '{name}' has no function '{name}'"

        except Exception as e:
            return False, f"Import error: {e}\n{traceback.format_exc()}"

    def reload_plugin(self, name: str) -> tuple[bool, object | str]:
        """Force reload a module, even if already loaded."""
        module_path = f"actions.{name}"
        if module_path in sys.modules:
            del sys.modules[module_path]
        if name in self._loaded_modules:
            del self._loaded_modules[name]
        return self.load_plugin(name)

    def get_all_loaded(self) -> dict[str, object]:
        return dict(self._loaded_modules)

    def scan_custom_tools(self) -> list[dict]:
        """Scan custom_tools.json and return any new tool definitions."""
        current_mtime = CUSTOM_TOOLS_PATH.stat().st_mtime if CUSTOM_TOOLS_PATH.exists() else 0
        if current_mtime <= self._last_mtime:
            return []
        self._last_mtime = current_mtime
        old_names = set(self._known_tools.keys())
        self._load_known()
        new_names = set(self._known_tools.keys()) - old_names
        return [self._known_tools[n] for n in new_names]

    def start_auto_reload(self):
        """Start background thread that checks for new custom tools."""
        if self._running:
            return
        self._running = True
        self._thread = Thread(target=self._reload_loop, daemon=True)
        self._thread.start()

    def stop_auto_reload(self):
        self._running = False

    def _reload_loop(self):
        while self._running:
            try:
                new_tools = self.scan_custom_tools()
                if new_tools and self._on_tools_changed:
                    self._on_tools_changed(new_tools)
            except Exception:
                pass
            time.sleep(RELOAD_INTERVAL)


_loader = None


def get_loader(on_tools_changed=None) -> PluginLoader:
    global _loader
    if _loader is None:
        _loader = PluginLoader(on_tools_changed=on_tools_changed)
    return _loader
