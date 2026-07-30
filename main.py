import os
import json
import sys
from pathlib import Path

# GPU Acceleration: leer de config
_gpu_enabled = False
try:
    _cfg_path = Path(__file__).resolve().parent / "config" / "api_keys.json"
    if _cfg_path.exists():
        _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
        _gpu_enabled = _cfg.get("gpu_acceleration", False)
except Exception:
    pass

if _gpu_enabled:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--use-gl=angle --use-angle=default"
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    print("[ONYX] GPU acceleration activada")
else:
    print("[ONYX] GPU acceleration desactivada")

import asyncio
from concurrent.futures import ThreadPoolExecutor
from beta_config import is_pro_tool, check_daily_limit, increment_calls, pro_tool_message, daily_limit_message
import re
import threading
import json
import sys
try:
    import pygetwindow as gw
except ImportError:
    gw = None
from PyQt6.QtCore import QMetaObject, Qt

import traceback
from pathlib import Path

# ── Dedicated thread pool for tool execution — prevents starvation ────────────
_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=min(64, (os.cpu_count() or 4) * 4), thread_name_prefix="onyx-tool")

from datetime import datetime as _dt, timezone as _tz, timedelta as _td
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
except Exception:
    _ZoneInfo = None
_BA_TZ = _dt.now().astimezone().tzinfo


_TZ_CACHE: str | None = None

def _load_tz():
    """Load timezone from api_keys.json config on first call; cached thereafter."""
    global _BA_TZ, _TZ_CACHE
    if _TZ_CACHE is not None:
        return
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        _TZ_CACHE = cfg.get("timezone", "").strip()
        if _TZ_CACHE and _ZoneInfo is not None:
            try:
                _BA_TZ = _ZoneInfo(_TZ_CACHE)
                print(f"[TZ] Timezone loaded: {_TZ_CACHE}")
                return
            except Exception as e:
                print(f"[TZ] Failed to load '{_TZ_CACHE}': {e}")
                import zoneinfo as _zi
                available = _zi.available_timezones()
                tz_lower = _TZ_CACHE.lower()
                for known in available:
                    if known.lower() == tz_lower:
                        _BA_TZ = _ZoneInfo(known)
                        return
                parts = _TZ_CACHE.replace("\\", "/").split("/")
                short = parts[-1].lower() if parts else ""
                for known in available:
                    if known.lower().endswith("/" + short):
                        _BA_TZ = _ZoneInfo(known)
                        return
    except Exception as e:
        print(f"[TZ] Error reading config: {e}")
    _BA_TZ = _dt.now().astimezone().tzinfo
    print(f"[TZ] Using system timezone: {_BA_TZ}")


class _LazyModule:
    """Defers module import until first attribute access."""
    __slots__ = ('_path', '_attr', '_mod')
    def __init__(self, path, attr=None):
        object.__setattr__(self, '_path', path)
        object.__setattr__(self, '_attr', attr)
        object.__setattr__(self, '_mod', None)
    def _load(self):
        if object.__getattribute__(self, '_mod') is None:
            import importlib
            m = importlib.import_module(object.__getattribute__(self, '_path'))
            attr = object.__getattribute__(self, '_attr')
            if attr:
                m = getattr(m, attr)
            object.__setattr__(self, '_mod', m)
    def __getattr__(self, name):
        self._load()
        return getattr(object.__getattribute__(self, '_mod'), name)
    def __call__(self, *args, **kwargs):
        self._load()
        return object.__getattribute__(self, '_mod')(*args, **kwargs)


np = _LazyModule("numpy")
sd = _LazyModule("sounddevice")
genai = _LazyModule("google.genai")
types = _LazyModule("google.genai", "types")
from ui import OnyxUI

def _patch_settings_ui():
    pass

_patch_settings_ui()

from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    shutdown_memory as _shutdown_memory, flush_memory as _flush_memory,
)

try:
    from actions.file_processor import file_processor
except ImportError:
    file_processor = None
try:
    from actions.flight_finder     import flight_finder
except ImportError:
    flight_finder = None
try:
    from actions.open_app          import open_app
except ImportError:
    open_app = None
try:
    from actions.close_app         import close_app
except ImportError:
    close_app = None
try:
    from actions.weather_report    import weather_action
except ImportError:
    weather_action = None
try:
    from actions.send_message      import send_message
except ImportError:
    send_message = None
try:
    from actions.reminder          import reminder
except ImportError:
    reminder = None
try:
    from actions.computer_settings import computer_settings
except ImportError:
    computer_settings = None
try:
    from actions.screen_vision import screen_vision
except ImportError:
    screen_vision = None
try:
    from actions.local_vision import local_vision
except ImportError:
    local_vision = None
try:
    from actions.youtube_video     import youtube_video, saltar_anuncios_youtube
except ImportError:
    youtube_video = None
try:
    from actions.desktop           import desktop_control
except ImportError:
    desktop_control = None
try:
    from actions.browser_control   import browser_control
except ImportError:
    browser_control = None
try:
    from actions.visual_click import visual_click
except ImportError:
    visual_click = None

try:
    from actions.smart_tracker import smart_tracker
except ImportError:
    smart_tracker = None
try:
    from actions.advanced_vision import advanced_vision_agent
except ImportError:
    advanced_vision_agent = None
try:
    from actions.epic_fortnite_control import epic_fortnite_control
except ImportError:
    epic_fortnite_control = None
try:
    from actions.file_controller   import file_controller
except ImportError:
    file_controller = None
try:
    from actions.code_helper       import code_helper
except ImportError:
    code_helper = None
try:
    from actions.dev_agent         import dev_agent
except ImportError:
    dev_agent = None
try:
    from actions.sandbox           import sandbox
except ImportError:
    sandbox = None
try:
    from actions.web_search        import web_search as web_search_action
except ImportError:
    web_search_action = None
try:
    from actions.computer_control  import computer_control
except ImportError:
    computer_control = None
try:
    from actions.game_updater      import game_updater
except ImportError:
    game_updater = None
try:
    from actions.google_calendar   import google_calendar
except ImportError:
    google_calendar = None
try:
    from actions.spotify_control   import spotify_control
except ImportError:
    spotify_control = None
try:
    from actions.media_control     import media_control
except ImportError:
    media_control = None
try:
    from actions.train_onyx        import train_onyx
except ImportError:
    train_onyx = None
try:
    from actions.evolve            import evolve
except ImportError:
    evolve = None
try:
    from actions.rgb_control       import rgb_control
except ImportError:
    rgb_control = None
try:
    from actions.scheduler         import scheduler, start_runner
except ImportError:
    scheduler = None; start_runner = None
try:
    from actions.google_drive      import google_drive
except ImportError:
    google_drive = None
try:
    from actions.gmail_control     import gmail_control
except ImportError:
    gmail_control = None
try:
    from actions.google_maps       import google_maps
except ImportError:
    google_maps = None
try:
    from actions.rules_engine import rules_engine, check_phrase_triggers
    start_rules_runner = None  # removed in v2
    _rules_run_action = None   # removed in v2: check_phrase_triggers runs internally
except ImportError:
    rules_engine = None
    start_rules_runner = None
    check_phrase_triggers = None
    _rules_run_action = None
try:
    from actions.social_media      import social_media
except ImportError:
    social_media = None
try:
    from actions.whatsapp          import whatsapp
except ImportError:
    whatsapp = None
try:
    from actions.user_profile      import user_profile, record_action
except ImportError:
    user_profile = None; record_action = None
try:
    from actions.goals             import goals
except ImportError:
    goals = None
try:
    from actions.git_control       import git_control
except ImportError:
    git_control = None
try:
    from actions.codebase          import codebase
except ImportError:
    codebase = None
try:
    from actions.knowledge_base    import knowledge_base
except ImportError:
    knowledge_base = None
try:
    from actions.windows_settings  import windows_settings
except ImportError:
    windows_settings = None
try:
    from actions.document_creator  import document_creator
except ImportError:
    document_creator = None
try:
    from actions.document_manager  import document_manager
except ImportError:
    document_manager = None
try:
    from actions.web_navigation    import web_navigation
except ImportError:
    web_navigation = None
try:
    from actions.image_generation  import image_generation
except ImportError:
    image_generation = None
try:
    from actions.smart_home        import smart_home
except ImportError:
    smart_home = None
try:
    from actions.system_monitor    import system_monitor
except ImportError:
    system_monitor = None
try:
    from actions.tiktok_analyzer   import tiktok_analyzer
except ImportError:
    tiktok_analyzer = None
try:
    from actions.arca_invoice      import arca_invoice
except ImportError:
    arca_invoice = None
try:
    from actions.terminal_agent    import terminal_agent
except ImportError:
    terminal_agent = None
try:
    from actions.native_ui         import native_ui
except ImportError:
    native_ui = None
try:
    from actions.accessibility          import accessibility, eye_tracking, micro_movement, task_simplify, routine_gamify
except ImportError:
    accessibility = None
    eye_tracking = None
    micro_movement = None
    task_simplify = None
    routine_gamify = None
try:
    from actions.screen_reader          import screen_reader
except ImportError:
    screen_reader = None
try:
    from actions.accessibility_overlay  import accessibility_overlay
except ImportError:
    accessibility_overlay = None
try:
    from actions.morning_brief     import morning_brief, already_briefed_today, mark_briefed
except ImportError:
    morning_brief = None; already_briefed_today = None; mark_briefed = None
try:
    from actions.vision_guardian   import vision_guardian, start as _start_vision_guardian
except ImportError:
    vision_guardian = None; _start_vision_guardian = None
try:
    from actions.openrouter_agent  import openrouter_agent
except ImportError:
    openrouter_agent = None
try:
    from actions.leer_articulo import leer_articulo
except ImportError:
    leer_articulo = None
try:
    from memory.episodic_memory import get_memory
    _episodic_memory = get_memory()
except Exception:
    _episodic_memory = None

try:
    from memory.vector_memory import get_vector_memory
    _vector_memory = get_vector_memory()
except Exception:
    _vector_memory = None
try:
    from memory.context_summarizer import get_summarizer
    _context_summarizer = get_summarizer()
except Exception:
    _context_summarizer = None
try:
    from actions._evaluator import get_evaluator
    _evaluator = get_evaluator()
except Exception:
    _evaluator = None
try:
    from actions._planner import get_planner
    _planner = get_planner()
except Exception:
    _planner = None
try:
    from actions.plugin_loader import get_loader
    _plugin_loader = get_loader()
except Exception:
    _plugin_loader = None
try:
    from memory.proactive_planner import get_planner as get_proactive_planner
    _proactive_planner = get_proactive_planner()
except Exception:
    _proactive_planner = None

try:
    from actions._action_executor import get_runner
    _tool_runner = get_runner()
    # Mark several read-only/safe tools as idempotent so their results get cached
    for _tn in ("screen_analyze", "evolve", "plan_status", "show_stats", "episodic_search",
                "vector_search", "memory_stats", "rules_engine_list", "web_search",
                "google_calendar", "google_maps", "weather_report"):
        try:
            _tool_runner.mark_idempotent(_tn)
        except Exception:
            pass
