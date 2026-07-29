import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
INDEX_PATH = BASE_DIR / "memory" / "codebase_index.json"

_SYMBOL_PATTERNS = [
    (r'^\s*(?:async\s+)?def\s+(\w+)\s*\(', "function"),
    (r'^\s*(?:async\s+)?def\s+(\w+)\s*\(', "function"),
    (r'^\s*class\s+(\w+)', "class"),
    (r'^\s*@(?:app|api|route|get|post|put|delete|patch)\.\w+', "decorator"),
    (r'^\s*(?:fn|const|let|var|function)\s+(\w+)\s*(?:[=\(]|\:\s*(?:function|\())', "function"),
    (r'^\s*(?:public|private|protected|static)?\s*(?:function|class|interface|trait|enum)\s+(\w+)', "function/class"),
    (r'^\s*(?:func|type|struct|interface|class)\s+(\w+)', "function/class"),
]

_EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript React",
    ".jsx": "JavaScript React", ".java": "Java", ".cpp": "C++", ".c": "C",
    ".h": "C/C++ Header", ".cs": "C#", ".go": "Go", ".rs": "Rust",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
    ".vue": "Vue", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell", ".bat": "Batch",
    ".yaml": "YAML", ".yml": "YAML", ".json": "JSON", ".xml": "XML",
    ".md": "Markdown", ".txt": "Text", ".toml": "TOML", ".ini": "INI",
}

_EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                 ".env", ".next", "dist", "build", ".idea", ".vscode",
                 ".vs", "bin", "obj", ".nx", ".yarn", ".pytest_cache",
                 ".mypy_cache", "target", "vendor"}

def _load_index() -> dict:
    if not INDEX_PATH.exists():
        return {}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_index(index: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

def _get_project_name(name: str, path: Path) -> str:
    return name or path.name

def _index_project(path: Path, name: str = "") -> str:
    if not path.exists():
        return f"Error: La ruta '{path}' no existe."
    project_name = _get_project_name(name, path)
    index = _load_index()

    files = []
    total_size = 0
    skipped = 0
    for root, dirs, fnames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS and not d.startswith(".")]
        for f in fnames:
            ext = Path(f).suffix.lower()
            if ext not in _EXT_LANG and ext not in (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".c", ".h", ".cs", ".go", ".rs"):
                skipped += 1
                continue
            fp = Path(root) / f
            try:
                size = fp.stat().st_size
                total_size += size
                rel = str(fp.relative_to(path))
                lang = _EXT_LANG.get(ext, "Unknown")
                symbols = _extract_symbols(fp)
                files.append({"path": rel, "language": lang, "size": size, "symbols": symbols})
            except:
                skipped += 1

    index[project_name] = {
        "root": str(path),
        "files": files,
        "file_count": len(files),
        "skipped": skipped,
        "total_size": total_size,
        "indexed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_index(index)
    return (f"Proyecto '{project_name}' indexado: {len(files)} archivos, "
            f"{skipped} omitidos, {total_size / 1024:.1f} KB total.")

def _extract_symbols(filepath: Path) -> list[dict]:
    symbols = []
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except:
        return symbols
    ext = filepath.suffix.lower()
    patterns = _SYMBOL_PATTERNS
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*", "--")):
            continue
        for pattern, kind in patterns:
            m = re.search(pattern, stripped)
            if m:
                name = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                symbols.append({"name": name, "kind": kind, "line": i})
                break
    return symbols

def _search_project(project: dict, query: str) -> list[dict]:
    results = []
    q = query.lower()
    for f in project.get("files", []):
        if q in f["path"].lower():
            results.append({"file": f["path"], "match": "filename", "line": 0})
            continue
        fp = Path(project["root"]) / f["path"]
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.split("\n"), 1):
                if q in line.lower():
                    results.append({"file": f["path"], "match": line.strip()[:150], "line": i})
                    if len(results) >= 30:
                        break
        except:
            pass
        if len(results) >= 30:
            break
    return results

