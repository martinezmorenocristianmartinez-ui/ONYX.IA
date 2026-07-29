"""Epic Games Launcher and Fortnite control."""
from __future__ import annotations

import os
import subprocess
import time
import winreg
from pathlib import Path


EPIC_FORTNITE_LAUNCH_URI = "com.epicgames.launcher://apps/Fortnite?action=launch&silent=true"
EPIC_FORTNITE_STORE_URI = "com.epicgames.launcher://store/product/fortnite/home"
EPIC_HOME_URI = "com.epicgames.launcher://home"


_HAS_PSUTIL = None

def _check_psutil():
    global _HAS_PSUTIL
    if _HAS_PSUTIL is None:
        try:
            import psutil
            _HAS_PSUTIL = True
        except ImportError:
            _HAS_PSUTIL = False
    return _HAS_PSUTIL


def _drives() -> list[str]:
    drives = []
    for letter in "BCDEFGHIJ":
        root = f"{letter}:\\"
        if Path(root).exists():
            drives.append(root)
    return drives or ["C:\\"]


def _launcher_candidates() -> list[Path]:
    candidates: list[Path] = []
    for drive in _drives():
        for base in ("Program Files", "Program Files (x86)"):
            root = Path(drive) / base / "Epic Games" / "Launcher" / "Portal" / "Binaries"
            candidates.extend(
                [
                    root / "Win64" / "EpicGamesLauncher.exe",
                    root / "Win32" / "EpicGamesLauncher.exe",
                ]
            )
    candidates.extend(
        [
            Path(os.environ.get("ProgramFiles", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
        ]
    )
    return candidates


def _fortnite_candidates() -> list[Path]:
    candidates: list[Path] = []
    for drive in _drives():
        for base in ("Program Files", "Program Files (x86)", "Epic Games"):
            root = Path(drive) / base if base != "Epic Games" else Path(drive) / base
            candidates.append(root / "Epic Games" / "Fortnite" / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe")
            candidates.append(root / "Fortnite" / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe")
    return candidates


def _app_path_from_registry(exe_name: str) -> Path | None:
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


def find_epic_launcher() -> Path | None:
    reg_path = _app_path_from_registry("EpicGamesLauncher.exe")
    if reg_path:
        return reg_path
    for path in _launcher_candidates():
        if path.exists():
            return path
    return None


def find_fortnite_binary() -> Path | None:
    for path in _fortnite_candidates():
        if path.exists():
            return path
    return None


def _open_uri(uri: str) -> None:
    os.startfile(uri)


def _launch_exe(path: Path) -> None:
    try:
        subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
    except Exception as exc:
        raise RuntimeError(f"No se pudo lanzar '{path}': {exc}") from exc


def _is_launcher_running() -> bool:
    if not _check_psutil():
        return False
    import psutil
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() == "epicgameslauncher.exe":
                return True
        except Exception:
            continue
    return False


def _wait_for_launcher(max_wait: float = 15.0) -> None:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if _is_launcher_running():
            return
        time.sleep(0.5)


def open_epic_launcher(player=None) -> str:
    launcher = find_epic_launcher()
    if launcher:
        if player:
            player.write_log(f"Abriendo Epic Games Launcher: {launcher}")
        _launch_exe(launcher)
        return f"He abierto Epic Games Launcher desde: {launcher}"

    if player:
        player.write_log("No encontre EpicGamesLauncher.exe; intentando protocolo de Epic.")
    _open_uri(EPIC_HOME_URI)
    return "He intentado abrir Epic Games Launcher mediante su protocolo de Windows."


def launch_fortnite(player=None, ensure_launcher: bool = True) -> str:
    launcher = find_epic_launcher()
    fortnite = find_fortnite_binary()

    if ensure_launcher and not _is_launcher_running():
        if launcher:
            if player:
                player.write_log("Abriendo Epic Games Launcher antes de Fortnite...")
            _launch_exe(launcher)
            _wait_for_launcher()
        else:
            if player:
                player.write_log("Launcher no encontrado por ruta; usando protocolo de Epic.")
            _open_uri(EPIC_HOME_URI)
            _wait_for_launcher()

    if player:
        player.write_log("Solicitando a Epic Games Launcher iniciar Fortnite...")

    try:
        _open_uri(EPIC_FORTNITE_LAUNCH_URI)
        if fortnite:
            return (
                "He enviado la orden correcta a Epic Games Launcher para iniciar Fortnite. "
                f"Fortnite esta instalado en: {fortnite}"
            )
        return "He enviado la orden a Epic Games Launcher para iniciar Fortnite."
    except Exception as exc:
        if fortnite:
            return (
                "No pude usar el protocolo de Epic para Fortnite. "
                f"Fortnite existe en {fortnite}, pero abrirlo directo suele fallar porque Epic exige el launcher. "
                f"Detalle: {exc}"
            )
        _open_uri(EPIC_FORTNITE_STORE_URI)
        return "No encontre Fortnite instalado por ruta; abri la pagina de Fortnite en Epic Games Launcher."


def epic_fortnite_control(parameters: dict, player=None) -> str:
    """Control Epic Games Launcher and launch Fortnite through Epic."""
    action = str(parameters.get("action", "")).lower().strip()
    if not action:
        action = "open_epic_fortnite"

    try:
        if action in (
            "open_epic",
            "abrir_epic",
            "open_epic_games",
            "abrir_epic_games_launcher",
            "open_epic_launcher",
        ):
            return open_epic_launcher(player=player)

        if action in (
            "open_epic_fortnite",
            "abrir_epic_y_fortnite",
            "open_fortnite_from_epic",
            "open_fortnite",
            "abrir_fortnite",
            "jugar_fortnite",
            "iniciar_fortnite",
            "launch_fortnite",
        ):
            return launch_fortnite(player=player, ensure_launcher=True)

        if action in ("fortnite_store", "open_fortnite_store", "abrir_pagina_fortnite"):
            _open_uri(EPIC_FORTNITE_STORE_URI)
            return "He abierto la pagina de Fortnite en Epic Games Launcher."

        return f"Accion '{action}' no reconocida para Epic/Fortnite."
    except Exception as exc:
        return f"Error al controlar Epic/Fortnite: {exc}"
