"""
rules_engine.py — Gestión y ejecución de reglas adaptativas (v2).

Reglas: list[dict] con campos:
  - id, phrase (string a buscar en input usuario), regex (opcional)
  - action: { type: memory_store | memory_update | speak_note | log_note | apply_correction | remember }
  - priority (int, menor = más prioritario), note, source, active=True/False

Compatibilidad con reglas antiguas (sin type explícito): se normaliza a memory_store por defecto.
"""
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
RULES_PATH = CONFIG_DIR / "rules.json"
LOG_PATH = BASE_DIR / "memory" / "rules_triggered.log"

_lock = threading.RLock()
_rules_cache: list[dict] | None = None
_cache_loaded_at: float = 0.0
_CACHE_TTL_SEC = 10


def load_rules() -> list[dict]:
    """Carga reglas desde disco con normalización de esquema. Cache interno 10s."""
    global _rules_cache, _cache_loaded_at
    now = time.time()
    with _lock:
        if _rules_cache is not None and (now - _cache_loaded_at) < _CACHE_TTL_SEC:
            return [dict(r) for r in _rules_cache]
        rules: list[dict] = []
        if RULES_PATH.exists():
            try:
                raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("rules"), list):
                    rules = list(raw["rules"])
                elif isinstance(raw, list):
                    rules = list(raw)
            except Exception:
                rules = []
        # Normalize
        normalized: list[dict] = []
        for r in rules:
            if not isinstance(r, dict):
                continue
            r2 = dict(r)
            if "id" not in r2 or not r2["id"]:
                r2["id"] = f"rule_{abs(hash(str(r2.get('phrase','')))) & 0xFFFFF}"
            if "active" not in r2:
                r2["active"] = True
            if "priority" not in r2:
                r2["priority"] = 5
            if "phrase" not in r2:
                r2["phrase"] = ""
            action = r2.get("action")
            if not isinstance(action, dict):
                # Legacy shape: wrap action into memory_store of itself
                action = {"type": "memory_store",
                          "category": "corrections",
                          "key": f"legacy_{r2['id']}",
                          "value": str(action or r2.get("note", ""))}
                r2["action"] = action
            if "type" not in action:
                action["type"] = "memory_store"
            normalized.append(r2)
        _rules_cache = normalized
        _cache_loaded_at = now
        return [dict(r) for r in normalized]


