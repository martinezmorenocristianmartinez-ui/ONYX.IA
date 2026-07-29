import json
import sys
import uuid
import threading
from pathlib import Path
from datetime import datetime

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
KB_PATH = BASE_DIR / "memory" / "knowledge_base.json"
_lock = threading.Lock()

def _load() -> list[dict]:
    with _lock:
        if not KB_PATH.exists():
            return []
        try:
            return json.loads(KB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []

def _save(entries: list[dict]) -> None:
    with _lock:
        KB_PATH.parent.mkdir(parents=True, exist_ok=True)
        KB_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _match(entry: dict, query: str) -> bool:
    q = query.lower()
    return (q in entry.get("title", "").lower()
            or q in entry.get("content", "").lower()
            or q in entry.get("tags", "").lower())

def knowledge_base(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    title = parameters.get("title", "").strip()
    content = parameters.get("content", "").strip()
    entry_type = parameters.get("type", "note").strip()
    tags = parameters.get("tags", "").strip()
    query = parameters.get("query", "").strip()
    entry_id = parameters.get("entry_id", "").strip()
    path = parameters.get("path", "").strip()

    add_actions = {"add", "save", "store"}
    search_actions = {"search", "find"}
    get_actions = {"get", "read", "view"}

    if action in add_actions:
        if not content:
            return "Error: Proporciona 'content' para guardar."
        entry = {
            "id": uuid.uuid4().hex[:8],
            "title": title or content.split("\n")[0][:60],
            "content": content,
            "type": entry_type if entry_type in ("note", "idea", "snippet", "reference", "fact", "task", "question") else "note",
            "tags": tags,
            "created": _now(),
            "updated": _now(),
        }
        entries = _load()
        entries.append(entry)
        _save(entries)
        return f"Guardado correctamente (ID: {entry['id']})."

    elif action in search_actions:
        if not query:
            return "Error: Proporciona 'query' para buscar."
        entries = _load()
        results = [e for e in entries if _match(e, query)]
        if not results:
            return f"No se encontraron resultados para '{query}'."
        lines = [f"Resultados para '{query}' ({len(results)}):"]
        for e in results[:50]:
            preview = e["content"][:500].replace("\n", " ")
            lines.append(f"\n  [{e['type']}] {e['title']} (ID: {e['id']})")
            lines.append(f"  {preview}{'...' if len(e['content']) > 500 else ''}")
            if e["tags"]:
                lines.append(f"  Tags: {e['tags']}")
        if len(results) > 50:
            lines.append(f"\n... y {len(results) - 50} más.")
        return "\n".join(lines)

    elif action == "list":
        entries = _load()
        if not entries:
            return "La base de conocimiento está vacía."
        counts = {}
        for e in entries:
            counts[e.get("type", "note")] = counts.get(e.get("type", "note"), 0) + 1
        type_summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        lines = [f"Base de conocimiento: {len(entries)} entradas ({type_summary})"]
        for e in entries[-50:]:
            lines.append(f"  [{e.get('type','general')}] {e['title']} ({e.get('updated','')})")
        if len(entries) > 500:
            lines.insert(1, f"  (mostrando últimas 50 de {len(entries)})")
        return "\n".join(lines)

    elif action in get_actions:
        entries = _load()
        if entry_id:
            match = [e for e in entries if e["id"] == entry_id]
        elif title:
            match = [e for e in entries if e["title"].lower() == title.lower()]
        else:
            return "Error: Proporciona 'entry_id' o 'title'."
        if not match:
            return "Entrada no encontrada."
        e = match[0]
        return (f"ID: {e['id']}\nTítulo: {e['title']}\nTipo: {e.get('type','note')}\n"
                f"Tags: {e.get('tags','')}\nCreado: {e.get('created','')}\nActualizado: {e.get('updated','')}\n\n{e['content']}")

    elif action == "update":
        if not entry_id:
            return "Error: Proporciona 'entry_id' para actualizar."
        entries = _load()
        for e in entries:
            if e["id"] == entry_id:
                if title:
                    e["title"] = title
                if content:
                    e["content"] = content
                if tags:
                    e["tags"] = tags
                if entry_type in ("note", "idea", "snippet", "reference", "fact", "task", "question"):
                    e["type"] = entry_type
                e["updated"] = _now()
                _save(entries)
                return f"Entrada {entry_id} actualizada."
        return f"Entrada {entry_id} no encontrada."

    elif action == "delete":
        if not entry_id:
            return "Error: Proporciona 'entry_id' para eliminar."
        entries = _load()
        new_entries = [e for e in entries if e["id"] != entry_id]
        if len(new_entries) == len(entries):
            return f"Entrada {entry_id} no encontrada."
        _save(new_entries)
        return f"Entrada {entry_id} eliminada."

    elif action == "stats":
        entries = _load()
        if not entries:
            return "Base de conocimiento vacía."
        total = len(entries)
        types = {}
        for e in entries:
            t = e.get("type", "note")
            types[t] = types.get(t, 0) + 1
        lines = [f"Base de conocimiento: {total} entradas"]
        for t, c in sorted(types.items(), key=lambda x: -x[1]):
            lines.append(f"  {t}: {c}")
        lines.append(f"  Última actualización: {entries[-1].get('updated', '')}")
        return "\n".join(lines)

    elif action == "export":
        entries = _load()
        if not entries:
            return "Base de conocimiento vacía, nada que exportar."
        export_path = Path(path) if path else BASE_DIR / "knowledge_export.json"
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
            return f"Exportado a {export_path} ({len(entries)} entradas)."
        except Exception as e:
            return f"Error exportando: {e}"

    else:
        return (f"Acción '{action}' no reconocida. Acciones: add, search, list, get, update, delete, stats, export.")
