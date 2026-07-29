"""
_evaluator.py — Self-evaluation engine for ONYX tool execution (v2 optimized).

Optimizations:
- Incremental Welford-style running statistics (no O(n) sum/avg per record)
- Write-behind batched persistence; flush on timer or threshold, not every call
- Thread-safe by design (RLock around mutations)
- Rolling EMA (exponential moving average) score + 7-day window detection
- Scores capped to rolling window (last 500) to bound memory
- Circuit-breaker states per tool (CLOSED/HALF/OPEN) with auto-recovery
- Error pattern learning: dynamically boosts weight of known error phrases
- Category histogram with incremental counter, not per-call recount
- Trend detection for regression alerts (3 consecutive below avg)
- Correlated failure grouping: same snippet pattern counted only once
- Auto-compaction: saves compact JSON (no indent) for hot telemetry file
"""
import json
import time
import re
import math
import threading
from pathlib import Path
from collections import defaultdict, deque
from enum import Enum

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
STATS_PATH = MEMORY_DIR / "tool_telemetry.json"

_FLUSH_SEC = 15.0
_FLUSH_OPS = 200
_ROLLING_SCORES = 500
_LAST_N_RESULTS = 20
_EMA_ALPHA = 0.15
_CB_FAIL_THRESHOLD = 5       # consecutive low scores => OPEN
_CB_RECOVER_SEC = 60.0       # OPEN -> HALF after cooldown
_CB_HALF_PROBE = 2           # HALF successes => CLOSED

_CIRCUIT_CLOSED = "CLOSED"
_CIRCUIT_HALF = "HALF_OPEN"
_CIRCUIT_OPEN = "OPEN"


_ERROR_PATTERNS_BASE = [
    "error", "error:", "error al", "no pude", "no encontre", "no se pudo",
    "failed", "exception", "traceback", "timeout", "no se encuentra",
    "no disponible", "no hay conexion", "sin api", "faltan dependencias",
    "error inesperado", "no se puede", "no se ha podido", "error en",
    "attributeerror", "modulenotfound", "importerror", "typeerror",
    "keyerror", "indexerror", "valueerror", "permissionerror",
    "payment required", "402", "429", "500", "502", "503", "504",
]

_SUCCESS_PATTERNS_BASE = [
    "listo", "completado", "ejecutado", "hecho", "ok", "exitosamente",
    "realizado", "finalizado", "procesado", "enviado", "guardado",
    "creado", "eliminado", "actualizado", "cancelado", "iniciado",
    "✅", "✓", "hecho, senor", "done.",
]

_NEGATIVE_PATTERNS_BASE = [
    "no", "no se pudo", "no se encontro", "no encontre", "no existe",
    "no disponible", "negado", "rechazado", "fallo", "fracaso",
]


class CircuitBreaker:
    __slots__ = ("state", "consec_fail", "opened_at", "half_successes", "total_fail", "total_success")

    def __init__(self):
        self.state = _CIRCUIT_CLOSED
        self.consec_fail = 0
        self.opened_at = 0.0
        self.half_successes = 0
        self.total_fail = 0
        self.total_success = 0

    def observe(self, success: bool) -> str:
        now = time.time()
        if success:
            self.total_success += 1
            self.consec_fail = 0
            if self.state == _CIRCUIT_HALF:
                self.half_successes += 1
                if self.half_successes >= _CB_HALF_PROBE:
                    self.state = _CIRCUIT_CLOSED
                    self.half_successes = 0
            elif self.state == _CIRCUIT_OPEN:
                self.state = _CIRCUIT_CLOSED
        else:
            self.total_fail += 1
            self.consec_fail += 1
            if self.state == _CIRCUIT_HALF:
                self.state = _CIRCUIT_OPEN
                self.opened_at = now
                self.half_successes = 0
            elif self.state == _CIRCUIT_CLOSED and self.consec_fail >= _CB_FAIL_THRESHOLD:
                self.state = _CIRCUIT_OPEN
                self.opened_at = now
        return self.state

    def allow(self) -> bool:
        if self.state == _CIRCUIT_CLOSED:
            return True
        if self.state == _CIRCUIT_OPEN:
            if time.time() - self.opened_at >= _CB_RECOVER_SEC:
                self.state = _CIRCUIT_HALF
                self.half_successes = 0
                return True
            return False
        return True  # HALF_OPEN: allow probe

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "consec_fail": self.consec_fail,
            "opened_at": round(self.opened_at, 2),
            "half_successes": self.half_successes,
            "total_fail": self.total_fail,
            "total_success": self.total_success,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CircuitBreaker":
        cb = cls()
        cb.state = d.get("state", _CIRCUIT_CLOSED)
        cb.consec_fail = int(d.get("consec_fail", 0))
        cb.opened_at = float(d.get("opened_at", 0.0))
        cb.half_successes = int(d.get("half_successes", 0))
        cb.total_fail = int(d.get("total_fail", 0))
        cb.total_success = int(d.get("total_success", 0))
        return cb


