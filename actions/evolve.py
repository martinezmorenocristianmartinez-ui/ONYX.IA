"""
evolve.py — Self-improvement engine for ONYX (v2.1 stable).

Features (todos los pipelines probados end-to-end):
  • Backward-compat payload migration: evolution.json v1 (lista) -> v2 (dict estructurado)
  • Failure classifier con normalización Unicode/acentos
  • Action proposal generator con prioridad, auto vs manual
  • Learning persistence: long_term memory (learnings/corrections) + rules engine
  • analyze_system() diagnostica KPIs + circuit breaker states + episodic
  • improve_tool() materializa lecciones con 3 estrategias (safe/balanced/aggressive)
  • auto_improve() loop multi-herramienta
  • refactor() dump de propuestas
  • Unified tool-compatible entrypoint evolve(parameters)
  • get_evolution_report() humano-leible
"""
import json
import re
import time
import hashlib
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from collections import Counter
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "memory"
CONFIG_DIR = BASE_DIR / "config"
EVOLUTION_LOG = MEMORY_DIR / "evolution.json"
RULES_PATH = CONFIG_DIR / "rules.json"

_EVO_VERSION = 2
_MAX_LEARNINGS = 200
_MAX_RULES_AUTO = 50

_evo_lock = threading.RLock()
_evo_cache: dict[str, Any] | None = None


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ────────────────────────────────────────────────────────────────────
# IO helpers con backward-compat migrations
# ────────────────────────────────────────────────────────────────────
def _default_evo() -> dict:
    return {
        "_version": _EVO_VERSION,
        "runs": 0,
        "improvements": [],
        "proposals": [],
        "rules_added": 0,
        "learnings_stored": 0,
        "last_run": "",
        "kpis": {},
        "history": [],
    }


def _migrate_evo_v1_v2(raw: Any) -> dict:
    """Migrate evolution payload. Supports:
      - v1 list of {timestamp,action,detail,success,metadata} -> history
      - dict old schema (without _version) -> patch fields
      - None/missing -> default
    Returns always a v2 dict."""
    target = _default_evo()
    if isinstance(raw, list):
        # v1: list of audit records
        target["history"] = list(raw)
        target["runs"] = len([r for r in raw if isinstance(r, dict) and r.get("action") == "improve"])
        target["last_run"] = max(
            [r.get("timestamp", "") for r in raw if isinstance(r, dict)],
            default="",
        )
        return target
    if isinstance(raw, dict):
        # Old dict schema or already v2
        for k, v in target.items():
            if k == "_version":
                continue
            if k in raw and raw[k] is not None:
                target[k] = raw[k]
        # Preserve any other unknown keys under "extra"
        extra = {k: raw[k] for k in raw if k not in target}
        if extra:
            target["_extra_legacy"] = extra
        target["_version"] = _EVO_VERSION
        return target
    return target


def _load_evolution() -> dict:
    global _evo_cache
    if _evo_cache is not None:
        return _evo_cache
    data: Any = None
    if EVOLUTION_LOG.exists():
        try:
            data = json.loads(EVOLUTION_LOG.read_text(encoding="utf-8"))
        except Exception:
            data = None
    _evo_cache = _migrate_evo_v1_v2(data)
    return _evo_cache


def _save_evolution(data: dict) -> None:
    global _evo_cache
    data["_version"] = _EVO_VERSION
    _evo_cache = data
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        EVOLUTION_LOG.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except Exception:
        pass


def _load_rules() -> list[dict]:
    if not RULES_PATH.exists():
        return []
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "rules" in data:
            if isinstance(data["rules"], list):
                return list(data["rules"])
        if isinstance(data, list):
            return list(data)
    except Exception:
        pass
    return []


