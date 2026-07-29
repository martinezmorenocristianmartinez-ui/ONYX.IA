"""Robust Windows application launcher for ONYX."""
from __future__ import annotations

import os
import shutil
import subprocess
import unicodedata
import winreg
from pathlib import Path


SYSTEM_COMMANDS = {
    "notepad": "notepad.exe",
    "bloc de notas": "notepad.exe",
    "calculator": "calc.exe",
    "calculadora": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "explorador": "explorer.exe",
    "explorador de archivos": "explorer.exe",
    "control panel": "control.exe",
    "panel de control": "control.exe",
    "task manager": "taskmgr.exe",
    "administrador de tareas": "taskmgr.exe",
    "settings": "ms-settings:",
    "configuracion": "ms-settings:",
    "configuración": "ms-settings:",
}


APP_EXE_ALIASES = {
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "brave": ["brave.exe"],
    "opera": ["opera.exe"],
    "steam": ["steam.exe"],
    "spotify": ["Spotify.exe"],
    "discord": ["Discord.exe", "Update.exe"],
    "whatsapp": ["WhatsApp.exe"],
    "esound": ["eSound.exe", "eSound Music.exe", "eSound-Music.exe", "eSoundMusic.exe"],
    "esound music": ["eSound.exe", "eSound Music.exe", "eSound-Music.exe", "eSoundMusic.exe"],
    "eSound Music": ["eSound.exe", "eSound Music.exe", "eSound-Music.exe", "eSoundMusic.exe"],
    "word": ["WINWORD.EXE"],
    "microsoft word": ["WINWORD.EXE"],
    "excel": ["EXCEL.EXE"],
    "microsoft excel": ["EXCEL.EXE"],
    "hoja de calculo": ["EXCEL.EXE"],
    "hoja de cálculo": ["EXCEL.EXE"],
    "hoja excel": ["EXCEL.EXE"],
    "powerpoint": ["POWERPNT.EXE"],
    "microsoft powerpoint": ["POWERPNT.EXE"],
    "outlook": ["OUTLOOK.EXE"],
    "microsoft outlook": ["OUTLOOK.EXE"],
    "teams": ["Teams.exe"],
    "microsoft teams": ["Teams.exe"],
    "vscode": ["Code.exe"],
    "visual studio code": ["Code.exe"],
    "code": ["Code.exe"],
    "epic": ["EpicGamesLauncher.exe"],
    "epic games": ["EpicGamesLauncher.exe"],
    "epic game": ["EpicGamesLauncher.exe"],
    "epic games launcher": ["EpicGamesLauncher.exe"],
}


COMMON_RELATIVE_PATHS = {
    "epic games launcher": [
        r"Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        r"Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    ],
    "epic games": [
        r"Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        r"Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    ],
    "epic": [
        r"Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        r"Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    ],
    "chrome": [
        r"Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"Microsoft\Edge\Application\msedge.exe",
    ],
    "vscode": [
        r"Microsoft VS Code\Code.exe",
        r"Programs\Microsoft VS Code\Code.exe",
    ],
    "spotify": [
        r"Spotify\Spotify.exe",
    ],
    "discord": [
        r"Discord\Update.exe",
    ],
    "esound": [
        r"eSound\eSound.exe",
        r"eSound Music\eSound.exe",
        r"eSound-Music\eSound.exe",
    ],
    "esound music": [
        r"eSound\eSound.exe",
        r"eSound Music\eSound.exe",
        r"eSound-Music\eSound.exe",
    ],
    "word": [
        r"Microsoft Office\Root\Office16\WINWORD.EXE",
        r"Microsoft Office\root\Office16\WINWORD.EXE",
        r"Microsoft Office\root\Office15\WINWORD.EXE",
        r"Microsoft Office\root\Office14\WINWORD.EXE",
        r"Microsoft Office\Office16\WINWORD.EXE",
        r"Microsoft Office\Office15\WINWORD.EXE",
        r"Microsoft Office\Office14\WINWORD.EXE",
        r"Microsoft Office 15\root\office15\WINWORD.EXE",
    ],
    "excel": [
        r"Microsoft Office\Root\Office16\EXCEL.EXE",
        r"Microsoft Office\root\Office16\EXCEL.EXE",
        r"Microsoft Office\root\Office15\EXCEL.EXE",
        r"Microsoft Office\root\Office14\EXCEL.EXE",
        r"Microsoft Office\Office16\EXCEL.EXE",
        r"Microsoft Office\Office15\EXCEL.EXE",
        r"Microsoft Office\Office14\EXCEL.EXE",
        r"Microsoft Office 15\root\office15\EXCEL.EXE",
    ],
    "powerpoint": [
        r"Microsoft Office\Root\Office16\POWERPNT.EXE",
        r"Microsoft Office\root\Office16\POWERPNT.EXE",
        r"Microsoft Office\root\Office15\POWERPNT.EXE",
        r"Microsoft Office\root\Office14\POWERPNT.EXE",
        r"Microsoft Office\Office16\POWERPNT.EXE",
        r"Microsoft Office\Office15\POWERPNT.EXE",
        r"Microsoft Office\Office14\POWERPNT.EXE",
        r"Microsoft Office 15\root\office15\POWERPNT.EXE",
    ],
    "outlook": [
        r"Microsoft Office\Root\Office16\OUTLOOK.EXE",
        r"Microsoft Office\root\Office16\OUTLOOK.EXE",
        r"Microsoft Office\Office16\OUTLOOK.EXE",
    ],
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().strip().split())


