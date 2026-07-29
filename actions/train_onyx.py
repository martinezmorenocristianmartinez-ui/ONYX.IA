import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
TRAINING_LOG = BASE_DIR / "memory" / "training_log.json"


def _log_training(topic: str, content: str, mode: str):
    """Log training entries for traceability."""
    if not TRAINING_LOG.exists():
        TRAINING_LOG.write_text(json.dumps([]), encoding="utf-8")
    try:
        log = json.loads(TRAINING_LOG.read_text(encoding="utf-8"))
    except Exception:
        log = []
    log.append({"topic": topic, "content": content, "mode": mode})
    TRAINING_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")


def _add_prompt_rule(rule: str) -> str:
    """Add a behavioral rule to the end of the system prompt."""
    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        tag = "## REGLAS ENTRENADAS"
        section = f"\n\n{tag}\nReglas aprendidas:\n- {rule}\n"
        if tag in prompt:
            prompt = prompt.rstrip() + f"\n- {rule}\n"
        else:
            prompt = prompt.rstrip() + section
        PROMPT_PATH.write_text(prompt, encoding="utf-8")
        return f"Regla '{rule}' agregada al prompt del sistema."
    except Exception as e:
        return f"Error editando prompt: {e}"


def _store_knowledge(key: str, value: str) -> str:
    """Store a fact in knowledge_base."""
    try:
        from actions.knowledge_base import knowledge_base
        return knowledge_base({"action": "add", "key": key, "value": value})
    except Exception as e:
        return f"Error guardando conocimiento: {e}"


def _store_memory(category: str, key: str, value: str) -> str:
    """Store a memory entry (preference, habit, etc)."""
    try:
        from memory.memory_manager import remember
        remember(category, key, value)
        return f"Guardado en memoria ({category}): {key} = {value}"
    except Exception as e:
        return f"Error guardando memoria: {e}"


def _store_macro(name: str, steps: str) -> str:
    """Create a macro from steps."""
    try:
        from actions.macros_control import macros_control
        steps_list = [s.strip() for s in steps.split(",") if s.strip()]
        macro_steps = []
        for s in steps_list:
            macro_steps.append({"type": "key", "value": s.strip(), "delay": 0.3})
        return macros_control({"action": "create", "name": name, "steps": macro_steps})
    except Exception as e:
        return f"Error creando macro: {e}"


def train_onyx(parameters: dict, player=None) -> str:
    """
    Entrena a ONYX con información, preferencias o comportamientos.
    Modos disponibles:
    - fact: guarda un hecho/conocimiento (key + value).
    - preference: guarda una preferencia del usuario.
    - habit: guarda un hábito del usuario.
    - behavior: agrega una regla de comportamiento al prompt del sistema.
    - macro: crea una macro de automatización.
    - list: muestra todo lo entrenado hasta ahora.
    """
    mode = parameters.get("mode", "fact").lower().strip()
    topic = parameters.get("topic", "").strip()
    content = parameters.get("content", "").strip()
    key = parameters.get("key", topic)
    value = parameters.get("value", content)

    if mode == "list":
        lines = []
        if TRAINING_LOG.exists():
            try:
                log = json.loads(TRAINING_LOG.read_text(encoding="utf-8"))
                for entry in log[-20:]:
                    lines.append(f"  [{entry['mode']}] {entry['topic']}: {entry['content'][:100]}")
            except Exception:
                pass
        if not lines:
            return "No hay entrenamiento registrado aún, Señor Cristian."
        return "Últimos entrenamientos:\n" + "\n".join(lines)

    if not topic and not key:
        return "Necesito un 'topic' o 'key' para entrenar, Señor Cristian."

    if mode == "fact":
        result = _store_knowledge(key, value or content)

    elif mode == "preference":
        result = _store_memory("preferences", key, value or content)

    elif mode == "habit":
        result = _store_memory("habits", key, value or content)

    elif mode == "behavior":
        result = _add_prompt_rule(content or key)

    elif mode == "macro":
        steps = parameters.get("steps", value)
        result = _store_macro(key, steps)

    else:
        result = f"Modo '{mode}' no reconocido. Usá: fact, preference, habit, behavior, macro, list."

    _log_training(topic or key, content or value, mode)
    return f"Entrenado, Señor Cristian. {result}"