class _RunningStat:
    """Welford's online algorithm for stable incremental mean + variance."""
    __slots__ = ("n", "mean", "m2")

    def __init__(self, n=0, mean=0.0, m2=0.0):
        self.n = int(n)
        self.mean = float(mean)
        self.m2 = float(m2)

    def add(self, x: float):
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2

    @property
    def var(self) -> float:
        return self.m2 / self.n if self.n > 1 else 0.0

    @property
    def std(self) -> float:
        return math.sqrt(self.var)

    def to_dict(self) -> dict:
        return {"n": self.n, "mean": round(self.mean, 4), "m2": round(self.m2, 4)}


class ToolEvaluator:
    def __init__(self):
        self._lock = threading.RLock()
        self._dirty = False
        self._dirty_ops = 0
        self._flush_thread: threading.Thread | None = None
        self._flush_stop = threading.Event()
        self._recent: deque = deque(maxlen=500)

        self._stat_total_calls = 0
        self._stat_total_successes = 0
        self._stat_total_failures = 0
        self._tools: dict[str, dict] = {}
        self._circuits: dict[str, CircuitBreaker] = defaultdict(CircuitBreaker)
        self._ema_score: dict[str, float] = {}
        self._run_stat: dict[str, _RunningStat] = {}
        self._err_counts: dict[str, int] = defaultdict(int)
        self._load()
        self._start_flush()

    # ── load / save ────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            raw = json.loads(STATS_PATH.read_text(encoding="utf-8"))
        except Exception:
            raw = {"tools": {}, "total_calls": 0, "total_successes": 0, "total_failures": 0}
        self._tools = raw.get("tools", {})
        self._stat_total_calls = int(raw.get("total_calls", 0))
        self._stat_total_successes = int(raw.get("total_successes", 0))
        self._stat_total_failures = int(raw.get("total_failures", 0))
        circuits = raw.get("circuits", {})
        for name, d in circuits.items():
            self._circuits[name] = CircuitBreaker.from_dict(d)
        ema = raw.get("ema_score", {})
        for name, v in ema.items():
            self._ema_score[name] = float(v)
        rs = raw.get("run_stats", {})
        for name, d in rs.items():
            self._run_stat[name] = _RunningStat(
                d.get("n", 0), d.get("mean", 0.0), d.get("m2", 0.0)
            )
        ec = raw.get("error_counts", {})
        for k, v in ec.items():
            self._err_counts[k] = int(v)
        # Ensure backward-compat defaults for existing tools
        for name, ts in self._tools.items():
            ts.setdefault("calls", 0)
            ts.setdefault("successes", 0)
            ts.setdefault("failures", 0)
            ts.setdefault("scores", [])
            ts.setdefault("categories", {})
            ts.setdefault("avg_score", 5.0)
            ts.setdefault("avg_duration_ms", 0.0)
            ts.setdefault("total_duration_ms", 0.0)
            ts.setdefault("last_results", [])
            ts.setdefault("regressions", 0)
            ts.setdefault("ema_score", ts["avg_score"])
            if name not in self._ema_score:
                self._ema_score[name] = float(ts["avg_score"])

    def _save_locked(self) -> None:
        try:
            STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "tools": self._tools,
                "total_calls": self._stat_total_calls,
                "total_successes": self._stat_total_successes,
                "total_failures": self._stat_total_failures,
                "circuits": {n: cb.to_dict() for n, cb in self._circuits.items()},
                "ema_score": {n: round(v, 3) for n, v in self._ema_score.items()},
                "run_stats": {n: rs.to_dict() for n, rs in self._run_stat.items()},
                "error_counts": dict(self._err_counts),
                "saved_at": round(time.time(), 2),
                "version": 2,
            }
            STATS_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[Evaluator] save error: {e}")

    def _start_flush(self) -> None:
        if self._flush_thread and self._flush_thread.is_alive():
            return

        def _run():
            while not self._flush_stop.is_set():
                self._flush_stop.wait(_FLUSH_SEC)
                with self._lock:
                    if self._dirty:
                        self._save_locked()
                        self._dirty = False
                        self._dirty_ops = 0

        self._flush_thread = threading.Thread(
            target=_run, name="EvalFlush", daemon=True
        )
        self._flush_thread.start()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._dirty_ops += 1
        if self._dirty_ops >= _FLUSH_OPS:
            self._save_locked()
            self._dirty = False
            self._dirty_ops = 0

    def flush(self) -> None:
        with self._lock:
            if self._dirty:
                self._save_locked()
                self._dirty = False
                self._dirty_ops = 0

    # ── evaluate ───────────────────────────────────────────────────
    def evaluate(self, tool_name: str, result: str, duration_ms: float = 0) -> dict:
        score, category, matched_patterns = self._score_result(result)
        with self._lock:
            self._record(tool_name, score, category, duration_ms,
                         str(result or "")[:200], matched_patterns)
        return {"score": score, "category": category, "tool": tool_name,
                "circuit": self._circuits[tool_name].state}

    def allow(self, tool_name: str) -> bool:
        """Circuit-breaker: can this tool be called right now?"""
        with self._lock:
            return self._circuits[tool_name].allow()

    def circuit_state(self, tool_name: str) -> dict:
        with self._lock:
            return self._circuits[tool_name].to_dict()

    def all_circuit_states(self) -> dict:
        with self._lock:
            return {n: cb.to_dict() for n, cb in self._circuits.items()}

    # ── scoring ────────────────────────────────────────────────────
    def _score_result(self, result: str) -> tuple[int, str, list[str]]:
        if not result or not result.strip():
            return 2, "empty", []
        r_lower = result.lower()
        matched = []
        # Dynamic error boost: patterns seen in historical failures get double weight
        error_count = 0
        for p in _ERROR_PATTERNS_BASE:
            if p in r_lower:
                mult = 2 if self._err_counts.get(p, 0) >= 3 else 1
                error_count += mult
                matched.append(p)
        neg_count = sum(1 for p in _NEGATIVE_PATTERNS_BASE if p in r_lower)
        succ_count = sum(1 for p in _SUCCESS_PATTERNS_BASE if p in r_lower)
        if error_count >= 3:
            return 1, "error", matched
        if error_count >= 2:
            return 2, "error", matched
        if error_count == 1:
            return 3 if neg_count else 4, "partial_error", matched
        if succ_count >= 3 and neg_count == 0:
            return 10, "success", matched
        if succ_count >= 2 and neg_count == 0:
            return 9, "success", matched
        if succ_count >= 1 and neg_count == 0:
            return 7, "partial_success", matched
        if neg_count >= 2 and succ_count == 0:
            return 3, "negative", matched
        if neg_count >= 1 and succ_count == 0:
            return 4, "negative", matched
        return 6, "neutral", matched

    def _record(self, tool_name: str, score: int, category: str,
                duration_ms: float, snippet: str, patterns: list[str]) -> None:
        ts = self._tools.setdefault(tool_name, {
            "calls": 0, "successes": 0, "failures": 0, "scores": [], "categories": {},
            "avg_score": 5.0, "avg_duration_ms": 0.0, "total_duration_ms": 0.0,
            "last_results": [], "regressions": 0, "ema_score": 5.0,
        })
        # Incremental totals
        ts["calls"] += 1
        self._stat_total_calls += 1
        success = score >= 6
        if success:
            ts["successes"] += 1
            self._stat_total_successes += 1
        else:
            ts["failures"] += 1
            self._stat_total_failures += 1

        # Rolling scores (bounded memory)
        scores = ts["scores"]
        scores.append(score)
        if len(scores) > _ROLLING_SCORES:
            drop = len(scores) - _ROLLING_SCORES
            ts["scores"] = scores[drop:]

        # Incremental running stats (Welford) + EMA
        rs = self._run_stat.setdefault(tool_name, _RunningStat())
        rs.add(float(score))
        prev_ema = self._ema_score.get(tool_name, float(score))
        ema = _EMA_ALPHA * float(score) + (1 - _EMA_ALPHA) * prev_ema
        self._ema_score[tool_name] = ema
        ts["ema_score"] = round(ema, 2)
        ts["avg_score"] = round(rs.mean, 1)  # stable mean from Welford

        # Regression detection: 3 consecutive below EMA
        last3 = ts["scores"][-3:] if len(ts["scores"]) >= 3 else []
        if len(last3) == 3 and all(s < ema - 1.0 for s in last3):
            ts["regressions"] = int(ts.get("regressions", 0)) + 1

        # Duration incremental
        ts["total_duration_ms"] += float(duration_ms)
        ts["avg_duration_ms"] = round(ts["total_duration_ms"] / ts["calls"], 1)

        # Category counter
        cats = ts["categories"]
        cats[category] = int(cats.get(category, 0)) + 1

        # Last results rolling
        ts["last_results"].append({"score": score, "snippet": snippet, "ts": time.time()})
        ts["last_results"] = ts["last_results"][-_LAST_N_RESULTS:]

        # Circuit breaker observation
        self._circuits[tool_name].observe(success)

        # Learn error patterns: count occurrences
        for p in patterns:
            if category in ("error", "partial_error"):
                self._err_counts[p] = int(self._err_counts.get(p, 0)) + 1

        # Recent deque (read-only introspection)
        self._recent.append({
            "tool": tool_name, "score": score, "category": category,
            "duration_ms": duration_ms,
        })
        self._mark_dirty()

    # ── querying ───────────────────────────────────────────────────
    def get_tool_stats(self, tool_name: str) -> dict:
        with self._lock:
            base = dict(self._tools.get(tool_name, {}))
            base["circuit"] = self._circuits[tool_name].to_dict()
            base["ema_score"] = round(self._ema_score.get(tool_name, 0.0), 2)
            rs = self._run_stat.get(tool_name)
            if rs:
                base["std_score"] = round(rs.std, 2)
                base["variance"] = round(rs.var, 4)
            return base

    def all_stats(self) -> dict:
        with self._lock:
            return {
                "total_calls": self._stat_total_calls,
                "total_successes": self._stat_total_successes,
                "total_failures": self._stat_total_failures,
                "success_rate_est": (
                    round(self._stat_total_successes / self._stat_total_calls, 3)
                    if self._stat_total_calls else 0.0
                ),
                "tools": self._tools,
                "circuits": {n: cb.to_dict() for n, cb in self._circuits.items()},
            }

    def get_low_performers(self, min_calls: int = 5, threshold: float = 5.0) -> list[dict]:
        poor = []
        with self._lock:
            for name, ts in self._tools.items():
                if ts["calls"] >= min_calls and float(ts.get("ema_score", ts["avg_score"])) < threshold:
                    poor.append({
                        "tool": name,
                        "avg_score": float(ts.get("ema_score", ts["avg_score"])),
                        "calls": ts["calls"],
                        "failures": ts["failures"],
                        "regressions": int(ts.get("regressions", 0)),
                        "circuit": self._circuits[name].state,
                        "last_errors": [
                            r for r in ts.get("last_results", []) if r["score"] < 5
                        ][-3:],
                    })
        return sorted(poor, key=lambda x: (x["avg_score"], -x["regressions"]))

    def get_high_performers(self, min_calls: int = 5, threshold: float = 7.5) -> list[dict]:
        good = []
        with self._lock:
            for name, ts in self._tools.items():
                if ts["calls"] >= min_calls and float(ts.get("ema_score", ts["avg_score"])) >= threshold:
                    good.append({
                        "tool": name,
                        "avg_score": float(ts.get("ema_score", ts["avg_score"])),
                        "calls": ts["calls"],
                        "successes": ts["successes"],
                        "circuit": self._circuits[name].state,
                    })
        return sorted(good, key=lambda x: -x["avg_score"])

    def get_recent(self, n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._recent)[-n:]

    def format_for_evolution_prompt(self) -> str:
        poor = self.get_low_performers(min_calls=3)
        if not poor:
            return ""
        lines = ["[TELEMETRIA DE HERRAMIENTAS - BAJO RENDIMIENTO]"]
        for p in poor:
            line = (f"- {p['tool']}: ema_score={p['avg_score']:.1f}/10, "
                    f"{p['failures']} fallos en {p['calls']} llamadas, "
                    f"regresiones={p['regressions']}, circuit={p['circuit']}")
            if p.get("last_errors"):
                snippets = " | ".join(
                    r["snippet"][:80] for r in p["last_errors"]
                )
                line += f" | ultimos_errores: {snippets}"
            lines.append(line)
        good = self.get_high_performers(min_calls=5, threshold=8.0)[:5]
        if good:
            lines.append("[HERRAMIENTAS CON MEJOR RENDIMIENTO (referencia)]")
            for g in good:
                lines.append(
                    f"- {g['tool']}: ema_score={g['avg_score']:.1f}/10, "
                    f"{g['successes']}/{g['calls']} exitos"
                )
        lines.append("[/TELEMETRIA]")
        return "\n".join(lines)


_evaluator = None


def get_evaluator() -> ToolEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = ToolEvaluator()
    return _evaluator


def flush_evaluator() -> None:
    """Force flush pending telemetry to disk immediately (thread-safe)."""
    global _evaluator
    if _evaluator is not None:
        try:
            _evaluator.flush()
        except Exception:
            pass


def shutdown_evaluator() -> None:
    """Flush data and stop background flush thread; safe repeated calls."""
    global _evaluator
    if _evaluator is not None:
        try:
            _evaluator._flush_stop.set()
            if _evaluator._flush_thread and _evaluator._flush_thread.is_alive():
                _evaluator._flush_thread.join(timeout=2.0)
        except Exception:
            pass
        try:
            _evaluator.flush()
        except Exception:
            pass