def _save_rules(rules: list[dict]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        RULES_PATH.write_text(
            json.dumps({"rules": rules}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _remember_learning(category: str, key: str, value: str,
                       ttl_days: int | None = None) -> bool:
    """Store evolution lesson into long_term memory via manager.
    Returns True on success, False otherwise."""
    try:
        from memory.memory_manager import remember
        remember(category, key, value, ttl_days=ttl_days)
        return True
    except Exception:
        return False


# ────────────────────────────────────────────────────────────────────
# Telemetry/memory accessors
# ────────────────────────────────────────────────────────────────────
def _get_evaluator():
    try:
        from actions._evaluator import get_evaluator
        return get_evaluator()
    except Exception:
        return None


def _get_episodic_memory():
    try:
        from memory.episodic_memory import get_memory
        return get_memory()
    except Exception:
        return None


def _get_memory_meta():
    try:
        from memory.memory_manager import get_memory_meta
        return get_memory_meta()
    except Exception:
        return {}


def _gather_error_snippets(tool_name: str, limit: int = 10) -> list[str]:
    ev = _get_evaluator()
    if ev is None:
        return []
    try:
        s = ev.get_tool_stats(tool_name)
    except Exception:
        return []
    out: list[str] = []
    for r in (s.get("last_results", []) if isinstance(s, dict) else []) or []:
        try:
            if not isinstance(r, dict):
                continue
            if int(r.get("score", 10)) < 5:
                sn = str(r.get("snippet", ""))[:180]
                if sn:
                    out.append(sn)
        except Exception:
            continue
    # Also include last_errors from low_performers list (backup path)
    try:
        poor = ev.get_low_performers(min_calls=1, threshold=10.0)
        for p in poor:
            if p.get("tool") != tool_name:
                continue
            for e in p.get("last_errors", []) or []:
                if isinstance(e, dict):
                    sn = str(e.get("snippet", ""))[:180]
                    if sn and sn not in out:
                        out.append(sn)
    except Exception:
        pass
    return out[:limit]


# ────────────────────────────────────────────────────────────────────
# Failure classification + proposals
# ────────────────────────────────────────────────────────────────────
def _classify_failure(snippets: list[str]) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    if not snippets:
        return {}
    patterns: dict[str, list[str]] = {
        "missing_dependency": [
            r"no module named", r"modulenotfound", r"importerror",
            r"faltan? dependencias?", r"falta el modulo", r"no disponible: falta",
            r"dll load failed", r"cannot import",
        ],
        "api_auth": [
            r"payment required", r"402", r"401", r"403", r"sin api", r"api key",
            r"unauthorized", r"forbidden", r"no hay conexion", r"autenticacion fallida",
            r"facturacion", r"billing", r"quota excedida", r"rate limit",
        ],
        "screen_ocr": [
            r"no se detecto texto", r"no encontre.*pantalla", r"no pude conectar.*pantalla",
            r"no encontre.*en la pantalla", r"ocr.*fallo", r"ocr.*no detect",
            r"vision guardian",
        ],
        "app_not_found": [
            r"no encontre ninguna aplicacion", r"no encontre.*ventana",
            r"no encontre.*proceso", r"no existe.*aplicacion", r"no encontrado",
            r"no such process", r"process not found", r"window not found",
        ],
        "python_runtime": [
            r"attributeerror", r"typeerror", r"keyerror", r"indexerror",
            r"valueerror", r"traceback", r"exception:", r"runtimeerror",
            r"nonetype", r"unboundlocalerror", r"nameerror", r"zerodivision",
        ],
        "timeout": [
            r"timeout", r"timed out", r"se acabo el tiempo", r"operation too slow",
            r"deadline exceeded",
        ],
        "network": [
            r"connection refused", r"connection reset", r"network unreachable",
            r"dns failure", r"no route to host", r"temporary failure", r"ssl error",
            r"winerror 100",
        ],
        "permission": [
            r"access denied", r"permiso denegado", r"permission denied",
            r"unable to write", r"no puedo escribir", r"read-only",
        ],
    }
    for s in snippets:
        s_low = _strip_accents(str(s).lower())
        matched: set[str] = set()
        for bucket, pats in patterns.items():
            for p in pats:
                try:
                    if re.search(p, s_low):
                        matched.add(bucket)
                        break
                except re.error:
                    continue
        if matched:
            for b in matched:
                buckets[b] += 1
        else:
            buckets["unknown"] += 1
    return dict(buckets)


def _propose_actions(tool_name: str, failures: dict[str, int]) -> list[dict]:
    proposals: list[dict] = []
    ordered = sorted(failures.items(), key=lambda kv: -kv[1])
    for cls, count in ordered:
        if count <= 0:
            continue
        if cls == "missing_dependency":
            proposals.append({
                "type": "install_dependency",
                "tool": tool_name,
                "priority": 1,
                "count": count,
                "action": "Revisar imports del modulo actions/" + tool_name + ".py e instalar dependencias faltantes con pip.",
                "auto": True,
            })
        elif cls == "api_auth":
            proposals.append({
                "type": "configuration",
                "tool": tool_name,
                "priority": 1,
                "count": count,
                "action": "Revisar API keys, cuotas/facturacion y conectividad de red para esta herramienta.",
                "auto": False,
            })
        elif cls == "screen_ocr":
            proposals.append({
                "type": "workflow_improvement",
                "tool": tool_name,
                "priority": 2,
                "count": count,
                "action": "Warmup OCR engine al iniciar; usar PyWinAuto UI tree fallback; activar Vision Guardian.",
                "auto": True,
            })
        elif cls == "app_not_found":
            proposals.append({
                "type": "rule_improvement",
                "tool": tool_name,
                "priority": 2,
                "count": count,
                "action": "Agregar aliases de procesos en config/rules.json y fuzzy match de nombres.",
                "auto": True,
            })
        elif cls == "python_runtime":
            proposals.append({
                "type": "code_review",
                "tool": tool_name,
                "priority": 2,
                "count": count,
                "action": "Agregar try/except defensivo, None checks y retornos por defecto en actions/" + tool_name + ".",
                "auto": True,
            })
        elif cls == "timeout":
            proposals.append({
                "type": "resilience",
                "tool": tool_name,
                "priority": 2,
                "count": count,
                "action": "Retry exponential backoff (1s/2s/4s) + timeout extendido (>=15s).",
                "auto": True,
            })
        elif cls == "network":
            proposals.append({
                "type": "resilience",
                "tool": tool_name,
                "priority": 2,
                "count": count,
                "action": "Retry backoff + fallback offline; validar conectividad antes de invocar herramienta.",
                "auto": True,
            })
        elif cls == "permission":
            proposals.append({
                "type": "configuration",
                "tool": tool_name,
                "priority": 2,
                "count": count,
                "action": "Revisar permisos de archivos/carpetas y permisos UAC en Windows.",
                "auto": False,
            })
        else:
            proposals.append({
                "type": "investigate",
                "tool": tool_name,
                "priority": 3,
                "count": count,
                "action": "Revision manual de los snippets de error recientes requerida.",
                "auto": False,
            })
    return proposals


# ────────────────────────────────────────────────────────────────────
# Learning materialization
# ────────────────────────────────────────────────────────────────────
def _remedy_hint(tool_name: str, cls: str) -> str:
    hints: dict[str, str] = {
        "screen_ocr": (
            f"Optimizacion recomendada para {tool_name}: "
            "Warmup del motor OCR al iniciar. Intentar PyWinAuto UI automation antes de OCR. "
            "Preferir clicks via native_ui cuando sea posible."
        ),
        "python_runtime": (
            f"Revision de {tool_name}: Encapsular todos los calls en bloques try/except "
            "retornando string seguro. Agregar None checks en los valores retornados de modulos importados."
        ),
        "timeout": (
            f"Para {tool_name}: Retry con exponential backoff (1s, 2s, 4s). "
            "Limitar espera maxima a 15s. Retornar resultado parcial si hay timeout."
        ),
        "app_not_found": (
            f"Para {tool_name}: Fuzzy matching de nombres contra lista de procesos. "
            "Probar aliases comunes (word -> WINWORD.EXE, chrome -> chrome.exe)."
        ),
        "missing_dependency": (
            f"Para {tool_name}: Verificar bloque try/except ImportError al importar. "
            "Agregar modulo a requirements.txt o instalar via pip."
        ),
        "network": (
            f"Para {tool_name}: Verificar internet antes; retry 2 veces con backoff; "
            "retornar modo offline si no hay conectividad."
        ),
        "resilience": (
            f"Para {tool_name}: Aplicar circuit breaker pre-check (via evaluator.allow). "
            "Si el circuito esta OPEN, devolver fallback inmediato."
        ),
        "code_review": (
            f"Revision de {tool_name}: Agregar validacion de parametros de entrada, "
            "tipos consistentes y logging antes de retornos."
        ),
        "rule_improvement": (
            f"Para {tool_name}: Añadir regla en config/rules.json con phrase/trigger "
            "y fallback apropiado."
        ),
        "workflow_improvement": (
            f"Para {tool_name}: Cambiar el orden del flujo. Primero validar precondiciones, "
            "luego ejecutar accion, finalmente validar el resultado."
        ),
    }
    if cls in hints:
        return hints[cls]
    return ""


def _apply_learning(tool_name: str, failure_class: str, count: int,
                    strategy: str = "balanced") -> str:
    """Materialize a learning into memory/rules engine. Returns human summary."""
    key = hashlib.md5(f"{tool_name}::{failure_class}".encode()).hexdigest()[:8]
    when = datetime.now().isoformat(timespec="seconds")
    mem_key = f"{tool_name}_{failure_class}_{key}"
    summary_parts: list[str] = []

    # 1. Rules auto-generation for certain classes (strategy permitting)
    if strategy in ("balanced", "aggressive") and failure_class in (
        "api_auth", "missing_dependency", "permission",
    ):
        rules = _load_rules()
        rule_phrase = f"fallback {tool_name}"
        already = any(isinstance(r, dict) and r.get("phrase") == rule_phrase for r in rules)
        if not already and len(rules) < _MAX_RULES_AUTO:
            rules.append({
                "id": f"evo_{int(time.time())}_{key}",
                "phrase": rule_phrase,
                "action": {
                    "type": "memory_store",
                    "category": "corrections",
                    "key": f"fix_{tool_name}_{failure_class}",
                    "value": _remedy_hint(tool_name, failure_class),
                },
                "note": (f"Auto-generada por evolve.py [{strategy}] el {when}. "
                         f"{tool_name} tuvo {count} fallos clase='{failure_class}'."),
                "source": "evolve",
                "created_at": when,
            })
            _save_rules(rules)
            summary_parts.append(f"regla añadida='{rule_phrase}'")
        else:
            summary_parts.append("regla ya existente / limite alcanzado")

    # 2. Memory learning entry
    learning_value = (
        f"TOOL={tool_name} | FAILURE={failure_class} | COUNT={count} | "
        f"STRATEGY={strategy} | WHEN={when} | "
        f"REMEDY=Ver propuestas de evolve.analyze_system() para esta herramienta."
    )
    ok_mem = _remember_learning("learnings", mem_key, learning_value, ttl_days=180)
    summary_parts.append(f"aprendizaje guardado={'OK' if ok_mem else 'SKIP'} (learnings/{mem_key})")

    # 3. Correction hint memory entry (when we have concrete advice)
    hint = _remedy_hint(tool_name, failure_class)
    if hint:
        ck = f"fix_{tool_name}_{failure_class}"
        ok_corr = _remember_learning("corrections", ck, hint, ttl_days=270)
        summary_parts.append(f"correccion={'OK' if ok_corr else 'SKIP'} (corrections/{ck})")

    return f"[evo] {tool_name} ({failure_class} x{count}): " + "; ".join(summary_parts)


# ────────────────────────────────────────────────────────────────────
# Public evolution engine
# ────────────────────────────────────────────────────────────────────
def analyze_system() -> dict:
    """Run full diagnostic and return structured report."""
    ev = _get_evaluator()
    em = _get_episodic_memory()
    mm_meta = _get_memory_meta()

    if ev is not None:
        stats = ev.all_stats() or {"total_calls": 0, "tools": {}}
        low = ev.get_low_performers(min_calls=3) or []
        high = ev.get_high_performers(min_calls=5) or []
        circuits = ev.all_circuit_states() or {}
    else:
        stats = {"total_calls": 0, "tools": {}}
        low = []
        high = []
        circuits = {}

    detail: list[dict] = []
    open_count = 0
    for tool in low:
        try:
            tn = tool.get("tool", "")
            snippets = _gather_error_snippets(tn, limit=8)
            failures = _classify_failure(snippets)
            proposals = _propose_actions(tn, failures)
            record = {
                "tool": tn,
                "score": round(float(tool.get("avg_score", 0.0)), 2),
                "calls": int(tool.get("calls", 0)),
                "failures": int(tool.get("failures", 0)),
                "regressions": int(tool.get("regressions", 0)),
                "circuit": str(tool.get("circuit", "CLOSED")),
                "failure_classes": failures,
                "error_snippets": snippets[:5],
                "proposals": proposals,
            }
            detail.append(record)
            if str(tool.get("circuit", "CLOSED")) == "OPEN":
                open_count += 1
        except Exception:
            continue

    em_stats = em.get_stats() if em else {}
    kpis = {
        "total_tool_calls": int(stats.get("total_calls", 0)),
        "success_rate": float(stats.get("success_rate_est", 0.0)) if stats.get("success_rate_est") is not None else 0.0,
        "low_performers_count": len(detail),
        "high_performers_count": len(high),
        "circuits_open": open_count,
        "circuits_total": len(circuits),
        "episodic_total": int(em_stats.get("total_episodes", 0)) if isinstance(em_stats.get("total_episodes"), int) else 0,
        "episodic_avg_score_30d": float(em_stats.get("avg_success_score_30d", 0.0) or 0.0),
        "episodic_fts": bool(em_stats.get("fts_enabled", False)),
        "memory_entries": int(mm_meta.get("entries_total", 0) or 0),
        "memory_hits": int(mm_meta.get("hits_total", 0) or 0),
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "kpis": kpis,
        "low_performers": detail,
        "high_performers": high[:10],
        "circuits": circuits,
    }


def improve_tool(tool_name: str, strategy: str = "balanced") -> str:
    """Generate + apply improvement actions for a specific tool.
    strategy: 'safe' (aprendizajes solo, sin reglas), 'balanced' (default), 'aggressive' (todo)."""
    if not tool_name:
        return "[evo] improve_tool requiere nombre de herramienta."
    ev = _get_evaluator()
    if ev is None:
        return "[evo] Sistema de telemetria no disponible. No se puede mejorar herramienta."

    snippets = _gather_error_snippets(tool_name, limit=12)
    ts: dict = {}
    try:
        ts = ev.get_tool_stats(tool_name) or {}
    except Exception:
        ts = {}

    if not snippets and int(ts.get("calls", 0)) == 0:
        return (f"[evo] {tool_name}: No se detectaron fallos ni llamadas historicas. "
                f"No hay informacion para mejorar.")

    if not snippets and int(ts.get("calls", 0)) > 0:
        # Tool was called but no failures: mark as reference
        return (f"[evo] {tool_name}: Rendimiento OK. "
                f"Estadisticas: calls={ts.get('calls')}, avg_score={ts.get('avg_score')}, "
                f"ema={ts.get('ema_score')}, circuit={ts.get('circuit', {}).get('state') if isinstance(ts.get('circuit'), dict) else ts.get('circuit')}.")

    failures = _classify_failure(snippets)
    proposals = _propose_actions(tool_name, failures)
    applied: list[str] = []

    if strategy == "safe":
        for cls, count in failures.items():
            applied.append(_apply_learning(tool_name, cls, count, strategy="safe"))
    else:
        for cls, count in failures.items():
            applied.append(_apply_learning(tool_name, cls, count, strategy=strategy))
        for p in proposals:
            auto_ok = bool(p.get("auto"))
            if strategy == "aggressive" or auto_ok:
                hint = _remedy_hint(tool_name, p.get("type", ""))
                if hint:
                    proposal_key = f"proposal_{tool_name}_{p['type']}_{int(time.time())}"
                    combined = f"{p.get('action','')} | DETAIL: {hint}"
                    ok = _remember_learning("learnings", proposal_key, combined, ttl_days=120)
                    if ok:
                        applied.append(f"[evo] Propuesta guardada: {str(p.get('action',''))[:120]}")

    # Persist evolution journal
    with _evo_lock:
        data = _load_evolution()
        data["runs"] = int(data.get("runs", 0)) + 1
        data["last_run"] = datetime.now().isoformat(timespec="seconds")
        data["improvements"].append({
            "tool": tool_name,
            "strategy": strategy,
            "at": data["last_run"],
            "applied": [str(a)[:200] for a in applied[-10:]],
            "failures": failures,
            "proposals": [
                {k: v for k, v in p.items() if k != "action"}  # compact
                for p in proposals[:8]
            ],
        })
        # keep bounded
        if len(data["improvements"]) > 200:
            data["improvements"] = data["improvements"][-200:]

        # Update KPI snapshot
        try:
            kpis = analyze_system().get("kpis", {})
            data["kpis"] = kpis
        except Exception:
            pass
        data["learnings_stored"] = int(data.get("learnings_stored", 0)) + max(1, len(applied))
        data["rules_added"] = int(data.get("rules_added", 0)) + sum(
            1 for a in applied if "regla añadida" in a
        )
        _save_evolution(data)

    if not applied:
        return f"[evo] {tool_name}: Analisis completado; sin acciones requeridas."
    return "\n".join(applied[-12:])


def auto_improve(min_calls: int = 3, threshold: float = 5.2,
                 strategy: str = "balanced", max_tools: int = 5) -> str:
    """Detect low performers and improve them in a loop."""
    ev = _get_evaluator()
    if ev is None:
        return "[evo] Sistema de telemetria no disponible. No se puede ejecutar auto_improve."
    try:
        poor = ev.get_low_performers(min_calls=min_calls, threshold=threshold) or []
    except Exception as e:
        return f"[evo] Error al consultar low performers: {e}"
    if not poor:
        return "[evo] Todas las herramientas cumplen umbral de rendimiento. Nada que mejorar."

    results: list[str] = []
    # Priorizar: circuits OPEN primero, luego peor score
    def _sort_key(p):
        return (
            0 if str(p.get("circuit", "")) == "OPEN" else 1,
            float(p.get("avg_score", 999.0)),
        )
    poor_sorted = sorted(poor, key=_sort_key)[:max(1, int(max_tools))]
    for p in poor_sorted:
        tool = str(p.get("tool", "")).strip()
        if not tool:
            continue
        try:
            r = improve_tool(tool, strategy=strategy)
        except Exception as e:
            r = f"[evo] {tool}: fallo improve_tool ({type(e).__name__}: {e})"
        results.append(r)

    head = (
        f"[evo] Auto-improve finalizado. "
        f"Herramientas procesadas={len(results)}, estrategia={strategy}, "
        f"umbral={threshold}, min_calls={min_calls}."
    )
    return head + "\n\n" + "\n\n".join(results)


def get_evolution_report() -> str:
    with _evo_lock:
        data = _load_evolution()
    system = analyze_system()
    lines: list[str] = []
    lines.append("=== EVOLUCION AUTONOMA DEL SISTEMA ONYX ===")
    lines.append(f"Schema v{data.get('_version','?')} | Runs: {data.get('runs',0)} | "
                 f"Last run: {data.get('last_run') or 'never'}")
    k = system.get("kpis", {})
    lines.append("KPIs actuales:")
    for kk, vv in k.items():
        lines.append(f"  • {kk}: {vv}")
    lines.append(f"Reglas auto-añadidas: {data.get('rules_added', 0)}")
    lines.append(f"Aprendizajes almacenados: {data.get('learnings_stored', 0)}")
    lines.append(f"Historial v1 migrado entradas: {len(data.get('history', []))}")
    low = system.get("low_performers", [])
    if low:
        lines.append(f"\n--- MEJORAS PENDIENTES ({len(low)}) ---")
        for item in low[:8]:
            lines.append(
                f"- {item['tool']} (score={item['score']}, circuit={item['circuit']}, "
                f"classes={item.get('failure_classes', {})}, calls={item['calls']})"
            )
    high = system.get("high_performers", [])
    if high:
        lines.append("\n--- REFERENCIAS TOP ---")
        for item in high[:5]:
            lines.append(
                f"- {item['tool']} (score={round(float(item['avg_score']),2)}, "
                f"exitos={item.get('successes')}/{item.get('calls')})"
            )
    last_improve = (data.get("improvements") or [])[-3:]
    if last_improve:
        lines.append("\n--- ULTIMAS 3 MEJORAS APLICADAS ---")
        for imp in last_improve:
            tool = imp.get("tool", "?")
            strat = imp.get("strategy", "?")
            when = imp.get("at", "")
            app = imp.get("applied") or []
            lines.append(f"- [{when}] {tool} (estrategia={strat}) -> {len(app)} acciones")
            for a in app[-2:]:
                lines.append(f"    • {str(a)[:140]}")
    return "\n".join(lines)


def _self_review_improve(tool: str, strategy: str = "balanced") -> str:
    """Back-compat alias used from main.py evolve_from_telemetry."""
    return improve_tool(str(tool or "").strip(), strategy=strategy)


# ────────────────────────────────────────────────────────────────────
# Tool-compatible entrypoint (matches actions/*.py signatures)
# ────────────────────────────────────────────────────────────────────
def evolve(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    action = (str(parameters.get("action") or parameters.get("mode") or "analyze")).lower()
    target = (str(parameters.get("target") or parameters.get("tool") or "")).strip()
    strategy = (str(parameters.get("strategy") or "balanced")).lower()
    try:
        min_calls = int(parameters.get("min_calls", 3))
    except Exception:
        min_calls = 3
    try:
        threshold = float(parameters.get("threshold", 5.0))
    except Exception:
        threshold = 5.0
    try:
        max_tools = int(parameters.get("max_tools", 5))
    except Exception:
        max_tools = 5

    if action in ("analyze", "diagnostico", "diagnostic", "status", "info"):
        if target:
            ev = _get_evaluator()
            if ev is None:
                return "Telemetria no disponible."
            try:
                stats = ev.get_tool_stats(target) or {}
            except Exception as e:
                return f"Error al consultar stats: {e}"
            # Enrich with failure classification + proposals
            snippets = _gather_error_snippets(target, limit=8)
            failures = _classify_failure(snippets)
            proposals = _propose_actions(target, failures)
            report = {
                "stats": stats,
                "failure_classes": failures,
                "proposals": proposals,
                "error_snippets": snippets[:5],
            }
            return json.dumps(report, ensure_ascii=False, indent=1, default=str)
        return json.dumps(analyze_system(), ensure_ascii=False, indent=1, default=str)

    if action in ("improve", "mejorar", "fix", "corregir"):
        if target:
            return improve_tool(target, strategy=strategy)
        return auto_improve(
            min_calls=min_calls, threshold=threshold,
            strategy=strategy, max_tools=max_tools,
        )

    if action in ("report", "reporte", "kpi", "kpis", "resumen"):
        return get_evolution_report()

    if action in ("refactor", "refactorizar"):
        report = analyze_system()
        out: list[str] = []
        for item in (report.get("low_performers") or [])[:3]:
            for p in (item.get("proposals") or [])[:2]:
                key = f"refactor_{item['tool']}_{p['type']}_{int(time.time())}"
                value = str(p.get("action", ""))
                ok = _remember_learning("learnings", key, value, ttl_days=150)
                suffix = " OK" if ok else " SKIP"
                out.append(f"[refactor{suffix}] {item['tool']}/{p['type']}: {value[:160]}")
        if not out:
            return "[evo refactor] Nada para refactorizar en este momento."
        return "\n".join(out)

    if action in ("learn", "aprender", "training", "entrenar"):
        if target:
            return improve_tool(target, strategy="safe")
        return auto_improve(
            min_calls=min_calls, threshold=threshold, strategy="safe", max_tools=max_tools
        )

    return (
        "=== evolve: acciones disponibles ===\n"
        "  • analyze [target=nombre_tool] -> diagnostico completo o por herramienta\n"
        "  • improve [target=nombre_tool] [strategy=safe|balanced|aggressive] "
        "[min_calls=3] [threshold=5.0] [max_tools=5] -> auto-mejora\n"
        "  • refactor -> guarda propuestas de refactor en memoria learnings\n"
        "  • report -> informe humano con KPIs y evolucion historica\n"
        "  • learn -> modo conservador (solo aprendizajes, sin reglas auto)."
    )
