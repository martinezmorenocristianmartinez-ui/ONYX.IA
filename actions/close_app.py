"""close_app.py — Cierra aplicaciones, ventanas y documentos en Windows."""

from __future__ import annotations

import re
import time

APP_EXE_ALIASES = {
    "whatsapp": ["WhatsApp.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "brave": ["brave.exe"],
    "opera": ["opera.exe"],
    "steam": ["steam.exe"],
    "spotify": ["Spotify.exe"],
    "discord": ["Discord.exe"],
    "word": ["WINWORD.EXE"],
    "microsoft word": ["WINWORD.EXE"],
    "excel": ["EXCEL.EXE"],
    "microsoft excel": ["EXCEL.EXE"],
    "powerpoint": ["POWERPNT.EXE"],
    "outlook": ["OUTLOOK.EXE"],
    "teams": ["Teams.exe"],
    "microsoft teams": ["Teams.exe"],
    "vscode": ["Code.exe"],
    "visual studio code": ["Code.exe"],
    "code": ["Code.exe"],
    "notepad": ["notepad.exe"],
    "bloc de notas": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calculadora": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "cmd": ["cmd.exe"],
    "terminal": ["wt.exe"],
    "powershell": ["powershell.exe"],
    "explorer": ["explorer.exe"],
    "explorador": ["explorador.exe"],
    "task manager": ["taskmgr.exe"],
    "administrador de tareas": ["taskmgr.exe"],
    "epic": ["EpicGamesLauncher.exe"],
    "epic games": ["EpicGamesLauncher.exe"],
    "telegram": ["Telegram.exe"],
    "zoom": ["Zoom.exe"],
    "slack": ["slack.exe"],
    "skype": ["Skype.exe"],
    "vlc": ["vlc.exe"],
    "adobe reader": ["AcroRd32.exe"],
    "acrobat": ["AcroRd32.exe"],
}

SYSTEM_APPS = {
    "notepad": "notepad.exe",
    "bloc de notas": "notepad.exe",
    "calculator": "calc.exe",
    "calculadora": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "administrador de tareas": "taskmgr.exe",
}

_TITLE_BLACKLIST = {"", "Program Manager", "Menu Inicio", "Inicio"}


def _get_process_names(name: str) -> list[str]:
    """Resuelve nombre de app a posibles nombres de proceso."""
    lower = name.lower().strip()
    if lower in APP_EXE_ALIASES:
        return APP_EXE_ALIASES[lower]
    if lower in SYSTEM_APPS:
        return [SYSTEM_APPS[lower]]
    if lower.endswith(".exe"):
        return [name]
    return [f"{name}.exe", f"{name}.EXE"]


def _close_by_title(name_fragment: str) -> int:
    """Busca ventanas cuyo título contenga el fragmento y las cierra."""
    try:
        import pygetwindow as gw
    except ImportError:
        return 0
    count = 0
    try:
        windows = gw.getAllWindows()
    except Exception:
        return 0
    for win in windows:
        try:
            title = (win.title or "").strip()
            if not title or title in _TITLE_BLACKLIST:
                continue
            if name_fragment.lower() in title.lower():
                try:
                    win.activate()
                    time.sleep(0.15)
                    win.close()
                    count += 1
                except Exception:
                    pass
        except Exception:
            pass
    return count


def _close_by_process(exe_names: list[str]) -> int:
    """Mata procesos por nombre de ejecutable."""
    try:
        import psutil
    except ImportError:
        return 0
    count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            pname = proc.info["name"] or ""
            for exe in exe_names:
                if pname.lower() == exe.lower():
                    proc.kill()
                    count += 1
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return count


def _close_active_window() -> str:
    """Cierra la ventana activa."""
    try:
        import pygetwindow as gw

        win = gw.getActiveWindow()
        if win and win.title and win.title not in _TITLE_BLACKLIST:
            try:
                win.close()
                return f"He cerrado la ventana '{win.title}'."
            except Exception as e:
                return f"No pude cerrar la ventana activa: {e}"
        return "No hay una ventana activa para cerrar."
    except Exception as e:
        return f"Error al cerrar ventana activa: {e}"


def _close_all_windows() -> int:
    """Cierra todas las ventanas de usuario no críticas."""
    try:
        import pygetwindow as gw
    except ImportError:
        return 0
    count = 0
    try:
        windows = gw.getAllWindows()
    except Exception:
        return 0
    for win in windows:
        try:
            title = (win.title or "").strip()
            if not title or title in _TITLE_BLACKLIST:
                continue
            try:
                win.activate()
                time.sleep(0.1)
                win.close()
                count += 1
            except Exception:
                pass
        except Exception:
            pass
    return count


def close_app(parameters: dict, response=None, player=None) -> str:
    """Cierra aplicaciones, ventanas o documentos por nombre.

    Args:
        parameters: Diccionario con clave 'app_name' (opcional).
                   Si se omite, cierra la ventana activa.
    """
    app_name = (parameters.get("app_name") or parameters.get("name") or "").strip()

    if not app_name:
        return _close_active_window()

    lower = app_name.lower().strip()

    # Comandos especiales
    if lower in ("todo", "todas", "todas las ventanas", "todos", "todo"):
        closed = _close_all_windows()
        if closed > 0:
            return f"He cerrado {closed} ventanas."
        return "No habia ventanas abiertas para cerrar."

    if lower in ("esto", "esta", "esta ventana", "este", "este documento", "activa", "esa", "esa ventana"):
        return _close_active_window()

    # Intentar por título de ventana primero (más amigable)
    title_count = _close_by_title(app_name)

    # También por proceso
    exe_names = _get_process_names(app_name)
    proc_count = _close_by_process(exe_names)

    total = title_count + proc_count
    if total > 0:
        friendly = exe_names[0].replace(".exe", "").replace(".EXE", "")
        return f"He cerrado {friendly} ({total} {'ventana' if total == 1 else 'ventanas'})."

    # Último intento: buscar ventanas que contengan alguna palabra clave
    keywords = re.split(r"[/\s,;:.!?]+", app_name)
    for kw in keywords:
        if len(kw) < 3:
            continue
        c = _close_by_title(kw)
        if c > 0:
            return f"He cerrado {c} {'ventana' if c == 1 else 'ventanas'} relacionadas con '{kw}'."
        c2 = _close_by_process([f"{kw}.exe", f"{kw}.EXE", f"{kw.capitalize()}.exe"])
        if c2 > 0:
            return f"He cerrado {c2} proceso{'s' if c2 > 1 else ''} de '{kw}'."

    return f"No encontre ninguna aplicacion, ventana o proceso llamado '{app_name}'."
