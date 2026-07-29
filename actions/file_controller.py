import os
import shutil
import subprocess
import json
from pathlib import Path
from datetime import datetime
import send2trash

def _get_desktop():
    try:
        from core.file_utils import get_desktop_path
        return get_desktop_path()
    except:
        return Path.home() / "Desktop"

def _get_documents():
    try:
        from core.file_utils import get_documents_path
        return get_documents_path()
    except:
        return Path.home() / "Documents"

_SHORTCUTS = {
    "desktop": _get_desktop(),
    "downloads": Path.home() / "Downloads",
    "documents": _get_documents(),
    "home": Path.home(),
    "music": Path.home() / "Music",
    "pictures": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "project": Path(__file__).resolve().parent.parent,
    "proyecto": Path(__file__).resolve().parent.parent,
}

def _resolve_path(path: str) -> Path:
    if not path:
        return _SHORTCUTS["project"]
    p = path.lower().strip()
    if p in _SHORTCUTS:
        return _SHORTCUTS[p]
    return Path(path).expanduser().resolve()

def _list_directory(path: Path, detail: bool = False) -> str:
    if not path.exists():
        return f"Error: La ruta '{path}' no existe."
    if not path.is_dir():
        return f"Error: '{path}' no es un directorio."
    items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines = [f"Contenido de '{path}':"]
    for item in items:
        if item.is_dir():
            lines.append(f"  [DIR]  {item.name}/")
        else:
            size = item.stat().st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 ** 2:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / 1024 ** 2:.1f} MB"
            modified = datetime.fromtimestamp(item.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            if detail:
                lines.append(f"  [FILE] {item.name}  ({size_str}, {modified})")
            else:
                lines.append(f"  [FILE] {item.name}")
    if len(lines) == 1:
        return f"El directorio '{path}' está vacío."
    return "\n".join(lines)

def _find_files(path: Path, name: str = "", extension: str = "", max_results: int = 200, search_all: bool = False) -> str:
    if not path.exists():
        return f"Error: La ruta '{path}' no existe."
    # Soportar una o varias extensiones (string simple o separadas por coma).
    if isinstance(extension, (list, tuple, set)):
        exts = [str(e).strip().lower() for e in extension if str(e).strip()]
    else:
        exts = [e.strip().lower() for e in str(extension or "").split(",") if e.strip()]
    results = []
    try:
        for root, dirs, files in os.walk(path):
            if len(results) >= max_results:
                break
            for f in files:
                if len(results) >= max_results:
                    break
                fp = Path(root) / f
                fl = f.lower()
                nlow = (name or "").lower().strip()
                if not nlow:
                    match_name = True
                else:
                    # Coincide si TODAS las palabras del nombre están en el archivo
                    # (en cualquier orden). Así 'memorias uraba' encuentra
                    # 'Plan de capacitacion memorias de uraba.pdf'.
                    match_name = all(tok in fl for tok in nlow.split())
                match_ext = not exts or any(fl.endswith(e) for e in exts)
                if match_name and match_ext:
                    size = fp.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 ** 2:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / 1024 ** 2:.1f} MB"
                    results.append(f"  {fp}  ({size_str})")
    except Exception as e:
        return f"Error durante la búsqueda: {e}"
    if not results:
        return f"No se encontraron archivos en '{path}' con esos criterios."
    header = f"Archivos encontrados ({len(results)}):"
    return header + "\n" + "\n".join(results[:max_results])

def _largest_files(path: Path, count: int = 10) -> str:
    if not path.exists():
        return f"Error: La ruta '{path}' no existe."
    files = []
    try:
        for root, dirs, fnames in os.walk(path):
            for f in fnames:
                fp = Path(root) / f
                try:
                    files.append((fp.stat().st_size, fp))
                except:
                    pass
    except Exception as e:
        return f"Error: {e}"
    files.sort(reverse=True, key=lambda x: x[0])
    lines = [f"Archivos más grandes en '{path}' (top {min(count, len(files))}):"]
    for size, fp in files[:count]:
        if size < 1024 ** 2:
            size_str = f"{size / 1024:.1f} KB"
        elif size < 1024 ** 3:
            size_str = f"{size / 1024 ** 2:.1f} MB"
        else:
            size_str = f"{size / 1024 ** 3:.2f} GB"
        lines.append(f"  {size_str:>8}  {fp}")
    return "\n".join(lines)