except Exception:
    _tool_runner = None


def _run_tool_resilient(name: str, args: dict, func):
    """Run a tool callable (zero-arg lambda) via ToolRunner.
    Returns (result, attempts, duration_ms, from_cache)."""
    if _tool_runner is None:
        t0 = __import__("time").perf_counter()
        try:
            r = func()
        except Exception as _e:
            r = f"Tool '{name}' failed: {_e}"
            traceback.print_exc()
        dur = int((__import__("time").perf_counter() - t0) * 1000)
        return r, 1, dur, False
    try:
        return _tool_runner.run(name, args, func, evaluator=_evaluator)
    except Exception as _re:
        return (f"Tool '{name}' failed in resilience wrapper: {_re}", 1, 0, False)


def _global_shutdown_hook():
    """Persist everything before interpreter exit."""
    try:
        _flush_memory()
    except Exception:
        pass
    try:
        _shutdown_memory()
    except Exception:
        pass
    try:
        if _evaluator is not None:
            from actions._evaluator import shutdown_evaluator
            shutdown_evaluator()
    except Exception:
        pass
    try:
        if _vector_memory is not None:
            _vector_memory.save()
    except Exception:
        pass
    try:
        if _episodic_memory is not None:
            _episodic_memory.shutdown()
    except Exception:
        pass


try:
    import atexit as _atexit
    _atexit.register(_global_shutdown_hook)
except Exception:
    _atexit = None



def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LOG_PATH        = BASE_DIR / "onyx.log"

# ── Redirect output to log file (pythonw.exe has no console) ─
try:
    import io as _io
    _log_fh = open(LOG_PATH, "w", encoding="utf-8", buffering=1)

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = [s for s in streams if s is not None]
        def write(self, data):
            for s in self._streams:
                try: s.write(data)
                except Exception: pass
        def flush(self):
            for s in self._streams:
                try: s.flush()
                except Exception: pass
        @property
        def encoding(self): return "utf-8"
        def fileno(self):
            for s in self._streams:
                try: return s.fileno()
                except Exception: pass
            raise _io.UnsupportedOperation("fileno")

    sys.stdout = _TeeStream(sys.stdout, _log_fh)
    sys.stderr = _TeeStream(sys.stderr, _log_fh)
except Exception:
    pass

# ── Suppress console windows from all child subprocesses ─────────────────────
if sys.platform == "win32":
    try:
        import ctypes as _ctypes
        if _ctypes.windll.kernel32.GetConsoleWindow() == 0:
            import subprocess as _sp
            _CREATE_NO_WINDOW = 0x08000000
            _orig_Popen = _sp.Popen
            class _NoCmdPopen(_orig_Popen):
                def __init__(self, *args, **kwargs):
                    kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
                    super().__init__(*args, **kwargs)
            _sp.Popen = _NoCmdPopen
            print("[ONYX] subprocess.Popen patched: CREATE_NO_WINDOW active")
    except Exception as _e:
        print(f"[ONYX] Could not patch subprocess: {_e}")

LIVE_MODEL          = "gemini-2.5-flash-native-audio-latest"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 256      # 16ms chunks — mic input (keep small for low latency)
PLAY_CHUNK_SIZE     = 480      # 20ms chunks — playback (smaller = lower latency)

_cached_api_key: str | None = None

from actions.dictation_processor import process_dictation

def _get_api_key() -> str:
    global _cached_api_key
    if _cached_api_key:
        return _cached_api_key
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        _cached_api_key = json.load(f)["gemini_api_key"]
    return _cached_api_key


ONYX_VOICES = {
    "Aoede":  ("Femenina", "Cálida y sofisticada — ideal para asistente IA"),
    "Kore":   ("Femenina", "Suave y precisa"),
    "Leda":   ("Femenina", "Natural y fluida"),
    "Zephyr": ("Femenina", "Dinámica y expresiva"),
    "Charon": ("Masculina", "Profunda y seria — voz original de ONYX"),
    "Puck":   ("Masculina", "Ágil y versátil"),
    "Fenrir": ("Masculina", "Grave y autoritaria"),
    "Orus":   ("Masculina", "Clásica y equilibrada"),
}

def _get_onyx_voice() -> str:
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("onyx_voice", "Aoede")
    except Exception:
        return "Aoede"


_SYS_PROMPT_CACHE: str | None = None

