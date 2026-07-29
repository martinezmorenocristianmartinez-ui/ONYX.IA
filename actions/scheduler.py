"""
scheduler.py — Task scheduling system for ONYX.
Persists scheduled tasks to JSON, runs a background thread
that checks for due tasks and fires callbacks.
"""
import json
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = BASE_DIR / "config" / "schedule.json"

_schedule_lock = threading.Lock()
_runner: Optional[threading.Thread] = None
_runner_running = False
_speak_callback: Optional[Callable] = None


def _load_tasks() -> list[dict]:
    with _schedule_lock:
        if SCHEDULE_FILE.exists():
            try:
                return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []


def _save_tasks(tasks: list[dict]) -> None:
    with _schedule_lock:
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULE_FILE.write_text(
            json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def scheduler(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action", "") or "").lower().strip()
    tasks = _load_tasks()
    name = (parameters.get("name") or "").strip()

    if action == "list":
        if not tasks:
            return "No hay tareas programadas."
        lines = [f"Tienes {len(tasks)} tarea(s) programada(s):"]
        for i, t in enumerate(tasks, 1):
            status = "[ACTIVA]" if t.get("active", True) else "[PAUSADA]"
            freq = t.get("frequency", "once")
            hour = t.get("hour", 0)
            minute = t.get("minute", 0)
            last = t.get("last_run", "nunca")
            lines.append(
                f"  {i}. {status} {t.get('name','?')} | {freq} a las {hour:02d}:{minute:02d} | "
                f"Último: {last}"
            )
            if t.get("description"):
                lines.append(f"     {t['description']}")
        return "\n".join(lines)

    if action == "create":
        if not name:
            return "Falta el nombre de la tarea (name)."
        frequency = (parameters.get("frequency") or "once").lower()
        hour = int(parameters.get("hour", 0))
        minute = int(parameters.get("minute", 0))
        description = parameters.get("description", "")

        task = {
            "name": name,
            "frequency": frequency,
            "hour": hour,
            "minute": minute,
            "description": description,
            "active": True,
            "created": datetime.now().isoformat(),
            "last_run": None,
        }
        tasks.append(task)
        _save_tasks(tasks)
        return f"Tarea '{name}' creada: {frequency} a las {hour:02d}:{minute:02d}."

    if action == "delete":
        if not name:
            return "Falta el nombre de la tarea a eliminar (name)."
        before = len(tasks)
        tasks = [t for t in tasks if t.get("name") != name]
        if len(tasks) == before:
            return f"No se encontró tarea '{name}'."
        _save_tasks(tasks)
        return f"Tarea '{name}' eliminada."

    if action in ("enable", "disable"):
        if not name:
            return f"Falta el nombre de la tarea."
        found = False
        for t in tasks:
            if t.get("name") == name:
                t["active"] = action == "enable"
                found = True
                break
        if not found:
            return f"No se encontró tarea '{name}'."
        _save_tasks(tasks)
        state = "activada" if action == "enable" else "pausada"
        return f"Tarea '{name}' {state}."

    if action == "run_now":
        if not name:
            # Run all due tasks
            due = _check_due_tasks(tasks)
            if due:
                msgs = []
                for t in due:
                    call_speak(f"Tarea programada: {t.get('name', '?')} - {t.get('description', '')}")
                    t["last_run"] = datetime.now().isoformat()
                    msgs.append(f"Ejecutada: {t['name']}")
                _save_tasks(tasks)
                return "\n".join(msgs)
            return "No hay tareas pendientes ahora."
        for t in tasks:
            if t.get("name") == name:
                call_speak(f"Ejecutando tarea: {name} - {t.get('description', '')}")
                t["last_run"] = datetime.now().isoformat()
                _save_tasks(tasks)
                return f"Tarea '{name}' ejecutada."
        return f"No se encontró tarea '{name}'."

    return "Usa: list, create, delete, enable, disable, run_now."


def _check_due_tasks(tasks: list[dict]) -> list[dict]:
    """Return tasks that are due right now."""
    now = datetime.now()
    due = []
    for t in tasks:
        if not t.get("active", True):
            continue
        freq = t.get("frequency", "once")
        hour = t.get("hour", 0)
        minute = t.get("minute", 0)
        last_run = t.get("last_run")

        # Check if the scheduled time matches current time (within 1 minute)
        if now.hour != hour or now.minute != minute:
            continue

        if freq == "once":
            if last_run is None:
                due.append(t)
        elif freq == "daily":
            # Allow once per day
            if last_run is None:
                due.append(t)
            else:
                try:
                    last_dt = datetime.fromisoformat(last_run)
                    if now.date() > last_dt.date():
                        due.append(t)
                except Exception:
                    due.append(t)
        elif freq == "hourly":
            if last_run is None:
                due.append(t)
            else:
                try:
                    last_dt = datetime.fromisoformat(last_run)
                    if (now - last_dt).total_seconds() >= 3600:
                        due.append(t)
                except Exception:
                    due.append(t)
        elif freq == "interval":
            interval_min = int(t.get("interval_minutes", 60))
            if last_run is None:
                due.append(t)
            else:
                try:
                    last_dt = datetime.fromisoformat(last_run)
                    if (now - last_dt).total_seconds() >= interval_min * 60:
                        due.append(t)
                except Exception:
                    due.append(t)
    return due


def call_speak(text: str) -> None:
    global _speak_callback
    if _speak_callback:
        try:
            _speak_callback(text)
        except Exception:
            pass


def _runner_loop(player=None) -> None:
    """Background loop: check tasks every 60 seconds."""
    global _runner_running
    _runner_running = True
    while _runner_running:
        try:
            tasks = _load_tasks()
            due = _check_due_tasks(tasks)
            for t in due:
                msg = f"[SCHEDULER] Tarea programada: {t.get('name', '?')}"
                if player:
                    try:
                        player.write_log(msg)
                    except Exception:
                        pass
                call_speak(f"Tarea programada: {t.get('name', '?')} - {t.get('description', '')}")
                t["last_run"] = datetime.now().isoformat()
            if due:
                _save_tasks(tasks)
        except Exception:
            pass
        for _ in range(60):
            if not _runner_running:
                return
            time.sleep(1)


def start_runner(player=None, speak=None) -> None:
    global _runner, _runner_running, _speak_callback
    if _runner is not None and _runner.is_alive():
        return
    _speak_callback = speak
    _runner = threading.Thread(
        target=_runner_loop, args=(player,), daemon=True
    )
    _runner.start()


def stop_runner() -> None:
    global _runner_running
    _runner_running = False