def file_controller(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower()
    path_str = parameters.get("path", "")
    dest_str = parameters.get("destination", "")
    new_name = parameters.get("new_name", "")
    content = parameters.get("content", "")
    name = parameters.get("name", "")
    extension = parameters.get("extension", "")
    count = parameters.get("count", 10)
    old_text = parameters.get("old_text", "")
    new_text = parameters.get("new_text", "")
    mode = parameters.get("mode", "replace")
    confirm = parameters.get("confirm", False)

    path = _resolve_path(path_str) if path_str else _SHORTCUTS["project"]

    if action == "list":
        return _list_directory(path, detail=True)

    elif action == "find" and not path_str:
        results = []
        for dir_path in [_SHORTCUTS["project"], _SHORTCUTS["desktop"], _SHORTCUTS["downloads"], _SHORTCUTS["documents"]]:
            r = _find_files(dir_path, name=name, extension=extension, max_results=100)
            if "No se encontraron" not in r:
                results.append(r)
            if sum(len(r.splitlines()) for r in results) > 200:
                break
        if results:
            return "\n---\n".join(results)
        return f"No se encontraron archivos con el nombre '{name}' en proyecto, escritorio, descargas ni documentos."

    elif action == "create_file":
        if not content:
            return "Error: Proporciona 'content' para crear el archivo."
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Archivo creado: {path}"
        except Exception as e:
            return f"Error creando archivo: {e}"

    elif action == "create_folder":
        try:
            path.mkdir(parents=True, exist_ok=True)
            return f"Carpeta creada: {path}"
        except Exception as e:
            return f"Error creando carpeta: {e}"

    elif action == "delete":
        if not confirm:
            return "Debes confirmar la eliminación con confirm=true."
        try:
            if path.is_dir():
                shutil.rmtree(path)
                return f"Carpeta eliminada permanentemente: {path}"
            else:
                send2trash.send2trash(str(path))
                return f"Archivo enviado a la papelera: {path}"
        except Exception as e:
            return f"Error eliminando: {e}"

    elif action == "move":
        if not dest_str:
            return "Error: Proporciona 'destination'."
        dest = _resolve_path(dest_str)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
            return f"Movido: {path} -> {dest}"
        except Exception as e:
            return f"Error moviendo: {e}"

    elif action == "copy":
        if not dest_str:
            return "Error: Proporciona 'destination'."
        dest = _resolve_path(dest_str)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                shutil.copytree(str(path), str(dest))
            else:
                shutil.copy2(str(path), str(dest))
            return f"Copiado: {path} -> {dest}"
        except Exception as e:
            return f"Error copiando: {e}"

    elif action == "rename":
        if not new_name:
            return "Error: Proporciona 'new_name'."
        try:
            new_path = path.parent / new_name
            path.rename(new_path)
            return f"Renombrado: {path} -> {new_path}"
        except Exception as e:
            return f"Error renombrando: {e}"

    elif action == "read":
        try:
            if not path.exists():
                return f"Error: Archivo no encontrado: {path}"
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > 5000:
                text = text[:5000] + "\n...[Truncado]"
            return f"Contenido de '{path}':\n{text}"
        except Exception as e:
            return f"Error leyendo archivo: {e}"

    elif action == "write":
        if not content:
            return "Error: Proporciona 'content' para escribir."
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Archivo escrito: {path}"
        except Exception as e:
            return f"Error escribiendo archivo: {e}"

    elif action == "edit":
        try:
            if not path.exists():
                return f"Error: Archivo no encontrado: {path}"
            current = path.read_text(encoding="utf-8", errors="replace")
            if mode == "replace":
                if not old_text:
                    return "Error: Proporciona 'old_text' para replace."
                new_content = current.replace(old_text, new_text)
            elif mode == "append":
                new_content = current + "\n" + new_text
            elif mode == "prepend":
                new_content = new_text + "\n" + current
            elif mode == "overwrite":
                new_content = new_text
            else:
                return f"Error: Modo '{mode}' no válido. Usa: replace, append, prepend, overwrite."
            path.write_text(new_content, encoding="utf-8")
            return f"Archivo editado correctamente: {path}"
        except Exception as e:
            return f"Error editando archivo: {e}"

    elif action == "find":
        return _find_files(path, name=name, extension=extension, max_results=200)

    elif action == "lar":
        return _largest_files(path, count=count)

    else:
        return f"Acción '{action}' no reconocida. Acciones: list, create_file, create_folder, delete, move, copy, rename, read, write, edit, find, lar."