def _load_system_prompt() -> str:
    global _SYS_PROMPT_CACHE
    if _SYS_PROMPT_CACHE is not None:
        return _SYS_PROMPT_CACHE
    try:
        _SYS_PROMPT_CACHE = PROMPT_PATH.read_text(encoding="utf-8")
        return _SYS_PROMPT_CACHE
    except Exception:
        return (
            "You are ONYX, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


def _expand_punctuation(text: str) -> str:
    _multi = [
        ("punto y coma", ";"),
        ("punto y aparte", ".\n"),
        ("punto y seguido", ". "),
        ("punto final", "."),
        ("dos puntos", ":"),
        ("abrir paréntesis", "("),
        ("cerrar paréntesis", ")"),
        ("abrir corchete", "["),
        ("cerrar corchete", "]"),
        ("abrir llave", "{"),
        ("cerrar llave", "}"),
        ("signo de interrogación", "?"),
        ("signo de exclamación", "!"),
        ("guion bajo", "_"),
        ("guion medio", "-"),
        ("barra invertida", "\\"),
        ("mayor que", ">"),
        ("menor que", "<"),
        ("nueva línea", "\n"),
        ("nuevo párrafo", "\n\n"),
        ("tabulación", "\t"),
    ]
    _multi.sort(key=lambda x: len(x[0]), reverse=True)
    for old, new in _multi:
        text = text.replace(old, new)

    _single = [
        ("coma", ","),
        ("punto", "."),
        ("guion", "-"),
        ("barra", "/"),
        ("comillas", '"'),
        ("comilla", "'"),
        ("porcentaje", "%"),
        ("arroba", "@"),
        ("numeral", "#"),
        ("dólar", "$"),
        ("euro", "€"),
        # ("más", "+"),    # Excluido: muy común como palabra
        ("paréntesis", "()"),
        ("parentesis", "()"),
        # ("menos", "-"),  # Excluido: muy común como palabra
        # ("igual", "="),  # Excluido: muy común como palabra
        ("espacio", " "),
    ]
    for old, new in _single:
        text = re.sub(rf"\b{old}\b", new, text, flags=re.IGNORECASE)

    text = re.sub(r"\s+([.,;:!?)\]}])", r"\1", text)
    text = re.sub(r"([\[({¿¡])\s+", r"\1", text)
    text = re.sub(r"  +", " ", text)
    text = text.strip()

    return text


_CORRECT_RE = re.compile(
    r"(?:corrige|cambia|reemplaza|replace)\s+(.+?)\s+(?:por|con|a|by)\s+(.+)",
    re.IGNORECASE,
)

_EXIT_PHRASES = (
    "modo comando", "salí del dictado", "sal del dictado",
    "para de escribir", "modo comando onyx",
    "apaga modo dictado", "apagar dictado",
    "apaga el dictado", "apaga dictado",
    "apaga dictado ya", "apaga el dictado ya",
    "termina dictado", "finalizar dictado",
    "desactivar dictado", "desactiva dictado",
    "desactiva modo dictado",
    "ya no escribas más", "no escribas más",
    "deja de escribir",
)

# Palabras que aparecen en frases de salida — buffer corto compuesto solo
# de estas se descarta (probable comando partido por VAD)
_EXIT_VOCAB = frozenset(
    w for p in _EXIT_PHRASES for w in p.split()
)


from core.tool_declarations import TOOL_DECLARATIONS
from core.tool_registry import SIMPLE_TOOL_SPECS, build_executor_kwargs, LOCAL_TOOL_NAMES

# Cargar herramientas dinámicas creadas por tool_creator
try:
    _custom_tools_path = BASE_DIR / "actions" / "custom_tools.json"
    if _custom_tools_path.exists():
        _custom_tools = json.loads(_custom_tools_path.read_text(encoding="utf-8"))
        if isinstance(_custom_tools, list):
            for _t in _custom_tools:
                if _t.get("name") not in [td["name"] for td in TOOL_DECLARATIONS]:
                    TOOL_DECLARATIONS.append(_t)
except Exception as _e:
    pass

_OPTIONAL_TOOL_IMPORTS = {
    "close_app": close_app,
    "send_message": send_message,
    "code_helper": code_helper,
    "dev_agent": dev_agent,
    "game_updater": game_updater,
    "file_processor": file_processor,
    "accessibility": accessibility,
    "accessibility_overlay": accessibility_overlay,
    "web_search": web_search_action,
    "leer_articulo": leer_articulo,
    "file_controller": file_controller,
    "codebase": codebase,
    "knowledge_base": knowledge_base,
    "media_control": media_control,
    "train_onyx": train_onyx,
    "evolve": evolve,
}


def _available_tool_declarations() -> list[dict]:
    """Return only tool declarations that can be executed in this install."""
    missing = {name for name, func in _OPTIONAL_TOOL_IMPORTS.items() if func is None}
    if not missing:
        return TOOL_DECLARATIONS

    filtered = [tool for tool in TOOL_DECLARATIONS if tool.get("name") not in missing]
    if len(filtered) != len(TOOL_DECLARATIONS):
        print(f"[ONYX] Herramientas deshabilitadas por modulo faltante: {', '.join(sorted(missing))}")
    return filtered


class OnyxLive:

    def __init__(self, ui: OnyxUI):
        self.ui             = ui
        self.ui._speak_fn   = self.speak  # Link UI speak to session speak
        self.session        = None
        self.is_sleeping    = False
        
        # --- PERMISSION UNLOCK ROUTINE (non-blocking, background threads) ---
        try:
            import os, subprocess, threading
            username = os.environ.get("USERNAME", "")
            user_profile = os.environ.get("USERPROFILE", "")
            if not username or not user_profile:
                raise ValueError("USERNAME/USERPROFILE not set")

            def _run_icacls(path, timeout=60):
                try:
                    if os.path.exists(path):
                        subprocess.run(
                            ["icacls", path, "/grant", f"{username}:(OI)(CI)F", "/T", "/C", "/Q"],
                            capture_output=True, timeout=timeout
                        )
                except Exception:
                    pass

            # Unlock user profile (covers Desktop, Documents, Downloads, OneDrive, etc.)
            threading.Thread(target=_run_icacls, args=(user_profile, 180), daemon=True).start()

            # Unlock specific extra folders
            for extra in ["Downloads", "OneDrive"]:
                p = os.path.join(user_profile, extra)
                if os.path.exists(p):
                    threading.Thread(target=_run_icacls, args=(p, 60), daemon=True).start()
        except Exception as e:
            print(f"[STARTUP] Error en rutina de desbloqueo: {e}")
        self.vosk_recognizer = None
        self.vosk_model = None
        self.vosk_dictation = None
        self.dictation_mode = False
        self._dictation_last_len = 0
        import queue as _q, threading as _thr
        self._dictation_queue = _q.Queue()
        self._dictation_worker_running = True
        def _dw(self=self):
            from actions.office_automation import office_automation
            while self._dictation_worker_running:
                try:
                    p = self._dictation_queue.get(timeout=1)
                    if p is None:
                        break
                    office_automation(p, player=self.ui)
                except _q.Empty:
                    continue
                except Exception:
                    pass
        _thr.Thread(target=_dw, daemon=True).start()
        self._dictation_turn_buf = ""  # accumulate full turn text
        self._exit_pending = False
        try:
            import vosk
            if os.path.exists("config/vosk_model"):
                self.vosk_model = vosk.Model("config/vosk_model")
                self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, 16000)
                print("[ONYX] Modelo Vosk cargado para Modo Suspensión.")
        except Exception as e:
            print(f"[ONYX] No se pudo cargar Vosk: {e}")
        self.audio_in_queue = None
        # Iniciar scheduler en background al arrancar ONYX
        if start_runner is not None:
            start_runner(player=ui, speak=self.speak)
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self.ui.on_text_command = self._on_text_command
        self.ui.on_stop_command = self._on_stop_pressed
        self.ui.on_config_saved = self._apply_config
        self._turn_done_event: asyncio.Event | None = None
        self._api_1011_tool: str | None = None   # tracks tool name when 1011 hits
        self._reconnect_event: asyncio.Event | None = None
        self._first_connect = True  # flag for auto morning brief + guardian start
        self._rule_semaphore = threading.Semaphore(100)  # max 100 concurrent rule threads
        from onyx.brain import Brain
        from core.tool_declarations import TOOL_DECLARATIONS
        from core.tool_registry import LOCAL_TOOL_NAMES
        self.brain = Brain(tool_declarations=TOOL_DECLARATIONS, local_tool_names=LOCAL_TOOL_NAMES)

    def _inject_text(self, text: str):
        """Thread-safe injection of a text message into the current live session."""
        if self._loop and self.session and not self._is_speaking:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )
        if _context_summarizer:
            _context_summarizer.add_turn("user", text)
        if _proactive_planner:
            _proactive_planner.mark_interaction()

    def _apply_config(self, cfg: dict):
        """Called from UI thread when user saves settings. Triggers session reconnect."""
        global _cached_api_key
        _cached_api_key = None  # Invalidate cached key so new one is loaded on reconnect
        print("[ONYX] ⚙️ Config actualizada — reconectando sesión...")
        self.ui.write_log("SYS: Aplicando nueva configuración...")
        if self._reconnect_event and self._loop:
            self._loop.call_soon_threadsafe(self._reconnect_event.set)

    async def _watch_reconnect(self):
        """Task that triggers a graceful reconnect when config changes."""
        if self._reconnect_event:
            await self._reconnect_event.wait()
            raise RuntimeError("Config changed — reconnect requested")

    def _on_text_command(self, text: str):
        if not text or not text.strip():
            return

        # Audio file: process with Gemini Vision (needs the realtime cloud session)
        if text.startswith("[AUDIO_FILE]"):
            if self._loop and self.session:
                m = re.search(r'path=([^\s|]+)', text)
                if m:
                    asyncio.run_coroutine_threadsafe(
                        self._process_audio_file(m.group(1)), self._loop
                    )
            else:
                self.ui.write_log("SYS: No puedo procesar audio sin conexión a la nube.")
            return

        # Check phrase triggers — if one fires, don't also send to the model
        if self._fire_phrase_triggers(text):
            return

        # Delegate to Brain — decide cloud vs local
        if self.brain.has_cloud():
            self.brain.send_to_cloud(text)
        else:
            self._run_local(text)

    def _run_local(self, text: str):
        """Ejecuta procesamiento local (Ollama) en un hilo y actualiza la UI con el resultado."""
        self.ui.write_log(f"Tú: {text}")
        self.ui.set_state("THINKING")

        def _worker():
            try:
                result = self.brain.process_local(text, tool_dispatch_fn=self._dispatch_tool_sync)
            except Exception as e:
                from onyx.brain.interfaces import BrainResult
                result = BrainResult(text=f"Error en el cerebro local: {e}", speak=True, state="LISTENING")

            try:
                self.ui.clear_onyx_response()
            except Exception:
                pass
            self.ui.write_log(f"ONYX (local): {result.text}")
            if result.speak:
                try:
                    self.ui.speak(result.text)
                except Exception:
                    pass
            if result.state and not self.ui.muted:
                self.ui.set_state(result.state)

        threading.Thread(target=_worker, daemon=True).start()

    def _dispatch_tool_sync(self, name: str, args: dict) -> str:
        """Ejecuta una herramienta de forma SINCRÓNICA para el cerebro local (offline).

        Reutiliza el registro de herramientas y la carga dinámica por módulo.
        No usa la nube ni la sesión de Gemini.
        """
        import importlib
        import inspect
        print(f"[ONYX-LOCAL] 🔧 {name}  {args}")
        try:
            if name in SIMPLE_TOOL_SPECS:
                spec = SIMPLE_TOOL_SPECS[name]
                func = globals().get(spec["func"])
                if func is None:
                    module = importlib.import_module(f"actions.{name}")
                    func = getattr(module, spec["func"], None) or getattr(module, name, None)
                if func is None:
                    return f"Herramienta '{name}' no disponible."
                kwargs = build_executor_kwargs(spec, args, self.ui, self.speak)
                r = func(**kwargs)
                return r if spec.get("raw") else (r or spec.get("default", "Hecho."))

            # Carga dinámica genérica (módulo y función con el mismo nombre).
            module = importlib.import_module(f"actions.{name}")
            func = getattr(module, name)
            sig = inspect.signature(func)
            kwargs = {"parameters": args, "player": self.ui}
            if "speak" in sig.parameters:
                kwargs["speak"] = self.speak
            r = func(**kwargs)
            return r or f"Herramienta {name} ejecutada."
        except Exception as e:
            return f"Error en herramienta '{name}': {e}"

    def _on_dictation_text(self, text: str):
        """Write dictated text into Word, or execute voice correction commands."""
        if not text:
            return
        if not getattr(self, "dictation_mode", False):
            return
        # Exit phrase detection (safety net for Vosk/Custom STT paths)
        if any(phrase in text.lower() for phrase in _EXIT_PHRASES):
            self.dictation_mode = False
            self.ui.set_state("LISTENING")
            self.ui.write_log("SYS: 🎙️ Modo comando activado.")
            return
        text = process_dictation(text)


        from actions.office_automation import office_automation
        loop = asyncio.get_event_loop()

        def _exec(action: str, **kw):
            params = {"app": "word", "action": action}
            params.update(kw)
            asyncio.ensure_future(
                loop.run_in_executor(_TOOL_EXECUTOR, lambda: None if not getattr(self, "dictation_mode", False) else office_automation(params, player=self.ui))
            )

        m = _CORRECT_RE.match(text)
        if m:
            old_t = m.group(1).strip()
            new_t = m.group(2).strip()
            if old_t and new_t:
                _exec("buscar_reemplazar", text=old_t, reemplazo=new_t)
            return

        cmd = text.strip().lower()
        if cmd in ("corrige eso", "corrige esto", "borra eso", "borra esto",
                    "quita eso", "quita esto", "saca eso", "saca esto"):
            _exec("borrar", cantidad=3)
            return

        if cmd in ("corrige todo", "borra todo", "limpia", "limpiar", "limpia todo"):
            _exec("escribir_texto", text="", limpiar=True)
            return

        if cmd in ("deshacer", "deshace", "deshace eso", "deshace esto"):
            _exec("tecla", tecla="ctrl_z")
            return

        if cmd in ("rehacer", "rehace", "rehace eso"):
            _exec("tecla", tecla="ctrl_y")
            return

        _exec("escribir_texto", text=text)

    async def _process_audio_file(self, path: str):
        """Transcribe and analyze an audio file via Gemini (separate from realtime session)."""
        try:
            p = Path(path)
            if not p.exists():
                self.ui.write_log(f"❌ Archivo no encontrado: {path}")
                return

            self.ui.set_state("THINKING")
            self.ui.write_log(f"🎵 Procesando audio: {p.name}…")

            data = p.read_bytes()
            ext  = p.suffix.lower().lstrip(".")
            mime_map = {
                "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
                "ogg": "audio/ogg",  "flac": "audio/flac", "aac": "audio/aac",
                "wma": "audio/x-ms-wma", "opus": "audio/opus", "webm": "audio/webm",
            }
            mime = mime_map.get(ext, "audio/mpeg")

            loop = asyncio.get_event_loop()

            def _analyze():
                client = genai.Client(api_key=_get_api_key())
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Content(parts=[
                            types.Part(text=(
                                f"El usuario adjuntó un archivo de audio: '{p.name}'.\n"
                                "1. Transcribí el contenido del audio.\n"
                                "2. Si es música, identificá la canción/artista si podés.\n"
                                "3. Describí brevemente qué contiene.\n"
                                "Respondé en español."
                            )),
                            types.Part(
                                inline_data=types.Blob(data=data, mime_type=mime)
                            ),
                        ])
                    ],
                )
                return resp.text.strip()

            result = await loop.run_in_executor(_TOOL_EXECUTOR, _analyze)
            self.ui.write_log(f"ONYX: {result}")

            # Feed result back into the realtime session so ONYX can speak it
            if self.session:
                await self.session.send_client_content(
                    turns={"parts": [{"text": f"[RESULTADO AUDIO '{p.name}']\n{result}"}]},
                    turn_complete=True
                )

        except Exception as e:
            traceback.print_exc()
            self.ui.write_log(f"❌ Error procesando audio: {e}")
        finally:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    def _fire_phrase_triggers(self, user_text: str) -> bool:
        """
        Check phrase-based automations. Returns True if any trigger fired
        (caller should skip sending the text to Gemini in that case).
        """
        text_lower = user_text.lower()

        # ── Accessibility quick triggers ──────────────────────────────────────
        if any(p in text_lower for p in ["activar seguimiento ocular", "iniciar eye tracking",
                                          "activar control ocular", "encender seguimiento de ojos"]):
            if eye_tracking:
                result = eye_tracking({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener seguimiento ocular", "apagar eye tracking",
                                          "desactivar control ocular"]):
            if eye_tracking:
                result = eye_tracking({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["activar detector de movimientos", "iniciar movimiento",
                                          "activar micromovimientos", "encender control por cabeza"]):
            if micro_movement:
                result = micro_movement({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener detector de movimientos", "apagar micromovimientos"]):
            if micro_movement:
                result = micro_movement({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["simplifica", "simplificar", "dividir en pasos"]):
            for phrase in ["simplifica ", "simplificar ", "dividir en pasos "]:
                if phrase in text_lower:
                    task_text = user_text[len(phrase):].strip()
                    if task_text:
                        if task_simplify:
                            result = task_simplify(task_text)
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ [Simplificado]\n" + result[:300])
                        return True

        if "agregar rutina" in text_lower or "nueva rutina" in text_lower:
            for phrase in ["agregar rutina ", "nueva rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "add", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "completar rutina" in text_lower or "terminar rutina" in text_lower:
            for phrase in ["completar rutina ", "terminar rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "complete", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "mis rutinas" in text_lower or "ver rutinas" in text_lower or "listar rutinas" in text_lower:
            if routine_gamify:
                result = routine_gamify({"action": "list"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ [Rutinas]\n" + result)
            return True

        # ── Dictation mode activation ──────────────────────────────────────
        _dictate_phrases = [
            "escucha", "escuchame", "escuchá", "escuchame",
            "modo dictado", "activa dictado", "activar dictado",
            "escribe esto", "escribí esto", "escribe lo que diga",
            "empezá a escribir", "empezar a escribir",
            "pone atención", "presta atención",
        ]
        if any(p in text_lower for p in _dictate_phrases):
            self.dictation_mode = True
            self.ui.write_log("SYS: 🎤 Modo dictado activado por voz.")
            return True

        # ── User-defined phrase automations (rules_engine v2) ─────────────────
        try:
            if check_phrase_triggers is not None:
                triggered = check_phrase_triggers(user_text, speak_callback=self.speak, limit=5)
                if triggered:
                    for rule in triggered:
                        if not isinstance(rule, dict):
                            continue
                        rid = rule.get("rule_id", "?")
                        atype = rule.get("action_type", "?")
                        matched = rule.get("matched", "")
                        desc = str(rule.get("description", ""))[:120]
                        ok = bool(rule.get("success"))
                        status = "OK" if ok else "SKIP"
                        self.ui.write_log(
                            f"⚡ Regla [{rid}] phrase='{matched}' -> {atype} [{status}] "
                            f"{desc}"
                        )
                    # Si se ejecutaron reglas con "speak_note" o apply_correction,
                    # devolver False para que también pase por Gemini y el usuario
                    # obtenga respuesta. Solo bloquear cuando la regla sea
                    # auto-contenida (memory_store/log_note) y no tenga speak.
                    has_interactive = any(
                        isinstance(r, dict)
                        and r.get("action_type") in ("speak_note", "say", "trigger_evolve")
                        for r in triggered
                    )
                    return bool(has_interactive)
        except Exception as e:
            print(f"[ONYX] phrase trigger error: {e}")

        return False

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"I'm afraid {tool_name} ran into a problem, sir. {short}")

    def _on_stop_pressed(self):
        """Llamado desde el hilo de la UI al presionar DETENER o ESC."""
        self._stop_requested.set()
        self.set_speaking(False)
        self.ui.stop_audio()
        self.ui.write_log("SYS: ⛔ Respuesta detenida.")
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._drain_audio_queue(), self._loop)

    async def _drain_audio_queue(self):
        """Vacía la cola de audio para cortar la reproducción de inmediato."""
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except Exception:
                    break
        self.set_speaking(False)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        # Refresh timezone from config each reconnect
        _load_tz()
        now      = datetime.now(_BA_TZ)
        # Add both 12-hour and 24-hour time to avoid any confusion
        time_str_12 = now.strftime("%A, %d %B %Y — %I:%M:%S %p")
        time_str_24 = now.strftime("%A, %d %B %Y — %H:%M:%S")
        hour_24    = now.hour
        utc_off    = now.strftime("%z")
        tz_name    = str(_BA_TZ)
        if 6 <= hour_24 <= 11:
            greeting = "Buenos días, Señor Cristian."
        elif 12 <= hour_24 <= 18:
            greeting = "Buenas tardes, Señor Cristian."
        else:
            greeting = "Buenas noches, Señor Cristian."
        time_ctx   = (
            f"[CURRENT DATE & TIME]\n"
            f"IMPORTANT: This is the EXACT time right now in the user's local timezone (NOT UTC).\n"
            f"Right now it is: {time_str_24} (24-hour format)\n"
            f"Or in 12-hour format: {time_str_12}\n"
            f"Current hour (24h): {hour_24}\n"
            f"Timezone: {tz_name} (UTC{utc_off})\n"
            f"Unix timestamp: {int(now.timestamp())}\n"
            f"CORRECT GREETING RIGHT NOW: \"{greeting}\"\n"
            f"YOU MUST START YOUR RESPONSE WITH THIS EXACT GREETING.\n"
            f"Do not use any other greeting.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        # Inject episodic memory (relevant past episodes)
        if _episodic_memory:
            try:
                epi_str = _episodic_memory.format_for_prompt()
                if epi_str:
                    parts.append(epi_str)
            except Exception:
                pass
        # Inject vector memory (semantic search across all episodes)
        if _vector_memory:
            try:
                vec_str = _vector_memory.format_for_prompt("", max_chars=4000)
                if vec_str:
                    parts.append(vec_str)
            except Exception:
                pass
        # Inject compressed conversation history (context summarizer)
        if _context_summarizer:
            try:
                ctx_str = _context_summarizer.format_for_prompt()
                if ctx_str:
                    parts.append(ctx_str)
            except Exception:
                pass
        parts.append(sys_prompt)

        # Build SpeechConfig — try to set speaking rate for faster delivery
        _voice_name = _get_onyx_voice()
        _speech_cfg = None
        try:
            _speech_cfg = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=_voice_name
                    )
                )
            )
        except Exception:
            _speech_cfg = None

        cfg_kwargs: dict = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": _available_tool_declarations()}],
        )
        if _speech_cfg:
            cfg_kwargs["speech_config"] = _speech_cfg

        # Speaking rate: faster for lower latency feel
        try:
            cfg_kwargs["output_audio_config"] = types.OutputAudioConfig(
                audio_encoding="LINEAR16",
                speaking_rate=1.35,   # 35% faster — responde más rápido
            )
        except Exception:
            pass

        # Temperature directly on LiveConnectConfig
        # Muy baja = respuestas rápidas y consistentes
        try:
            cfg_kwargs["temperature"] = 0.15
        except Exception:
            pass

        # ── VAD: ultra-fast end-of-speech detection → nada de silencio post-voz ──
        _vad_applied = False
        try:
            cfg_kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                    end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                    prefix_padding_ms=30,
                    silence_duration_ms=200,
                )
            )
            _vad_applied = True
            print("[ONYX] VAD config aplicado (typed)")
        except Exception:
            pass

        if not _vad_applied:
            try:
                cfg_kwargs["realtime_input_config"] = {
                    "automatic_activity_detection": {
                        "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                        "end_of_speech_sensitivity": "END_SENSITIVITY_HIGH",
                        "prefix_padding_ms": 100,
                        "silence_duration_ms": 500,
                    }
                }
                print("[ONYX] VAD config aplicado (dict)")
            except Exception:
                print("[ONYX] VAD config no aplicado")

        # ── Context compression: prevent session degradation over time ────────
        try:
            cfg_kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                trigger_tokens=12000,
                sliding_window=types.SlidingWindow(target_tokens=6000),
            )
        except Exception:
            pass

        # ── Thinking budget: disable model reasoning for lowest latency ─────────
        # Set directly on LiveConnectConfig (generation_config field is deprecated)
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass

        return types.LiveConnectConfig(**cfg_kwargs)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[ONYX] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")



        if name == "shutdown_onyx":
            self.ui.write_log("SYS: Apagando ONYX...")
            # Flush persistence before shutting down
            try:
                _global_shutdown_hook()
            except Exception:
                pass
            # Must quit from Qt main thread — signals are thread-safe
            self.ui._win._shutdown_sig.emit()
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Apagando ONYX. ¡Hasta luego, señor!"}
            )

        if name == "restart_onyx":
            self.ui.write_log("SYS: Reiniciando ONYX...")
            # Flush persistence before restart
            try:
                _global_shutdown_hook()
            except Exception:
                pass
            # Emitir señal de reinicio desde el hilo de la UI
            self.ui._win._restart_sig.emit()
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Reiniciando sistema. Estaré de vuelta en un segundo, Señor Cristian."}
            )

        if name == "modo_voz_avanzado":
            texto = args.get("texto", "")
            estilo = args.get("estilo", "normal")
            intensidad = args.get("intensidad", "normal")
            
            if texto:
                is_whisper = (estilo == "whisper")
                self.ui.speak(texto, whisper=is_whisper, whisper_intensity=intensidad)
                result_msg = f"Modo voz '{estilo}' ({intensidad}) ejecutado."
            else:
                result_msg = "No hay texto para procesar."
            
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": result_msg}
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Memory saved."}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."
        _duration_ms = 0
        _attempts = 0
        _cached = False

        try:
            if name in _OPTIONAL_TOOL_IMPORTS and _OPTIONAL_TOOL_IMPORTS[name] is None:
                result = f"Herramienta '{name}' no disponible: falta el modulo correspondiente en actions."

            elif name in SIMPLE_TOOL_SPECS:
                _spec = SIMPLE_TOOL_SPECS[name]
                _func = globals().get(_spec["func"])
                if _func is None:
                    result = f"Herramienta '{name}' no disponible: falta el modulo correspondiente en actions."
                else:
                    _kwargs = build_executor_kwargs(_spec, args, self.ui, self.speak)
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: _func(**_kwargs))
                    )
                    result = r if _spec.get("raw") else (r or _spec.get("default", "Done."))
            elif name == "open_app":
                r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _run_tool_resilient(name, args, lambda: open_app(parameters=args, response=None, player=self.ui))
                )
                result = r or f"Opened {args.get('app_name')}."

            elif name == "sleep_mode":
                self.is_sleeping = True
                self.ui.stop_audio()
                self.ui.write_log("SYS: 💤 Entrando en suspensión local.")
                self.ui.set_state("MUTED")
                result = "Entrando en suspensión absoluta. Cortando transmisión a la nube hasta escuchar 'ONYX'."

            elif name == "dictation_mode":
                if getattr(self, "session", None) is not None:
                    self.dictation_mode = True
                    self.ui.write_log("SYS: 🎤 Modo dictado activado (transcripción por Gemini). Escribiendo en Word...")
                    result = "Modo dictado activado. Todo lo que digas se escribirá en Word con la máxima precisión. Decí 'modo comando' para salir."
                elif getattr(self, "vosk_model", None) is not None:
                    import vosk
                    self.vosk_dictation = vosk.KaldiRecognizer(self.vosk_model, 16000)
                    self.dictation_mode = True
                    self.ui.write_log("SYS: 🎤 Modo dictado local activado (Vosk offline). Escribiendo en Word...")
                    result = "Modo dictado local activado. Todo lo que digas se escribirá directamente en Word sin usar internet. Decí 'modo comando' para salir."
                else:
                    result = "Error: No hay conexión Gemini ni modelo Vosk disponible. Ejecutá download_vosk.py primero."

            elif name == "visual_click":
                r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _run_tool_resilient(name, args, lambda: visual_click(parameters=args, player=self.ui))
                )
                result = r or "Done."
            elif name == "screen_analyze":
                try:
                    from actions._screen_analyzer import analyze_screen_structure, format_structure_report, ocr_screen, describe_screen_advanced
                    from actions._screen_analyzer import find_text_on_screen as _find_text
                    import pyautogui
                    sa_action = args.get("action", "describe").lower()
                    sa_target = args.get("target", "")
                    if sa_action == "describe":
                        r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                            _TOOL_EXECUTOR,
                            lambda: _run_tool_resilient(name, args, describe_screen_advanced)
                        )
                        result = r
                    elif sa_action == "ocr":
                        texts = ocr_screen()
                        if not texts:
                            result = "No se detecto texto en la pantalla."
                        else:
                            result_lines = [f"Textos detectados ({len(texts)}):"]
                            for t in texts[:40]:
                                result_lines.append(f"  '{t['text']}' en ({t['x']},{t['y']}) conf={t['conf']}%")
                            result = "\n".join(result_lines)
                    elif sa_action == "find":
                        if not sa_target:
                            result = "Necesito el texto a buscar."
                        else:
                            matches = _find_text(sa_target)
                            if not matches:
                                result = f"No encontre '{sa_target}' en la pantalla."
                            else:
                                result_lines = [f"Encontre '{sa_target}' ({len(matches)} coincidencias):"]
                                for m in matches[:10]:
                                    result_lines.append(f"  '{m['text']}' en ({m['x']},{m['y']}) conf={m['conf']}%")
                                result = "\n".join(result_lines)
                    elif sa_action == "click":
                        if not sa_target:
                            result = "Necesito el texto del elemento a cliquear."
                        else:
                            matches = _find_text(sa_target)
                            if not matches:
                                result = f"No encontre '{sa_target}' en la pantalla."
                            else:
                                m = matches[0]
                                pyautogui.moveTo(m["x"], m["y"], duration=0.3)
                                time.sleep(0.1)
                                pyautogui.click()
                                result = f"Cliquee '{m['text']}' en ({m['x']},{m['y']}) via OCR (conf={m['conf']}%)."
                    else:
                        structure = analyze_screen_structure()
                        result = format_structure_report(structure)
                except ImportError as _sae:
                    result = f"screen_analyze no disponible: {_sae}"

            elif name == "screen_agent":
                try:
                    from actions.screen_agent import screen_agent
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: screen_agent(parameters=args, player=self.ui))
                    )
                    result = r or "Done."
                except ImportError as _sae2:
                    result = f"screen_agent no disponible: {_sae2}"

            elif name == "narrar_texto":
                texto = args.get("texto", "")
                if texto:
                    self.ui.speak(texto)
                    result = "Narración iniciada localmente."
                else:
                    result = "No hay texto para narrar."

            elif name == "macros_control":
                from actions.macros_control import macros_control
                r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _run_tool_resilient(name, args, lambda: macros_control(parameters=args, player=self.ui))
                )
                result = r or "Acción de macro completada."

            elif name == "office_control":
                from actions.office_control import office_control
                r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _run_tool_resilient(name, args, lambda: office_control(parameters=args, player=self.ui))
                )
                result = r or "Operación de Office completada."

            elif name == "office_automation":
                from actions.office_automation import office_automation
                _oa_action = args.get("action", "").lower()
                if _oa_action == "escribir_texto" and not getattr(self, "dictation_mode", False):
                    result = "No puedo escribir en Word automaticamente. Decí 'escucha' o 'modo dictado' para activar el modo dictado, y cuando termines decí 'modo comando' para salir."
                else:
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: office_automation(parameters=args, player=self.ui))
                    )
                    result = r or "Operación en tiempo real completada."

            elif name == "send_message":
                r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _run_tool_resilient(name, args, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                )
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "local_vision":
                if local_vision is None:
                    result = "Visión local no disponible."
                else:
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: local_vision(parameters=args, player=self.ui))
                    )
                    result = r or "No pude analizar la pantalla con visión local."

            elif name == "computer_settings":
                action = args.get("action", "")
                if action == "volume" and args.get("value", ""):
                    val = args.get("value", "")
                    try:
                        import pyautogui
                        # Si es un número absoluto (ej: '50')
                        if str(val).isdigit():
                            target = int(val)
                            try:
                                from ctypes import cast, POINTER
                                from comtypes import CoInitialize, CoUninitialize
                                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                                CoInitialize()
                                devices = AudioUtilities.GetSpeakers()
                                interface = devices.Activate(IAudioEndpointVolume._iid_, 1, None)
                                volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
                                # Rango 0.0 a 1.0
                                scalar_vol = max(0.0, min(1.0, target / 100.0))
                                volume_ctrl.SetMasterVolumeLevelScalar(scalar_vol, None)
                                CoUninitialize()
                                result = f"Volumen ajustado al {target}%."
                            except Exception as e:
                                result = f"Error ajustando volumen absoluto: {e}"
                        else:
                            # Comando relativo: up, down, mute
                            if "up" in val.lower() or "subir" in val.lower():
                                pyautogui.press("volumeup", presses=5)
                                result = "Volumen subido."
                            elif "down" in val.lower() or "bajar" in val.lower():
                                pyautogui.press("volumedown", presses=5)
                                result = "Volumen bajado."
                            elif "mute" in val.lower() or "silenciar" in val.lower():
                                pyautogui.press("volumemute")
                                result = "Volumen silenciado."
                            else:
                                result = f"Acción de volumen no reconocida: {val}"
                    except Exception as ve:
                        result = f"Error en control de volumen: {ve}"
                elif action in ("theme", "color", "set_theme", "set_color", "tema", "interfaz", "full_theme", "toda_la_interfaz", "diseño", "change_theme", "poner_color", "cambiar_color"):
                    color_name = args.get("value", args.get("description", "")).strip().lower()
                    known = {"cyan":"cyan","green":"green","red":"red","purple":"purple","gold":"gold","white":"white","pink":"pink","orange":"orange","teal":"teal","indigo":"indigo","lime":"lime",
                             "azul":"cyan","verde":"green","rojo":"red","morado":"purple","dorado":"gold","blanco":"white",
                             "celeste":"cyan","naranja":"orange","negro":"dark",
                             "rainbow":"rainbow","multicolor":"rainbow","arcoiris":"rainbow","arcoíris":"rainbow","arco iris":"rainbow","arco-iris":"rainbow"}
                    mapped = known.get(color_name, color_name)
                    try:
                        applied = self.ui.set_theme(mapped)
                    except Exception as e:
                        applied = ""
                        result = f"Error al cambiar tema: {e}"
                    if applied == "rainbow":
                        result = "Modo arcoíris activado en toda la interfaz y esfera."
                    elif applied:
                        result = f"Tema cambiado a {applied}."
                    else:
                        result = f"Color no reconocido: {color_name}."
                elif action in ("visual_mode", "modo_visual", "sphere_mode", "neural_mode", "modo_diseño", "estilo_visual"):
                    mode = args.get("value", args.get("description", "neural")).strip().lower()
                    mode_map = {"neural": "neural", "neuronal": "neural", "red": "neural",
                                "galaxy": "galaxy", "galaxia": "galaxy", "espiral": "galaxy",
                                "pulse": "pulse", "pulso": "pulse", "latido": "pulse",
                                "aurora": "aurora", "aurora boreal": "aurora",
                                "cortina": "aurora"}
                    mapped_mode = mode_map.get(mode, mode)
                    valid_modes = {"neural", "galaxy", "pulse", "aurora"}
                    if mapped_mode in valid_modes:
                        self.ui.set_visual_mode(mapped_mode)
                        result = f"Modo visual cambiado a {mapped_mode}."
                    else:
                        result = f"Modo visual no reconocido: {mode}. Usa: neural, galaxy, pulse, aurora."
                elif action in ("show_stats", "stats", "synaptic_stats", "mostrar_stats", "mostrar_estadisticas"):
                    self.ui.show_stats()
                    result = "Stats mostrados por 4 segundos."
                elif action in ("set_browser", "browser", "navegador", "default_browser", "preferred_browser"):
                    browser_name = args.get("value", args.get("description", "")).strip().lower()
                    from actions._browser_launch import set_preferred_browser
                    result = set_preferred_browser(browser_name)
                elif action in ("movement", "movimiento", "sphere_movement"):
                    movement = args.get("value", args.get("description", "still")).strip().lower()
                    mov_map = {"still": "still", "quieto": "still", "quiet": "still", "parado": "still",
                               "orbit": "orbit", "orbita": "orbit", "orbital": "orbit", "circular": "orbit",
                               "bob": "bob", "rebote": "bob", "saltar": "bob",
                               "sway": "sway", "balanceo": "sway", "lado": "sway",
                               "drift": "drift", "deriva": "drift", "flotar": "drift", "suave": "drift"}
                    mapped_mov = mov_map.get(movement, movement)
                    valid_mov = {"still", "orbit", "bob", "sway", "drift"}
                    if mapped_mov in valid_mov:
                        self.ui.set_movement(mapped_mov)
                        result = f"Movimiento de esfera cambiado a {mapped_mov}."
                    else:
                        result = f"Movimiento no reconocido: {movement}. Usa: still, orbit, bob, sway, drift."
                elif action in ["window_minimize", "minimize"]:
                    if gw:
                        try:
                            window = gw.getActiveWindow()
                            if window: window.minimize()
                            result = "Ventana minimizada."
                        except Exception as e:
                            result = f"Error al minimizar: {e}"
                    else:
                        result = "Librería pygetwindow no disponible."
                elif action in ["window_maximize", "maximize"]:
                    if gw:
                        try:
                            window = gw.getActiveWindow()
                            if window: window.maximize()
                            result = "Ventana maximizada."
                        except Exception as e:
                            result = f"Error al maximizar: {e}"
                    else:
                        result = "Librería pygetwindow no disponible."
                else:
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                    )
                    result = r or "Done."

            elif name == "sandbox":
                if sandbox is None:
                    result = "Sandbox no disponible."
                else:
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: sandbox(parameters=args, player=self.ui))
                    )
                    result = r or "Sandbox no produjo resultado."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _run_tool_resilient(
                        name, args,
                        lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                    )
                )
                result = r or "Done."

            elif name == "media_control":
                try:
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: media_control(parameters=args, player=self.ui))
                    )
                except Exception:
                    r = None; _attempts = 0; _duration_ms = 0; _cached = False
                result = r or "Done."

            elif name == "train_onyx":
                try:
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: train_onyx(parameters=args, player=self.ui))
                    )
                except Exception:
                    r = None; _attempts = 0; _duration_ms = 0; _cached = False
                result = r or "Entrenado, Señor Cristian."

            elif name == "rgb_control":
                from actions.rgb_control import rgb_control
                r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _run_tool_resilient(name, args, lambda: rgb_control(parameters=args, player=self.ui))
                )
                result = r or "Done."

            elif name == "proactive_plan":
                if _proactive_planner is None:
                    result = "Planificador proactivo no disponible."
                else:
                    from memory.proactive_planner import proactive_plan
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: proactive_plan(parameters=args, player=self.ui))
                    )
                    result = r or "Planificador consultado."

            elif name == "openrouter_agent":
                if openrouter_agent:
                    self.ui.write_log("🤖 Delegando tarea a OpenRouter...")
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(
                            name, args,
                            lambda: openrouter_agent(
                                query=args.get("query", ""),
                                model=args.get("model", "google/gemini-2.5-flash")
                            )
                        )
                    )
                    result = r or "Error al procesar con OpenRouter."
                    if len(str(result)) > 300:
                        print(f"[ONYX] Resultado largo detectado ({len(str(result))} chars). Iniciando narración local.")
                        self.ui.speak(result)
                else:
                    result = "Módulo openrouter_agent no encontrado."

            elif name == "terminal_agent":
                if terminal_agent:
                    self.ui.write_log("⚠️ Ejecutando en Terminal...")
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: terminal_agent(parameters=args, player=self.ui))
                    )
                    result = r or "Comando ejecutado."
                else:
                    result = "Módulo terminal_agent no encontrado."

            elif name == "native_ui":
                if native_ui:
                    self.ui.write_log("💻 UI Nativa en acción...")
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: native_ui(parameters=args, player=self.ui))
                    )
                    result = r or "Acción de UI completada."
                else:
                    result = "Módulo native_ui no encontrado."

            elif name == "onyx_ui_control":
                action_ui = args.get("action", "").lower()
                widget_name = args.get("widget", "").lower()
                if action_ui == "minimize":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showMinimized"):
                            QMetaObject.invokeMethod(self.ui._win, "showMinimized", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "iconify"):
                            self.ui.root.after(0, self.ui.root.iconify)
                        result = "Interfaz de usuario minimizada."
                    except Exception as ui_e:
                        result = f"Error al minimizar: {ui_e}"
                elif action_ui == "restore":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                            QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                            QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                            def _restore():
                                self.ui.root.deiconify()
                                self.ui.root.attributes("-topmost", True)
                                self.ui.root.attributes("-topmost", False)
                            self.ui.root.after(0, _restore)
                        result = "Interfaz de usuario restaurada."
                    except Exception as ui_e:
                        result = f"Error al restaurar: {ui_e}"
                elif action_ui == "hide_all":
                    self.ui.write_log("__hide__")
                    result = "Todos los widgets ocultados."
                elif action_ui in ("show", "hide", "toggle"):
                    if widget_name == "main_window" or not widget_name:
                        if action_ui == "show":
                            try:
                                if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                                    QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                                    QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                                elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                                    def _restore():
                                        self.ui.root.deiconify()
                                        self.ui.root.attributes("-topmost", True)
                                        self.ui.root.attributes("-topmost", False)
                                    self.ui.root.after(0, _restore)
                                result = "Interfaz de usuario restaurada."
                            except Exception as ui_e:
                                result = f"Error al restaurar: {ui_e}"
                        else:
                            self.ui.write_log("__hide__")
                            result = "Todos los widgets ocultados."
                    else:
                        cmd = "__widget_show__" if action_ui in ("show", "toggle") else "__widget_close__"
                        self.ui.write_log(f"{cmd}:{widget_name}")
                        result = f"Widget '{widget_name}' {'mostrado' if 'show' in cmd else 'ocultado'}."
                else:
                    result = f"Acción de UI desconocida: {action_ui}"

            elif name == "plan_task":
                goal = args.get("goal", "")
                if not goal:
                    result = "Necesito una descripcion de la tarea a planificar."
                elif _planner is None:
                    result = "Sistema de planificacion no disponible."
                else:
                    plan = _planner.create_plan(goal)
                    result = f"Plan creado: {goal}. Usa plan_status para ver el progreso. ID: {plan.id}"
                    if _episodic_memory:
                        _episodic_memory.record(
                            user_message=goal,
                            summary=f"Plan creado: {goal}",
                            tags="plan,creado",
                        )
                    if _vector_memory:
                        try:
                            _vector_memory.add(
                                f"Plan creado: {goal}",
                                {
                                    "timestamp": __import__("datetime").datetime.now().isoformat(),
                                    "summary": f"Plan creado: {goal}",
                                    "user_message": goal,
                                    "tags": "plan,creado",
                                    "tool": "planner",
                                },
                            )
                        except Exception:
                            pass

            elif name == "plan_status":
                if _planner is None:
                    result = "Sistema de planificacion no disponible."
                else:
                    plans = _planner.get_active_plans()
                    if not plans:
                        result = "No hay planes activos."
                    else:
                        lines = ["Planes activos:"]
                        for pid, plan in plans.items():
                            lines.append(f"  [{pid}] {plan.goal[:80]} - {plan.status} - {plan.progress()}")
                        result = "\n".join(lines)

            elif name == "evolve_from_telemetry":
                ev_action = str(args.get("action") or args.get("mode") or "analyze").lower()
                ev_target = str(args.get("target") or args.get("tool") or "").strip()
                ev_strategy = str(args.get("strategy") or "balanced").lower()
                try:
                    ev_min_calls = int(args.get("min_calls", 3))
                except Exception:
                    ev_min_calls = 3
                try:
                    ev_threshold = float(args.get("threshold", 5.0))
                except Exception:
                    ev_threshold = 5.0
                try:
                    ev_max_tools = int(args.get("max_tools", 5))
                except Exception:
                    ev_max_tools = 5
                try:
                    from actions.evolve import evolve
                    ev_payload = {
                        "action": ev_action,
                        "target": ev_target,
                        "strategy": ev_strategy,
                        "min_calls": ev_min_calls,
                        "threshold": ev_threshold,
                        "max_tools": ev_max_tools,
                    }
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(
                            name, ev_payload,
                            lambda: evolve(ev_payload, player=self.ui)
                        )
                    )
                    result = r or "Sistema de evolucion no disponible."
                except Exception as _evo_e:
                    result = f"Sistema de evolucion no disponible: {_evo_e}"

            else:
                # Intento de cargar herramienta dinámica (tool_creator u otras)
                import importlib
                import inspect
                try:
                    module = importlib.import_module(f"actions.{name}")
                    func = getattr(module, name)
                    sig = inspect.signature(func)
                    kwargs = {"parameters": args, "player": self.ui}
                    if "speak" in sig.parameters: kwargs["speak"] = self.speak
                    r, _attempts, _duration_ms, _cached = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: _run_tool_resilient(name, args, lambda: func(**kwargs))
                    )
                    result = r or f"Herramienta {name} ejecutada."
                except Exception as dyn_e:
                    result = f"Unknown tool: {name}. (Dynamic load failed: {dyn_e})"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        # Record action for habit learning (fire-and-forget, non-blocking)
        if record_action:
            threading.Thread(target=lambda: record_action(name, args), daemon=True).start()

        # Evaluate tool result (fire-and-forget, non-blocking)
        if _evaluator and name not in ("shutdown_onyx", "restart_onyx"):
            try:
                _evaluator.evaluate(name, result, duration_ms=max(0, int(_duration_ms or 0)))
            except Exception:
                pass

        # Record episode in episodic memory (fire-and-forget)
        if _episodic_memory and name not in ("shutdown_onyx", "restart_onyx", "save_memory"):
            try:
                tool_calls = [{"name": name, "args": args}]
                score = 5
                if _evaluator:
                    ts = _evaluator.get_tool_stats(name)
                    if ts and ts.get("scores"):
                        score = ts["scores"][-1]
                threading.Thread(
                    target=lambda: _episodic_memory.record(
                        tool_calls=tool_calls,
                        tool_results=[{"name": name, "result": str(result)[:200]}],
                        success_score=score,
                        tags=f"tool:{name}",
                    ),
                    daemon=True
                ).start()
                # Also record in vector memory for semantic retrieval
                if _vector_memory:
                    try:
                        _vector_memory.add(
                            f"Tool call: {name} | Args: {json.dumps(args, ensure_ascii=False)[:300]} | Result: {str(result)[:300]}",
                            {
                                "timestamp": __import__("datetime").datetime.now().isoformat(),
                                "summary": f"Used {name} tool",
                                "user_message": json.dumps(args, ensure_ascii=False)[:200],
                                "tags": f"tool:{name}",
                                "tool": name,
                            },
                        )
                    except Exception:
                        pass
            except Exception:
                pass

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        _tags = []
        if _cached: _tags.append("cached")
        if _attempts and _attempts > 1: _tags.append(f"retries={_attempts-1}")
        if _duration_ms: _tags.append(f"{_duration_ms}ms")
        _tag_str = f" [{', '.join(_tags)}]" if _tags else ""
        print(f"[ONYX] 📤 {name}{_tag_str} → {str(result)[:120]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[ONYX] 🎤 Mic iniciado")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if getattr(self, "is_sleeping", False):
                if getattr(self, "vosk_recognizer", None):
                    audio_data = indata.tobytes()
                    if self.vosk_recognizer.AcceptWaveform(audio_data):
                        res = json.loads(self.vosk_recognizer.Result())
                        text = res.get("text", "")
                        if "onyx" in text.lower():
                            self.is_sleeping = False
                            self.ui.set_state("LISTENING")
                            self.ui.write_log("SYS: 🟢 ¡Despierto!")
                            try:
                                import winsound
                                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                            except: pass
                return

            if getattr(self, "dictation_mode", False):
                # Primero probamos el STT personalizado si está activado
                try:
                    from actions.custom_stt import load_config, get_stt_engine
                    cfg = load_config()
                    if cfg.get("enabled"):
                        engine = get_stt_engine()
                        if engine.load_model():
                            audio_data = indata.tobytes()
                            text = engine.recognize_audio(audio_data)
                            text = text.strip()
                            if text:
                                if any(phrase in text.lower() for phrase in _EXIT_PHRASES):
                                    self.dictation_mode = False
                                    self.ui.set_state("LISTENING")
                                    self.ui.write_log("SYS: 🎙️ Modo comando activado.")
                                else:
                                    loop.call_soon_threadsafe(self._on_dictation_text, text)
                            return
                except Exception as e:
                    print(f"[Custom STT] Error: {e}")

                # Usamos Gemini para transcripción (mucho más preciso) si está disponible
                if getattr(self, "session", None) is not None:
                    # El audio fluye a Gemini; la transcripción se maneja en _receive_audio
                    pass
                else:
                    # Sin Gemini - fallback a Vosk offline
                    if getattr(self, "vosk_dictation", None):
                        audio_data = indata.tobytes()
                        # Detectar frase de salida en resultados parciales (respuesta inmediata)
                        if self.vosk_dictation.PartialResult():
                            partial = json.loads(self.vosk_dictation.PartialResult())
                            partial_text = partial.get("partial", "").lower().strip()
                            if partial_text and any(phrase in partial_text for phrase in _EXIT_PHRASES):
                                self.dictation_mode = False
                                self.ui.set_state("LISTENING")
                                self.ui.write_log("SYS: 🎙️ Modo comando activado.")
                        if self.vosk_dictation.AcceptWaveform(audio_data):
                            res = json.loads(self.vosk_dictation.Result())
                            text = res.get("text", "").strip()
                            if text:
                                if any(phrase in text.lower() for phrase in _EXIT_PHRASES):
                                    self.dictation_mode = False
                                    self.ui.set_state("LISTENING")
                                    self.ui.write_log("SYS: 🎙️ Modo comando activado.")
                                else:
                                    loop.call_soon_threadsafe(self._on_dictation_text, text)
                    return

            with self._speaking_lock:
                onyx_speaking = self._is_speaking
            if not onyx_speaking and not self.ui.muted:
                # Calculate RMS audio level for sphere visualization
                try:
                    rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
                    self.ui.set_audio_level(min(1.0, rms * 18))
                except Exception:
                    pass
                data = indata.tobytes()
                # Silently drop if queue is full (during long tool calls)
                def _safe_put(q, item):
                    try:
                        q.put_nowait(item)
                    except Exception:
                        pass  # Queue full — discard; prevents QueueFull crash
                loop.call_soon_threadsafe(
                    _safe_put, self.out_queue, {"data": data, "mime_type": "audio/pcm"}
                )
            elif onyx_speaking:
                # When ONYX is speaking, also update level (from playback perspective)
                try:
                    rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
                    self.ui.set_audio_level(min(1.0, rms * 15))
                except Exception:
                    pass

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[ONYX] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.03)  # 30ms — balance responsividad/CPU
        except Exception as e:
            print(f"[ONYX] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[ONYX] 👂 Recv iniciado")
        out_buf, in_buf = [], []
        _first_chunk   = True
        _last_tool     = None   # track which tool was executing when error hit

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if not self._stop_requested.is_set() and not getattr(self, "dictation_mode", False):
                            self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                if not getattr(self, "dictation_mode", False):
                                    if _first_chunk:
                                        self.ui.clear_onyx_response()
                                        _first_chunk = False
                                    self.ui.stream_onyx_chunk(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            raw_txt = sc.input_transcription.text
                            # Remove control chars but DON'T strip — positions must align
                            _t = _CTRL_RE.sub("", raw_txt)
                            _t = re.sub(r"[\x00-\x08\x0b-\x1f]", "", _t)
                            txt = _t.strip()  # stripped for display / OOB matching
                            if txt:
                                self._last_in_text = txt  # latest cumulative text for logging
                                # Check voice activation for dictation mode
                                if not getattr(self, "dictation_mode", False):
                                    _activate_phrases = [
                                        "escucha", "escuchame", "escuchá", "escuchame",
                                        "modo dictado", "activa dictado", "activar dictado",
                                        "escribe esto", "escribí esto", "escribe lo que diga",
                                        "empezá a escribir", "empezar a escribir",
                                        "pone atención", "presta atención",
                                    ]
                                    if any(p in txt.lower() for p in _activate_phrases):
                                        self.dictation_mode = True
                                        # Skip only the activation phrase itself, not the dictation text
                                        _t_lower = _t.lower()
                                        _match_end = 0
                                        for p in _activate_phrases:
                                            idx = _t_lower.find(p)
                                            if idx >= 0:
                                                end = idx + len(p)
                                                if end > _match_end:
                                                    _match_end = end
                                        if _match_end < len(_t) and _t[_match_end] == ' ':
                                            _match_end += 1
                                        self._dictation_last_len = _match_end
                                        self.ui.write_log("SYS: 🎤 Modo dictado activado por voz.")
                                 # Streaming dictation: accumulate delta until turn_complete
                                if getattr(self, "dictation_mode", False):
                                    prev_len = self._dictation_last_len
                                    if not getattr(self, "_exit_pending", False) and len(_t) > prev_len:
                                        delta = _t[prev_len:]
                                        self._dictation_turn_buf += delta
                                        self._dictation_last_len = len(_t)
                                    # Detect exit phrase early to stop accumulation
                                    if not getattr(self, "_exit_pending", False) and any(phrase in txt.lower() for phrase in _EXIT_PHRASES):
                                        self._exit_pending = True
                                        self.ui.set_state("LISTENING")
                                        self.ui.write_log("SYS: 🎙️ Modo comando activado.")

                        if sc.turn_complete:
                            self._stop_requested.clear()
                            if self._turn_done_event:
                                self._turn_done_event.set()
                            full_in = getattr(self, "_last_in_text", "")
                            if full_in:
                                self.ui.write_log(f"Tú: {full_in}")
                                if getattr(self, "dictation_mode", False):
                                    buf = self._dictation_turn_buf.strip()
                                    _exit_now = getattr(self, "_exit_pending", False)
                                    # Safety net: check full_in for exit phrases
                                    if not _exit_now:
                                        _fl = full_in.lower()
                                        for phrase in _EXIT_PHRASES:
                                            if phrase in _fl:
                                                _exit_now = True
                                                break
                                    # Also: short buffer of command vocabulary
                                    if not _exit_now and buf:
                                        _words = buf.split()
                                        if len(_words) <= 5 and all(w.lower() in _EXIT_VOCAB for w in _words):
                                            _exit_now = True
                                            buf = ""
                                    if _exit_now and buf:
                                        # Strip exit phrase from buffer
                                        _bl = buf.lower()
                                        for phrase in _EXIT_PHRASES:
                                            idx = _bl.find(phrase)
                                            if idx >= 0:
                                                buf = buf[:idx].strip()
                                                break
                                    if _exit_now:
                                        if buf:
                                            buf = process_dictation(buf)
                                            _p = {"app": "word", "action": "escribir_texto", "text": buf}
                                            self._dictation_queue.put(_p)
                                        self.dictation_mode = False
                                        self.ui.set_state("LISTENING")
                                        self.ui.write_log("SYS: 🎙️ Modo comando activado.")
                                    else:
                                        if buf:
                                            buf = process_dictation(buf)
                                            _p = {"app": "word", "action": "escribir_texto", "text": buf}
                                            self._dictation_queue.put(_p)
                                    self._dictation_last_len = 0
                                    self._dictation_turn_buf = ""
                                    self._exit_pending = False
                                else:
                                    self._fire_phrase_triggers(full_in)
                            if _context_summarizer:
                                if full_in:
                                    _context_summarizer.add_turn("user", full_in)
                                    if _proactive_planner:
                                        _proactive_planner.mark_interaction()
                                if out_buf:
                                    _context_summarizer.add_turn("assistant", " ".join(out_buf))
                            in_buf = []
                            out_buf = []
                            self._last_in_text = ""
                            _first_chunk = True

                    if response.tool_call:
                        self.ui.clear_onyx_response()
                        _first_chunk = True
                        fcs = response.tool_call.function_calls
                        for fc in fcs:
                            print(f"[ONYX] 📞 {fc.name}")
                            _last_tool = fc.name
                        # Execute all tool calls in parallel when there are multiple
                        if len(fcs) > 1:
                            tasks = [asyncio.create_task(self._execute_tool(fc)) for fc in fcs]
                            fn_responses = list(await asyncio.gather(*tasks))
                        else:
                            fn_responses = [await self._execute_tool(fcs[0])]
                        try:
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                            _last_tool = None  # only clear AFTER successful send
                        except Exception as tool_err:
                            print(f"[ONYX] ❌ send_tool_response failed: {tool_err}")
                            raise
        except Exception as e:
            msg  = str(e)
            code = getattr(e, "status_code", 0) or getattr(e, "code", 0) or 0
            # Detect 1011 (internal server error) regardless of exception type
            if code == 1011 or "1011" in msg or "Internal error" in msg:
                tool_info = f" durante '{_last_tool}'" if _last_tool else ""
                print(f"[ONYX] ⚡ API 1011{tool_info} — reconectando...")
                self._api_1011_tool = _last_tool
            else:
                print(f"[ONYX] ❌ Recv: {e}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print(f"[ONYX] 🔊 Play iniciado (default device: {sd.default.device})")

        stream: sd.RawOutputStream | None = None
        _jitter_buf: list[bytes] = []
        _JITTER_TARGET = 1

        def _ensure_stream():
            nonlocal stream
            if stream is None:
                s = sd.RawOutputStream(
                    samplerate=RECEIVE_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=PLAY_CHUNK_SIZE,
                )
                s.start()
                stream = s

        def _close_stream():
            nonlocal stream
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                stream = None

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.05
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        for buffered in _jitter_buf:
                            if stream:
                                await asyncio.to_thread(stream.write, buffered)
                        _jitter_buf.clear()
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                        _close_stream()
                    continue

                self.set_speaking(True)
                _ensure_stream()
                _jitter_buf.append(chunk)

                if len(_jitter_buf) >= _JITTER_TARGET and stream:
                    for buffered in _jitter_buf:
                        await asyncio.to_thread(stream.write, buffered)
                    _jitter_buf.clear()
        except asyncio.CancelledError:
            print("[ONYX] 🔊 Play cancelado.")
            raise
        except Exception as e:
            print(f"[ONYX] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            _close_stream()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        reconnect_delay   = 1.0
        consecutive_fails = 0

        while True:
            try:
                print("[ONYX] 🔌 Conectando...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.brain.set_cloud_session(session, self._loop)
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=5)  # buffer moderado — evita drops durante ráfagas de mic
                    self._turn_done_event = asyncio.Event()
                    self._reconnect_event = asyncio.Event()

                    print("[ONYX] ✅ Conectado.")
                    self.ui.write_log("SYS: ONYX en línea.")
                    reconnect_delay   = 1.0   # reset backoff on successful connection
                    consecutive_fails = 0
                    self._api_1011_tool = None   # clear 1011 tool tracker
                    self._offline_notified = False  # volvió la nube: salir de modo local

                    # ── First-connect extras ──────────────────────────────────
                    if self._first_connect:
                        self._first_connect = False

                        # Start plugin loader to watch for new custom tools
                        if _plugin_loader:
                            try:
                                current_names = {td["name"] for td in _available_tool_declarations()}
                                new_tools = _plugin_loader.get_new_tools(current_names)
                                if new_tools:
                                    print(f"[ONYX] Plugin loader: {len(new_tools)} herramientas nuevas encontradas")
                                _plugin_loader.start_auto_reload()
                            except Exception as _ple:
                                print(f"[ONYX] Plugin loader init error: {_ple}")

                        # Vision Guardian desactivado por defecto
                        # Activarlo manualmente con: 'ONYX, activá el Guardian de Visión'
                        # Start Proactive Planner
                        if _proactive_planner:
                            try:
                                _proactive_planner.start(
                                    inject_fn=self._inject_text,
                                    speaking_fn=lambda: self._is_speaking,
                                )
                            except Exception as _ppe:
                                print(f"[ONYX] ProactivePlanner init error: {_ppe}")
                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._watch_reconnect())

                    self.ui.set_state("LISTENING")

            except Exception as e:
                exceptions = e.exceptions if isinstance(e, ExceptionGroup) else [e]

                is_handshake_timeout = False
                is_config_reconnect  = False
                for exc in exceptions:
                    msg = str(exc)
                    if "Config changed" in msg:
                        # Intentional reconnect triggered by config change — fast, no backoff
                        is_config_reconnect = True
                        consecutive_fails = 0
                    elif "timed out during opening handshake" in msg or (
                        isinstance(exc, TimeoutError) and "handshake" in msg
                    ):
                        # Timeout de WebSocket al conectar — error de red transitorio.
                        # NO incrementar consecutive_fails: sólo reintento rápido.
                        is_handshake_timeout = True
                        print(f"[ONYX] ⏱️ Timeout al conectar — reintentando en 1s...")
                    elif "1011" in msg or "Internal error" in msg:
                        tool_hint = self._api_1011_tool or ""
                        print(f"[ONYX] ⚡ API 1011{tool_hint and ' durante '+tool_hint} — reconectando...")
                        consecutive_fails += 1
                        if consecutive_fails >= 4:
                            self.ui.write_log(
                                "SYS: ⚠️ Error 1011 repetido. Esperando para no saturar la API...\n"
                                "SYS: Si persiste más de 2 min, reiniciá ONYX."
                            )
                        elif tool_hint:
                            self.ui.write_log(f"SYS: Error de servidor al ejecutar '{tool_hint}'. Reconectando...")
                        else:
                            self.ui.write_log("SYS: Error de servidor 1011. Reconectando...")
                    elif "RESOURCE_EXHAUSTED" in msg or "429" in msg or "exceeded your current quota" in msg.lower():
                        # Cuota de la API agotada — pasar a modo LOCAL y avisar una sola vez.
                        consecutive_fails += 1
                        if not getattr(self, "_offline_notified", False):
                            self._offline_notified = True
                            self.ui.write_log(
                                "SYS: ⚠️ Cuota de Gemini agotada. ONYX pasa a MODO LOCAL.\n"
                                "SYS: Escribime por texto y te respondo con el cerebro local (Ollama)."
                            )
                            try:
                                self.ui.speak(
                                    "Señor Cristian, el servicio en la nube agotó su cuota. "
                                    "Paso a modo local. Escribime por texto y te respondo igual."
                                )
                            except Exception:
                                pass
                        else:
                            print("[ONYX] 💤 Cuota agotada — reintento espaciado (modo local activo).")

                    elif "1008" in msg or "policy violation" in msg.lower() or "not found for API version" in msg:
                        # Model not available / wrong API version — log clearly, retry with same model
                        print(f"[ONYX] ⚠️ Modelo no disponible en esta versión de API: {msg[:120]}")
                        self.ui.write_log("SYS: ⚠️ Modelo no disponible. Reintentando...")
                        consecutive_fails += 1
                        # Model not available / wrong API version — log clearly, retry with same model
                        print(f"[ONYX] ⚠️ Modelo no disponible en esta versión de API: {msg[:120]}")
                        self.ui.write_log("SYS: ⚠️ Modelo no disponible. Reintentando...")
                        consecutive_fails += 1
                    elif "1000" in msg or "going away" in msg.lower():
                        # Cierre normal de la sesión (expiró ~15 min) — silencioso
                        print(f"[ONYX] 🔄 Sesión expirada — reconectando...")
                        consecutive_fails = 0   # reset: no es un fallo
                    else:
                        print(f"[ONYX] ⚠️ {exc}")
                        traceback.print_exc()
                        consecutive_fails += 1

                if is_config_reconnect:
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(0.5)
                    continue

                if is_handshake_timeout:
                    # Timeout en handshake → reintento fijo de 1s, sin backoff
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(1.0)
                    continue

            self.set_speaking(False)
            self.ui.set_state("THINKING")

            # Exponential backoff con jitter para evitar thundering herd
            # After 5+ fails: wait up to 90s to let API rate limits recover
            if getattr(self, "_offline_notified", False):
                # Cuota agotada: reintentos muy espaciados (la cuota se recupera con el tiempo).
                reconnect_delay = 30.0
            elif consecutive_fails > 1:
                max_delay = 5.0 if consecutive_fails >= 5 else 2.0
                reconnect_delay = min(reconnect_delay * 2, max_delay)
            elif consecutive_fails == 0:
                reconnect_delay = 1.0

            import random as _rnd
            jitter = _rnd.uniform(0, reconnect_delay * 0.25)
            total  = reconnect_delay + jitter
            print(f"[ONYX] 🔄 Reconectando en {total:.1f}s...")
            await asyncio.sleep(total)

def main():
    # ── Single Instance Lock ──────────────────────────────────────────────────
    import ctypes
    global _single_instance_mutex
    _single_instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ONYX_AI_SINGLE_INSTANCE_MUTEX")
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        print("[ONYX] Ya hay una instancia en ejecución. Cerrando.")
        sys.exit(0)

    # ── License check ─────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────

    # Load timezone from config
    _load_tz()

    def _ensure_both_api_keys():
        cfg = {}
        if API_CONFIG_PATH.exists():
            try:
                cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        gemini = cfg.get("gemini_api_key", "").strip()
        openrouter = cfg.get("openrouter_api_key", "").strip()
        
        if gemini and openrouter:
            return
            
        from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
        from PyQt6.QtCore import Qt
        
        # We need an app instance before dialogs
        app = QApplication.instance() or QApplication(sys.argv)
        
        dialog = QDialog()
        dialog.setWindowTitle("Configuración Inicial de ONYX")
        dialog.resize(450, 250)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        layout = QVBoxLayout(dialog)
        
        lbl_info = QLabel("¡Bienvenido a ONYX!\n\nPor favor, ingresa tus API keys para continuar.\nEstas se guardarán localmente y de forma segura.")
        lbl_info.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_info)
        
        lbl_gemini = QLabel("Gemini API Key:")
        layout.addWidget(lbl_gemini)
        inp_gemini = QLineEdit()
        inp_gemini.setText(gemini)
        inp_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(inp_gemini)
        
        lbl_openrouter = QLabel("OpenRouter API Key:")
        layout.addWidget(lbl_openrouter)
        inp_openrouter = QLineEdit()
        inp_openrouter.setText(openrouter)
        inp_openrouter.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(inp_openrouter)
        
        btn_save = QPushButton("Guardar y Continuar")
        btn_save.setStyleSheet("background-color: #0078D7; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
        layout.addWidget(btn_save)
        
        def on_save():
            g = inp_gemini.text().strip()
            o = inp_openrouter.text().strip()
            if not g or not o:
                QMessageBox.warning(dialog, "Error", "Ambas claves son obligatorias.")
                return
            cfg["gemini_api_key"] = g
            cfg["openrouter_api_key"] = o
            API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            API_CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
            dialog.accept()
            
        btn_save.clicked.connect(on_save)
        
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted:
            sys.exit(0)

    _ensure_both_api_keys()

    ui = OnyxUI("face.png")

    # --- UI COSMETICS PATCH ---
    try:
        if hasattr(ui, "_win"):
            # Aumentar transparencia (Glassmorphism)
            ui._win.setWindowOpacity(0.85)
            # Reemplazar textos "Beta" y "Gratuito"
            from PyQt6.QtWidgets import QLabel
            for label in ui._win.findChildren(QLabel):
                text_lower = label.text().lower()
                if "beta" in text_lower or "gratuita" in text_lower or "gratuito" in text_lower or "premium" in text_lower:
                    try:
                        # Ocultar el contenedor completo del banner (incluye el botón PRO)
                        label.parentWidget().hide()
                    except:
                        label.hide()

            # 2. Add keyboard shortcut & Global Hotkey (INS / Insert key) to wake up ONYX
            from PyQt6.QtGui import QKeySequence, QShortcut
            from PyQt6.QtCore import Qt, QTimer

            def on_shortcut_triggered():
                # Wake up / unmute ONYX
                if hasattr(ui, "_win"):
                    # Si está muteado, desmutearlo para que escuche
                    if getattr(ui, "muted", False):
                        if hasattr(ui._win, "_toggle_mute"):
                            ui._win._toggle_mute()
                            ui.write_log("SYS: 🎤 Micrófono ACTIVADO vía atajo INS.")
                    else:
                        # Si ya está activo, mostrar/restaurar la ventana principal y enfocarla
                        if hasattr(ui._win, "showNormal"):
                            ui._win.showNormal()
                            ui._win.activateWindow()
                            ui.write_log("SYS: 🔔 ONYX en foco vía atajo INS.")
                        
                        # Cambiar estado visual a escuchando
                        try:
                            ui.set_state("LISTENING")
                        except:
                            pass

            # A. PyQt Window Shortcut (for local window events)
            local_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Insert), ui._win)
            local_shortcut.activated.connect(on_shortcut_triggered)

            # B. Win32 Native Global Hotkey Hook (for background capture)
            def setup_global_hotkey():
                import threading
                import ctypes
                import ctypes.wintypes

                def hotkey_thread():
                    user32 = ctypes.windll.user32
                    # MOD_NOREPEAT = 0x4000
                    # VK_INSERT = 0x2D
                    try:
                        if not user32.RegisterHotKey(None, 99, 0x0000, 0x2D):
                            print("[HOTKEY] Error registering global Insert hotkey.")
                            return
                    except Exception as e:
                        print(f"[HOTKEY] Exception registering global hotkey: {e}")
                        return

                    try:
                        msg = ctypes.wintypes.MSG()
                        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                            if msg.message == 0x0312: # WM_HOTKEY
                                if msg.wParam == 99:
                                    # Thread-safely trigger UI callback inside PyQt event loop
                                    QTimer.singleShot(0, on_shortcut_triggered)
                            user32.TranslateMessage(ctypes.byref(msg))
                            user32.DispatchMessageW(ctypes.byref(msg))
                    finally:
                        user32.UnregisterHotKey(None, 99)

                threading.Thread(target=hotkey_thread, daemon=True).start()

            setup_global_hotkey()
            print("[PATCH] Avengers: Age of Ultron golden aesthetics & Insert global hotkey loaded successfully!")

    except Exception as e:
        print(f"[PATCH] Cosmetics & Shortcut patch failed: {e}")

    def runner():
        ui.wait_for_api_key()
        onyx = OnyxLive(ui)
        try:
            asyncio.run(onyx.run())
        except KeyboardInterrupt:
            print("\n🔴 Apagando...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
