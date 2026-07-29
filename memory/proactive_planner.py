"""
proactive_planner.py — Background agent that monitors idle time, time-of-day,
and system conditions to suggest relevant actions to the user.
Runs as a daemon thread, injects messages via callback.
"""
import time
import threading
import json
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

def _load_planner_tz():
    tz = None
    try:
        _cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        if _cfg_path.exists():
            _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
            _tz_name = _cfg.get("timezone", "").strip()
            if _tz_name:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(_tz_name)
    except Exception:
        pass
    return tz

_PLANNER_TZ = _load_planner_tz()

_IDLE_SUGGEST = 600         # 10 min idle -> suggestion
_LONG_IDLE_SUGGEST = 1800   # 30 min idle -> stronger suggestion
_MIN_INTERVAL = 300         # 5 min between suggestions
_CHECK_INTERVAL = 60        # check every 60 seconds


class ProactivePlanner:
    def __init__(self):
        self.last_interaction: float = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._inject_fn: Optional[Callable] = None
        self._speaking_fn: Optional[Callable] = None
        self._last_suggestion: float = 0
        self._brief_done_today: bool = False
        self._afternoon_done: bool = False
        self._evening_done: bool = False
        self._last_idle_warning: int = 0
        self._start_time: float = 0  # set on start, skip triggers for first 120s

    def start(self, inject_fn: Callable, speaking_fn: Optional[Callable] = None) -> None:
        self._inject_fn = inject_fn
        self._speaking_fn = speaking_fn
        if self._running:
            return
        self._start_time = time.time()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def mark_interaction(self) -> None:
        self.last_interaction = time.time()

    @staticmethod
    def _now():
        return datetime.now(_PLANNER_TZ) if _PLANNER_TZ else datetime.now()

    def get_status(self) -> str:
        idle = time.time() - self.last_interaction
        now = self._now()
        return (
            f"Planner activo, {int(idle/60)} min sin interacción, "
            f"hora actual: {now.hour:02d}:{now.minute:02d}, "
            f"brief={self._brief_done_today}, tarde={self._afternoon_done}, "
            f"noche={self._evening_done}"
        )

    def _loop(self) -> None:
        while self._running:
            try:
                self._check_time_triggers()
                self._check_idle()
            except Exception:
                pass
            time.sleep(_CHECK_INTERVAL)

    def _can_suggest(self) -> bool:
        if self._speaking_fn and self._speaking_fn():
            return False
        return (time.time() - self._last_suggestion) >= _MIN_INTERVAL

    def _suggest(self, text: str) -> None:
        if not self._can_suggest():
            return
        self._last_suggestion = time.time()
        if self._inject_fn:
            try:
                self._inject_fn(f"[Proactive] {text}")
            except Exception:
                pass

    def _check_time_triggers(self) -> None:
        now = self._now()
        hour = now.hour
        today_str = now.strftime("%Y-%m-%d")

        # Grace period: skip time triggers for 120s after startup
        if time.time() - self._start_time < 120:
            return

        # Reset daily flags at midnight
        self._reset_daily_flags(today_str)

        # Morning brief (8:00-10:59)
        if 8 <= hour < 11 and not self._brief_done_today:
            self._suggest(
                "Buenos dias Señor Cristian. Han pasado algunas horas desde su ultima conexion. "
                "Si gusta, puedo darle un resumen de lo que hemos estado haciendo o revisar su agenda."
            )
            self._brief_done_today = True

        # Afternoon check-in (14:00-16:59)
        if 14 <= hour < 17 and not self._afternoon_done and self._brief_done_today:
            self._suggest(
                "Buenas tardes Señor Cristian. Recuerde que si necesita ayuda con algo, "
                "puedo analizar datos, ejecutar codigo, buscar archivos o lo que requiera."
            )
            self._afternoon_done = True

        # Evening summary (20:00-22:59)
        if 20 <= hour < 23 and not self._evening_done and self._afternoon_done:
            self._suggest(
                "Se acerca el final del dia. Si desea, puedo preparar un resumen de las "
                "actividades del dia o recordarle tareas pendientes."
            )
            self._evening_done = True

    def _reset_daily_flags(self, today_str: str) -> None:
        stored = getattr(self, "_last_date", "")
        if stored != today_str:
            self._brief_done_today = False
            self._afternoon_done = False
            self._evening_done = False
            self._last_date = today_str

    def _check_idle(self) -> None:
        idle = time.time() - self.last_interaction
        idle_min = int(idle / 60)

        if idle < _IDLE_SUGGEST:
            self._last_idle_warning = 0
            return

        # Idle levels: 10min, 30min, 60min
        if idle_min >= 60 and self._last_idle_warning < 3:
            self._suggest(
                "Lleva mas de una hora sin interaccion. Si termino por hoy, "
                "puedo preparar un resumen del dia. Si no, aqui estoy para lo que necesite."
            )
            self._last_idle_warning = 3
        elif idle_min >= 30 and self._last_idle_warning < 2:
            self._suggest(
                "Lleva un rato sin actividad. Avise si necesita algo, "
                "o si prefiere que entre en modo reposo para ahorrar recursos."
            )
            self._last_idle_warning = 2
        elif idle_min >= 10 and self._last_idle_warning < 1:
            self._suggest(
                f"Han pasado {idle_min} minutos desde su ultimo mensaje. "
                "¿Todo bien? Recuerde que puede pedirme lo que necesite."
            )
            self._last_idle_warning = 1


# Module-level singleton
_planner: Optional[ProactivePlanner] = None
_planner_lock = threading.Lock()


def get_planner() -> ProactivePlanner:
    global _planner
    with _planner_lock:
        if _planner is None:
            _planner = ProactivePlanner()
        return _planner


def proactive_plan(parameters: dict, player=None) -> str:
    """Tool function: query planner status or trigger a suggestion."""
    action = (parameters.get("action") or "status").lower().strip()
    planner = get_planner()

    if action == "status":
        return planner.get_status()

    if action == "suggest":
        text = parameters.get("text") or parameters.get("message") or ""
        if text:
            planner._suggest(text)
            return "Sugerencia enviada."
        return "Falta el texto de la sugerencia."

    if action == "mark":
        planner.mark_interaction()
        return "Interaccion registrada."

    if action == "reset_daily":
        planner._brief_done_today = False
        planner._afternoon_done = False
        planner._evening_done = False
        return "Banderas diarias reiniciadas."

    return planner.get_status()
