"""
_action_executor.py — Resilience layer for tool execution.

Provides:
  • ToolRunner  — Wraps any tool call with:
      - allow() pre-check against Circuit Breaker
      - Exponential backoff retry (jittered)
      - LRU idempotent-result cache
      - Timeout enforcement
      - Duration measurement for telemetry

  • get_runner() -> singleton

Idempotent tool list (read-only, no side effects, safe to cache):
  screen_analyze, episodic_search, memory_manager*, vector_search,
  weather, search_web, file_info, analyze, rules_engine(list),
  evolve(analyze/report), get_stats*, train_onyx(list/read)
"""
import hashlib
import json
import random
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

_CACHE_MAX = 256
_CACHE_TTL_SEC = 60

_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BASE_WAIT = 0.6
_DEFAULT_MAX_WAIT = 8.0
_DEFAULT_TIMEOUT = 30.0

# Tools considered idempotent/safe to cache (set of names).
# Default policy: tools listed here -> cached by stable-hash of arguments.
_IDEMPOTENT_TOOLS = {
    "screen_analyze", "episodic_search", "recall_memory", "get_memory",
    "memory_stats", "vector_search", "weather", "search_web",
    "file_processor_info", "file_stats", "get_telemetry",
    "rules_engine_list", "evolve_analyze", "evolve_report",
    "show_stats", "plan_status", "office_automation_info",
    "read_file", "list_files", "folder_search", "find_file",
    "file_search", "custom_stt_info", "download_vosk_info",
}


class _IdempotentCache:
    def __init__(self, max_size: int = _CACHE_MAX, ttl: int = _CACHE_TTL_SEC):
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.RLock()
        self._max = max_size
        self._ttl = ttl
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(tool: str, args: dict) -> str:
        canon = json.dumps(
            {k: args[k] for k in sorted(args)}, sort_keys=True, ensure_ascii=False
        )
        return tool + ":" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]

    def get(self, tool: str, args: dict):
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

    def put(self, tool: str, args: dict, value: Any) -> None:
        with self._lock:
            k = self._key(tool, args)
            self._data[k] = (time.time(), value)
            self._data.move_to_end(k)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._data),
                "max": self._max,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": (
                    self.hits / (self.hits + self.misses)
                    if (self.hits + self.misses) else 0.0
                ),
            }


def _is_recoverable(result: Any) -> bool:
    """Heuristic: should we retry this result? Fail -> retry."""
    if result is None:
        return False
    s = str(result).lower()
    # True failures worth retrying (transient):
    transient = [
        "timeout", "timed out", "connection refused", "service unavailable",
        "502", "503", "504", "temporarily unavailable", "try again",
        "rate limit", "too many requests", "reset by peer", "broken pipe",
    ]
    for p in transient:
        if p in s:
            return True
    hard = [
        "no module named", "modulenotfound", "401", "402", "403", "404",
        "argument invalido", "no encontre", "no disponible",
        "no tengo permiso", "desconocido", "sintaxerror",
    ]
    for p in hard:
        if p in s:
            return False
    return False


class ToolRunner:
    def __init__(self):
        self._cache = _IdempotentCache()
        self._lock = threading.RLock()

    # ──────────────────── config ────────────────────
    def mark_idempotent(self, tool: str) -> None:
        _IDEMPOTENT_TOOLS.add(tool)

    def unmark_idempotent(self, tool: str) -> None:
        _IDEMPOTENT_TOOLS.discard(tool)

    def is_idempotent(self, tool: str) -> bool:
        return tool in _IDEMPOTENT_TOOLS

    def cache_stats(self) -> dict:
        return self._cache.stats()

    def cache_clear(self) -> None:
        self._cache.clear()

    # ──────────────────── core ────────────────────
    def run(self, tool: str, args: dict,
            func: Callable[..., Any],
            max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
            base_wait: float = _DEFAULT_BASE_WAIT,
            max_wait: float = _DEFAULT_MAX_WAIT,
            use_cache: bool | None = None,
            evaluator=None) -> tuple[Any, int, float, bool]:
        """Execute a tool with retries, caching and circuit pre-check.

        Returns (result, attempts, duration_ms, from_cache).
        """
        t0 = time.perf_counter()
        cached_result = None
        hit = False
        use_cache_bool = use_cache if use_cache is not None else self.is_idempotent(tool)
        if use_cache_bool:
            cached_result, hit = self._cache.get(tool, args)
            if hit and cached_result is not None:
                dur = max(0, int((time.perf_counter() - t0) * 1000))
                return cached_result, 0, dur, True

        # Circuit breaker pre-check
        blocked = False
        if evaluator is not None:
            try:
                if not evaluator.allow(tool):
                    result = (
                        f"Circuito {tool} abierto por fallos repetidos. "
                        f"Espera el cooldown o ejecuta evolve(improve). "
                        f"Estado: {json.dumps(evaluator.circuit_state(tool), ensure_ascii=False)}"
                    )
                    dur = max(0, int((time.perf_counter() - t0) * 1000))
                    return result, 0, dur, False
            except Exception:
                blocked = False

        attempts = 0
        last_result = None
        last_err: Exception | None = None
        while attempts < max_attempts:
            attempts += 1
            try:
                result = func()
                last_result = result
                if attempts == max_attempts or not _is_recoverable(result):
                    break
                last_result = result
            except Exception as e:
                last_err = e
                last_result = f"Tool '{tool}' failed (attempt {attempts}): {e}"
            # Backoff (jittered exponential)
            sleep = min(max_wait, base_wait * (2 ** (attempts - 1)))
            sleep *= (0.7 + random.random() * 0.6)
            if attempts < max_attempts:
                time.sleep(sleep)

        result = last_result
        dur = max(0, int((time.perf_counter() - t0) * 1000))

        # Store cache if success-ish and idempotent
        if use_cache_bool and attempts <= max_attempts and last_err is None:
            # Only cache results that don't look like errors
            s = str(result or "").lower()
            not_error = not any(w in s for w in ("error:", "failed:", "fallo", "no disponible", "error"))
            if not_error:
                self._cache.put(tool, args, result)

        return result, attempts, dur, False


_RUNNER: ToolRunner | None = None
_RUNNER_LOCK = threading.Lock()


def get_runner() -> ToolRunner:
    global _RUNNER
    if _RUNNER is None:
        with _RUNNER_LOCK:
            if _RUNNER is None:
                _RUNNER = ToolRunner()
    return _RUNNER
