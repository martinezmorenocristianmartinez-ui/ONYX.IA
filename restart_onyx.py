"""Restart only this ONYX instance."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
MAIN = BASE_DIR / "main.py"
PYW = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"


def _same_file(path_text: str) -> bool:
    try:
        return Path(path_text).resolve() == MAIN.resolve()
    except Exception:
        return False


def stop_current_instances() -> int:
    try:
        import psutil
    except Exception:
        return 0

    current_pid = None
    try:
        current_pid = psutil.Process().pid
    except Exception:
        pass

    stopped = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            name = (proc.info.get("name") or "").lower()
            if name not in ("python.exe", "pythonw.exe"):
                continue
            cmdline = proc.info.get("cmdline") or []
            if any(_same_file(part) for part in cmdline):
                proc.terminate()
                stopped += 1
        except Exception:
            continue

    deadline = time.time() + 5
    while time.time() < deadline:
        alive = []
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                cmdline = proc.info.get("cmdline") or []
                if name in ("python.exe", "pythonw.exe") and any(_same_file(part) for part in cmdline):
                    alive.append(proc)
            except Exception:
                pass
        if not alive:
            break
        time.sleep(0.2)

    for proc in alive if "alive" in locals() else []:
        try:
            proc.kill()
        except Exception:
            pass
    return stopped


def start_onyx() -> None:
    exe = PYW if PYW.exists() else PY
    if not exe.exists() or not MAIN.exists():
        raise FileNotFoundError(f"No se encontro {exe} o {MAIN}")
    subprocess.Popen([str(exe), str(MAIN)], cwd=str(BASE_DIR), close_fds=True)


def main() -> int:
    stopped = stop_current_instances()
    time.sleep(1)
    start_onyx()
    print(f"ONYX reiniciado. Instancias cerradas: {stopped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