def codebase(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    path_str = parameters.get("path", "")
    name = parameters.get("name", "").strip()
    project = parameters.get("project", "").strip()
    query = parameters.get("query", "").strip()
    symbol = parameters.get("symbol", "").strip()
    file_path = parameters.get("file_path", "").strip()

    if action == "index":
        if not path_str:
            return "Error: Proporciona 'path' al proyecto."
        p = Path(path_str).expanduser().resolve()
        return _index_project(p, name)

    elif action == "list":
        index = _load_index()
        if not index:
            return "No hay proyectos indexados. Usa action=index para indexar uno."
        lines = ["Proyectos indexados:"]
        for proj, data in sorted(index.items()):
            lines.append(f"  {proj}: {data.get('file_count', 0)} archivos, {data.get('root', '?')}")
        return "\n".join(lines)

    elif action == "info":
        if not project:
            return "Error: Proporciona 'project'."
        index = _load_index()
        if project not in index:
            return f"Proyecto '{project}' no encontrado en el índice."
        data = index[project]
        lang_counts = {}
        symbol_count = 0
        for f in data.get("files", []):
            lang = f.get("language", "Unknown")
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            symbol_count += len(f.get("symbols", []))
        lines = [f"Proyecto: {project}"]
        lines.append(f"  Ruta: {data.get('root', '?')}")
        lines.append(f"  Archivos: {data.get('file_count', 0)}")
        lines.append(f"  Símbolos: {symbol_count}")
        lines.append(f"  Tamaño: {data.get('total_size', 0) / 1024:.1f} KB")
        lines.append(f"  Indexado: {data.get('indexed_at', '?')}")
        lines.append("  Lenguajes:")
        for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
            lines.append(f"    {lang}: {count}")
        return "\n".join(lines)

    elif action == "search":
        if not project or not query:
            return "Error: Proporciona 'project' y 'query'."
        index = _load_index()
        if project not in index:
            return f"Proyecto '{project}' no encontrado."
        results = _search_project(index[project], query)
        if not results:
            return f"Sin resultados para '{query}' en '{project}'."
        lines = [f"Resultados en '{project}' para '{query}' ({len(results)}):"]
        for r in results[:25]:
            if r["line"]:
                lines.append(f"  {r['file']}:{r['line']}  {r['match']}")
            else:
                lines.append(f"  {r['file']}")
        return "\n".join(lines)

    elif action == "find_symbol":
        if not project or not symbol:
            return "Error: Proporciona 'project' y 'symbol'."
        index = _load_index()
        if project not in index:
            return f"Proyecto '{project}' no encontrado."
        q = symbol.lower()
        results = []
        for f in index[project].get("files", []):
            for s in f.get("symbols", []):
                if q in s["name"].lower():
                    results.append({"file": f["path"], "symbol": s["name"], "kind": s["kind"], "line": s["line"]})
        if not results:
            return f"Símbolo '{symbol}' no encontrado en '{project}'."
        lines = [f"Símbolos encontrados para '{symbol}' en '{project}' ({len(results)}):"]
        for r in results:
            lines.append(f"  {r['kind']}: {r['symbol']}  {r['file']}:{r['line']}")
        return "\n".join(lines)

    elif action == "generate_docs":
        if not file_path:
            return "Error: Proporciona 'file_path'."
        fp = Path(file_path).expanduser().resolve()
        if not fp.exists():
            return f"Error: Archivo '{fp}' no encontrado."
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error leyendo archivo: {e}"
        symbols = _extract_symbols(fp)
        lines = [f"Documentación de {fp.name}", "=" * 40, ""]
        if symbols:
            lines.append(f"Símbolos ({len(symbols)}):")
            for s in symbols:
                lines.append(f"  {s['kind']}: {s['name']} (línea {s['line']})")
            lines.append("")
        lines.append(f"Líneas: {text.count(chr(10)) + 1}")
        lines.append(f"Tamaño: {len(text)} chars")
        lines.append(f"Extensión: {fp.suffix.lower()}")
        return "\n".join(lines)

    elif action == "remove":
        if not project:
            return "Error: Proporciona 'project'."
        index = _load_index()
        if project not in index:
            return f"Proyecto '{project}' no encontrado."
        del index[project]
        _save_index(index)
        return f"Proyecto '{project}' eliminado del índice."

    else:
        return (f"Acción '{action}' no reconocida. Acciones: index, list, info, search, find_symbol, generate_docs, remove.")