def _base_dirs() -> list[Path]:
    from core.file_utils import get_desktop_path
    raw = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
        os.environ.get("ProgramData"),
        str(get_desktop_path()),
        str(Path.home() / "Desktop"),
    ]
    for drive in "DEFGHI":
        raw.extend([f"{drive}:\\Program Files", f"{drive}:\\Program Files (x86)", f"{drive}:\\Epic Games"])
    dirs = []
    for item in raw:
        if item:
            path = Path(item)
            if path.exists() and path not in dirs:
                dirs.append(path)
    return dirs


def _start_menu_dirs() -> list[Path]:
    candidates = [
        Path(os.environ.get("ProgramData", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path.home() / "Desktop",
        Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Desktop",
    ]
    return [path for path in candidates if path.exists()]


def _query_app_path(exe_name: str) -> Path | None:
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
    )
    for hive, key_path in roots:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
                path = Path(value)
                if path.exists():
                    return path
        except OSError:
            continue
    return None


def _shortcut_score(shortcut: Path, query: str) -> int:
    name = _norm(shortcut.stem)
    tokens = [token for token in query.split() if token]
    if name == query:
        return 100
    if query in name:
        return 80
    if tokens and all(token in name for token in tokens):
        return 60
    if tokens and any(token in name for token in tokens):
        return 20
    return 0


def _find_shortcut(app_name: str) -> Path | None:
    query = _norm(app_name)
    best: tuple[int, Path] | None = None
    for folder in _start_menu_dirs():
        try:
            for shortcut in folder.rglob("*.lnk"):
                score = _shortcut_score(shortcut, query)
                if score and (best is None or score > best[0]):
                    best = (score, shortcut)
        except OSError:
            continue
    return best[1] if best else None


def _candidate_relative_paths(app_name: str) -> list[str]:
    name = _norm(app_name)
    paths: list[str] = []
    for key, values in COMMON_RELATIVE_PATHS.items():
        if key in name or name in key:
            paths.extend(values)
    return paths


def _candidate_exes(app_name: str) -> list[str]:
    name = _norm(app_name)
    exes: list[str] = []
    for key, values in APP_EXE_ALIASES.items():
        if key in name or name in key:
            exes.extend(values)
    if app_name.lower().endswith(".exe"):
        exes.append(app_name)
    else:
        raw = name + ".exe"
        if raw not in exes:
            exes.append(raw)
        compact = name.replace(" ", "")
        if compact and compact + ".exe" not in exes:
            exes.append(compact + ".exe")
        tokens = name.split()
        if len(tokens) > 1:
            first = tokens[0] + ".exe"
            if first not in exes:
                exes.append(first)
            last = tokens[-1] + ".exe"
            if last not in exes:
                exes.append(last)
    return list(dict.fromkeys(exes))


def find_app_path(app_name: str) -> str:
    """Find an application target: exe path, shortcut path, protocol, or command."""
    name = _norm(app_name)
    if name in SYSTEM_COMMANDS:
        return SYSTEM_COMMANDS[name]

    for exe in _candidate_exes(app_name):
        reg_path = _query_app_path(exe)
        if reg_path:
            return str(reg_path)

        which = shutil.which(exe)
        if which:
            return which

    for base in _base_dirs():
        for relative in _candidate_relative_paths(app_name):
            candidate = base / relative
            if candidate.exists():
                return str(candidate)

    shortcut = _find_shortcut(app_name)
    if shortcut:
        return str(shortcut)

    for base in _base_dirs():
        try:
            for exe in base.rglob("*.exe"):
                exe_name = _norm(exe.stem)
                if name and (name in exe_name or exe_name in name):
                    return str(exe)
        except OSError:
            continue

    for exe in _candidate_exes(app_name):
        try:
            os.startfile(exe)
            return exe
        except OSError:
            continue

    # Last resort: try via cmd /c start (handles AppUserModelId and registered apps)
    try:
        subprocess.Popen(["cmd", "/c", "start", "", name], shell=True, close_fds=True)
        print(f"[open_app] Fallback start cmd para: {name}")
        return name
    except OSError:
        pass

    return app_name


def _launch_target(target: str) -> None:
    if target.startswith(("ms-settings:", "com.epicgames.launcher://", "steam://", "http://", "https://")):
        os.startfile(target)
        return

    path = Path(target)
    if path.exists():
        if path.suffix.lower() == ".lnk":
            os.startfile(str(path))
            return
        subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
        return

    os.startfile(target)


def open_app(parameters: dict, response=None, player=None) -> str:
    """Launch local desktop applications with robust Windows path search."""
    app_name = str(parameters.get("app_name", "")).strip()
    if not app_name:
        return "Senor Cristian, necesito el nombre de la aplicacion."

    normalized = _norm(app_name)
    if "fortnite" in normalized or "fortnit" in normalized:
        from actions.epic_fortnite_control import epic_fortnite_control

        return epic_fortnite_control({"action": "open_fortnite"}, player=player)
    if "epic" in normalized:
        from actions.epic_fortnite_control import epic_fortnite_control

        return epic_fortnite_control({"action": "open_epic"}, player=player)

    if player:
        player.write_log(f"Buscando aplicacion: {app_name}")

    try:
        target = find_app_path(app_name)
        if player:
            player.write_log(f"Destino encontrado: {target}")
        _launch_target(target)
        return f"Hecho, Senor Cristian. He abierto {app_name}."
    except Exception as exc:
        if player:
            player.write_log(f"Error abriendo {app_name}: {exc}")
        return f"No pude abrir '{app_name}', Senor Cristian. Error: {exc}"