def save_rules(rules: list[dict]) -> bool:
    global _rules_cache, _cache_loaded_at
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        RULES_PATH.write_text(
            json.dumps({"rules": list(rules)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with _lock:
            _rules_cache = [dict(r) for r in rules]
            _cache_loaded_at = time.time()
        return True
    except Exception:
        return False


def list_rules(search: str = "", include_inactive: bool = False) -> str:
    """Lista reglas en formato legible (herramienta rules_engine action=list)."""
    rules = load_rules()
    out_lines: list[str] = []
    q = (search or "").strip().lower()
    count = 0
    for r in sorted(rules, key=lambda x: (int(x.get("priority", 5)), str(x.get("phrase", "")))):
        if not bool(r.get("active", True)) and not include_inactive:
            continue
        phrase = str(r.get("phrase", "")).lower()
        note = str(r.get("note", "")).lower()
        if q and q not in phrase and q not in note:
            continue
        count += 1
        snippet = {
            "id": r.get("id"),
            "priority": r.get("priority", 5),
            "phrase": r.get("phrase"),
            "type": r.get("action", {}).get("type"),
            "source": r.get("source", ""),
            "active": r.get("active", True),
            "note": (str(r.get("note", ""))[:80] + ("..." if len(str(r.get("note",""))) > 80 else "")),
        }
        out_lines.append(f"- {snippet['id']} [p{snippet['priority']}] '{snippet['phrase']}' -> {snippet['type']} ({snippet['source'] or 'manual'}) active={snippet['active']}")
        if snippet["note"]:
            out_lines.append(f"    note: {snippet['note']}")
    if count == 0:
        return "Sin reglas coincidentes."
    return f"Reglas ({count}):\n" + "\n".join(out_lines)


def add_rule(phrase: str, action: dict | None = None, note: str = "",
             priority: int = 5, source: str = "manual") -> str:
    phrase = (phrase or "").strip()
    if not phrase:
        return "Frase requerida para crear regla."
    action = action or {"type": "log_note", "message": note or phrase}
    rules = load_rules()
    new_rule = {
        "id": f"r_{int(time.time())}_{abs(hash(phrase)) & 0xFFFFF}",
        "phrase": phrase,
        "action": action,
        "note": note,
        "priority": int(priority),
        "source": source,
        "active": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    rules.append(new_rule)
    save_rules(rules)
    return f"Regla creada: {new_rule['id']} ({phrase} -> {action.get('type')})"


def delete_rule(rule_id: str) -> str:
    rule_id = (rule_id or "").strip()
    if not rule_id:
        return "rule_id requerido."
    rules = load_rules()
    new_rules = [r for r in rules if str(r.get("id")) != rule_id]
    if len(new_rules) == len(rules):
        return f"No encontre regla con id '{rule_id}'."
    save_rules(new_rules)
    return f"Regla eliminada: {rule_id}."


def enable_rule(rule_id: str, active: bool = True) -> str:
    rules = load_rules()
    for r in rules:
        if str(r.get("id")) == rule_id:
            r["active"] = bool(active)
            save_rules(rules)
            return f"Regla {rule_id}: active={bool(active)}."
    return f"No encontre regla con id '{rule_id}'."


def _run_action(action: dict, match_text: str,
                speak_callback=None) -> tuple[bool, str]:
    """Execute a rule action. Returns (success, description)."""
    if not isinstance(action, dict):
        return False, "accion invalida"
    atype = str(action.get("type", "")).lower() or "log_note"

    if atype in ("memory_store", "memory_save", "remember", "learning", "store"):
        category = str(action.get("category") or action.get("type2") or "corrections")
        key = str(action.get("key") or f"triggered_{int(time.time()*1000)}")
        value = str(action.get("value") or match_text or "")
        if not value:
            value = match_text
        try:
            from memory.memory_manager import remember
            remember(category, key, value, ttl_days=int(action.get("ttl_days", 0) or 180))
            return True, f"memory_store OK: {category}/{key}"
        except Exception as e:
            return False, f"memory_store fallo ({e})"

    if atype in ("memory_update", "update_memory"):
        updates = action.get("updates") or action.get("value") or {}
        try:
            from memory.memory_manager import update_memory
            if isinstance(updates, dict):
                update_memory(updates)
                return True, f"update_memory OK ({len(updates)} keys)"
            return False, "update_memory requiere dict updates"
        except Exception as e:
            return False, f"update_memory fallo ({e})"

    if atype in ("apply_correction", "correction"):
        # Fetch correction from memory (by key) and return it as note
        ck = str(action.get("key") or "")
        try:
            from memory.memory_manager import recall
            val = recall("corrections", ck) if ck else None
            text = val or str(action.get("value") or match_text or "")
            if speak_callback and text:
                try: speak_callback(text)
                except Exception: pass
            return True, f"apply_correction: {text[:120]}"
        except Exception as e:
            return False, f"apply_correction fallo ({e})"

    if atype in ("speak_note", "speak", "say"):
        text = str(action.get("message") or action.get("value") or match_text or "")
        if speak_callback and text:
            try: speak_callback(text)
            except Exception: pass
        return True, f"speak_note: {text[:100]}"

    if atype in ("log_note", "log", "note"):
        text = str(action.get("message") or action.get("value") or match_text or "")
        try:
            import os
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} | {match_text[:120]!r} | {text[:200]}\n")
        except Exception:
            pass
        return True, f"log_note: {text[:100]}"

    if atype in ("trigger_evolve", "auto_improve"):
        try:
            from actions.evolve import auto_improve
            min_c = int(action.get("min_calls", 3))
            thr = float(action.get("threshold", 5.0))
            strat = str(action.get("strategy", "balanced"))
            summary = auto_improve(min_calls=min_c, threshold=thr, strategy=strat)
            return True, f"trigger_evolve OK: {str(summary)[:150]}"
        except Exception as e:
            return False, f"trigger_evolve fallo ({e})"

    return False, f"tipo accion desconocido: {atype}"


def check_phrase_triggers(text: str, speak_callback=None,
                          limit: int = 5) -> list[dict]:
    """Busca reglas que matcheen el texto del usuario y ejecuta sus acciones.
    Devuelve lista de {rule_id, phrase, matched, action_type, success, description}.
    """
    text = str(text or "")
    if not text:
        return []
    results: list[dict] = []
    rules = load_rules()
    rules_sorted = sorted(
        [r for r in rules if r.get("active", True)],
        key=lambda r: int(r.get("priority", 5))
    )
    for r in rules_sorted:
        if len(results) >= int(limit):
            break
        phrase = str(r.get("phrase", "")).strip().lower()
        regex = str(r.get("regex") or "").strip()
        matched = False
        matched_text = ""
        if regex:
            try:
                m = re.search(regex, text, re.IGNORECASE)
                if m:
                    matched = True
                    matched_text = m.group(0)
            except re.error:
                matched = False
        if not matched and phrase:
            if phrase in text.lower():
                matched = True
                matched_text = phrase
        if not matched:
            continue
        ok, desc = _run_action(r.get("action") or {}, text, speak_callback=speak_callback)
        results.append({
            "rule_id": r.get("id"),
            "phrase": r.get("phrase"),
            "regex": regex or None,
            "matched": matched_text,
            "action_type": (r.get("action") or {}).get("type"),
            "success": bool(ok),
            "description": desc,
            "priority": int(r.get("priority", 5)),
            "source": r.get("source", "manual"),
        })
    return results


# ────────────────────────────────────────────────────────────────────
# Tool-compatible entrypoint
# ────────────────────────────────────────────────────────────────────
def rules_engine(parameters: dict | None = None, player=None, speak=None) -> str:
    parameters = parameters or {}
    action = str(parameters.get("action") or "list").lower()
    if action in ("list", "lista", "mostrar", "get", "buscar"):
        return list_rules(
            search=str(parameters.get("search") or parameters.get("phrase") or ""),
            include_inactive=bool(parameters.get("include_inactive")),
        )
    if action in ("add", "crear", "agregar", "nuevo"):
        return add_rule(
            phrase=str(parameters.get("phrase") or parameters.get("trigger") or ""),
            action=parameters.get("action_body") or parameters.get("rule_action"),
            note=str(parameters.get("note") or ""),
            priority=int(parameters.get("priority", 5)),
            source=str(parameters.get("source") or "manual"),
        )
    if action in ("delete", "eliminar", "borrar", "remove"):
        return delete_rule(str(parameters.get("rule_id") or parameters.get("id") or ""))
    if action in ("enable", "habilitar", "activar"):
        return enable_rule(str(parameters.get("rule_id") or parameters.get("id") or ""), True)
    if action in ("disable", "deshabilitar", "desactivar"):
        return enable_rule(str(parameters.get("rule_id") or parameters.get("id") or ""), False)
    if action in ("check", "ejecutar", "run", "match", "validar"):
        results = check_phrase_triggers(
            str(parameters.get("text") or parameters.get("input") or ""),
            speak_callback=speak,
            limit=int(parameters.get("limit", 5)),
        )
        if not results:
            return "Sin reglas coincidentes para el texto."
        lines = [f"Disparadas {len(results)} reglas:"]
        for r in results:
            lines.append(f"  ✓ [{r['rule_id']}] matched={r['matched']!r} "
                         f"-> {r['action_type']} ok={r['success']} | {r['description'][:120]}")
        return "\n".join(lines)
    return (
        "Acciones rules_engine:\n"
        "  • list [search=palabra] [include_inactive=false]\n"
        "  • add phrase= trigger [note=...] [priority=5] [rule_action={dict}]\n"
        "  • delete rule_id=...\n"
        "  • enable/disable rule_id=...\n"
        "  • check text=... [limit=5] -> prueba reglas sobre el texto."
    )
