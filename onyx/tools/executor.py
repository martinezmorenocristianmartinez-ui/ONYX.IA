"""
tools/executor.py — Executes tools with resilience guarantees.

Wraps the existing ``actions/_action_executor.py`` logic:
- LRU idempotent-result cache
- Exponential backoff retry with jitter
- Circuit-breaker integration (via Evaluator)
- Duration measurement for telemetry
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from collections import OrderedDict
from typing import Any

from onyx.tools.interfaces import Tool, ToolResult

_CACHE_MAX = 256
_CACHE_TTL_SEC = 60
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BASE_WAIT = 0.6
_DEFAULT_MAX_WAIT = 8.0


class _IdempotentCache:
    """LRU cache with TTL for idempotent tool results."""

    def __init__(self, max_size: int = _CACHE_MAX, ttl: int = _CACHE_TTL_SEC) -> None:
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.RLock()
        self._max = max_size
        self._ttl = ttl
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(tool: str, args: dict) -> str:
        canon = json.dumps({k: args[k] for k in sorted(args)}, sort_keys=True, ensure_ascii=False)
        return tool + ":" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]

    def get(self, tool: str, args: dict) -> tuple[str | None, bool]:
        with self._lock:
            k = self._key(tool, args)
            if k not in self._data:
                self.misses += 1
                return None, False
            ts, val = self._data[k]
            if time.time() - ts > self._ttl:
                self._data.pop(k, None)
                self.misses += 1
                return None, False
            self._data.move_to_end(k)
            self.hits += 1
            return val, True

    def put(self, tool: str, args: dict, value: str) -> None:
        with self._lock:
            k = self._key(tool, args)
            self._data[k] = (time.time(), value)
            self._data.move_to_end(k)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class ToolExecutor:
    """Executes tools with caching, retry, and telemetry.

    Usage:
        executor = ToolExecutor()
        result = executor.execute(tool, {"app_name": "Chrome"})
    """

    def __init__(self) -> None:
        self._cache = _IdempotentCache()
        self._idempotent: set[str] = set()

    def mark_idempotent(self, name: str) -> None:
        self._idempotent.add(name)

    def is_idempotent(self, name: str) -> bool:
        return name in self._idempotent

    def execute(
        self,
        tool: Tool,
        params: dict[str, Any],
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        base_wait: float = _DEFAULT_BASE_WAIT,
        max_wait: float = _DEFAULT_MAX_WAIT,
    ) -> ToolResult:
        """Run a tool with resilience guarantees.

        For idempotent tools, results are cached (keyed by canonical
        parameter dict).  Transient failures trigger exponential backoff
        with jitter.
        """
        t0 = time.perf_counter()
        name = tool.spec.name

        # ── Cache check for idempotent tools ──
        if self.is_idempotent(name):
            cached, hit = self._cache.get(name, params)
            if hit and cached is not None:
                dur = (time.perf_counter() - t0) * 1000
                return ToolResult(success=True, output=cached, duration_ms=dur, from_cache=True)

        # ── Execution with retry ──
        attempts = 0
        last_output = ""
        last_error: str | None = None

        while attempts < max_attempts:
            attempts += 1
            try:
                result = tool.execute(params)
                if result.success:
                    last_output = result.output
                    # Cache if idempotent and looks successful
                    if self.is_idempotent(name) and last_output:
                        self._cache.put(name, params, last_output)
                    dur = (time.perf_counter() - t0) * 1000
                    return ToolResult(
                        success=True,
                        output=last_output,
                        duration_ms=dur,
                    )
                last_output = result.output
                last_error = result.error
            except Exception as e:
                last_error = str(e)
                last_output = f"Tool '{name}' failed (attempt {attempts}): {e}"

            # Backoff before retrying
            if attempts < max_attempts:
                sleep = min(max_wait, base_wait * (2 ** (attempts - 1)))
                sleep *= 0.7 + random.random() * 0.6
                time.sleep(sleep)

        dur = (time.perf_counter() - t0) * 1000
        return ToolResult(
            success=False,
            output=last_output,
            error=last_error,
            duration_ms=dur,
        )

    def cache_clear(self) -> None:
        self._cache.clear()

    def cache_stats(self) -> dict:
        return {"hits": self._cache.hits, "misses": self._cache.misses}
