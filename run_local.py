"""ONYX Modo Local — 100% offline con Ollama + Vosk + edge-tts.
Ejecutar: python run_local.py
"""
import os, sys, json, time, queue, threading, asyncio, tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

# ── Importar UI ──
from ui import OnyxUI
from actions.local_brain import get_brain

# ── Config ──
CONFIG = json.loads((BASE_DIR / "config" / "api_keys.json").read_text(encoding="utf-8"))
VOICE_NAME = CONFIG.get("onyx_voice", "Charon")
OLLAMA_MODEL = CONFIG.get("ollama_model", "qwen3.5:2b")

# ── Estado global ──
_running = True
_speaking = False
_input_queue: queue.Queue = queue.Queue()
_tool_executor = None
_ui = None
_brain = None

# ── Cargar TOOL_DECLARATIONS (sin ejecutar main.py) ──
def _load_tool_declarations():
    """Lee TOOL_DECLARATIONS del archivo main.py sin importarlo."""
    import ast
    main_py = BASE_DIR / "main.py"
    content = main_py.read_text(encoding="utf-8")
    # Buscar la asignación TOOL_DECLARATIONS = [...]
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOOL_DECLARATIONS":
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        pass
    print("[LOCAL] No se pudo parsear TOOL_DECLARATIONS. Usando lista vacía.")
    return []

# ── Importar herramientas dinámicamente ──
_IMPORT_MAP = {
    "open_app": ("actions.open_app", "open_app"),
    "close_app": ("actions.close_app", "close_app"),
    "weather_report": ("actions.weather_report", "weather_action"),
    "web_search": ("actions.web_search", "web_search"),
    "browser_control": ("actions.browser_control", "browser_control"),
    "computer_settings": ("actions.computer_settings", "computer_settings"),
    "computer_control": ("actions.computer_control", "computer_control"),
    "file_controller": ("actions.file_controller", "file_controller"),
    "desktop_control": ("actions.desktop", "desktop_control"),
    "youtube_video": ("actions.youtube_video", "youtube_video"),
    "saltar_anuncios_youtube": ("actions.youtube_video", "saltar_anuncios_youtube"),
    "spotify_control": ("actions.spotify_control", "spotify_control"),
    "reminder": ("actions.reminder", "reminder"),
    "screen_process": ("actions.screen_vision", "screen_vision"),
    "local_vision": ("actions.local_vision", "local_vision"),
    "visual_click": ("actions.visual_click", "visual_click"),
    "smart_tracker": ("actions.smart_tracker", "smart_tracker"),
    "vision_guardian": ("actions.vision_guardian", "vision_guardian"),
    "whatsapp": ("actions.whatsapp", "whatsapp"),
    "native_ui": ("actions.native_ui", "native_ui"),
    "rgb_control": ("actions.rgb_control", "rgb_control"),
    "system_monitor": ("actions.system_monitor", "system_monitor"),
    "terminal_agent": ("actions.terminal_agent", "terminal_agent"),
    "narrar_texto": ("actions.custom_tts", "custom_tts_speak"),
    "leer_articulo": ("actions.leer_articulo", "leer_articulo"),
    "macros_control": ("actions.macros_control", "macros_control"),
    "sandbox": ("actions.sandbox", "sandbox"),
    "proactive_plan": ("memory.proactive_planner", "proactive_plan"),
    "user_profile": ("actions.user_profile", "user_profile"),
    "goals": ("actions.goals", "goals"),
    "knowledge_base": ("actions.knowledge_base", "knowledge_base"),
    "windows_settings": ("actions.windows_settings", "windows_settings"),
    "morning_brief": ("actions.morning_brief", "morning_brief"),
    "scheduler": ("actions.scheduler", "scheduler"),
    "rules_engine": ("actions.rules_engine", "rules_engine"),
    "git_control": ("actions.git_control", "git_control"),
    "codebase": ("actions.codebase", "codebase"),
    "gmail_control": ("actions.gmail_control", "gmail_control"),
    "web_navigation": ("actions.web_navigation", "web_navigation"),
    "self_edit": ("actions.self_edit", "self_edit"),
    "tool_creator": ("actions.tool_creator", "tool_creator"),
}

_tool_cache = {}

def _load_tool(name):
    if name in _tool_cache:
        return _tool_cache[name]
    if name not in _IMPORT_MAP:
        # Dynamic import attempt
        try:
            mod = __import__(f"actions.{name}", fromlist=[name])
            fn = getattr(mod, name, None)
            if fn:
                _tool_cache[name] = fn
                return fn
        except Exception:
            pass
        return None
    module_path, func_name = _IMPORT_MAP[name]
    try:
        mod = __import__(module_path, fromlist=[func_name])
        fn = getattr(mod, func_name, None)
        _tool_cache[name] = fn
        return fn
    except Exception:
        return None

# ── Tool dispatcher ──
def _dispatch_tool(name: str, args: dict) -> str:
    if _ui:
        _ui.write_log(f"🔧 {name}  {args}")
        _ui.set_state("THINKING")

    fn = _load_tool(name)
    if fn is None:
        return f"Herramienta {name} no disponible en modo local."

    try:
        result = fn(parameters=args, player=_ui)
        result = result or f"{name} ejecutada."
        if _ui:
            _ui.write_log(f"✅ {name} → {str(result)[:100]}")
        return result
    except Exception as e:
        err = f"Error en {name}: {e}"
        if _ui:
            _ui.write_log(f"❌ {err}")
        return err

# ── edge-tts local ──
def _speak(text: str):
    global _speaking
    _speaking = True
    if _ui:
        _ui.set_state("SPEAKING")
        _ui._speak_local(text)
    # Wait for speaking to finish (approximate)
    time.sleep(max(0.5, len(text) * 0.06))
    _speaking = False
    if _ui:
        _ui.set_state("LISTENING")

# ── Vosk listener ──
def _vosk_listener():
    global _running
    try:
        import vosk
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("[LOCAL] Vosk/sounddevice no instalado. Usá entrada por teclado.")
        while _running:
            try:
                text = input(">> ")
                if text.strip():
                    _input_queue.put(text.strip())
            except (EOFError, KeyboardInterrupt):
                break
        return

    model_path = str(BASE_DIR / "config" / "vosk_model")
    if not os.path.exists(model_path):
        print("[LOCAL] Vosk model not found. Run download_vosk.py first.")
        print("[LOCAL] Fallback a entrada por teclado.")
        while _running:
            try:
                text = input(">> ")
                if text.strip():
                    _input_queue.put(text.strip())
            except (EOFError, KeyboardInterrupt):
                break
        return

    try:
        model = vosk.Model(model_path)
        rec = vosk.KaldiRecognizer(model, 16000)
        print(f"[LOCAL] Vosk listo. Escuchando...")

        def callback(indata, frames, time_info, status):
            nonlocal rec
            if _speaking or not _running:
                return
            try:
                data = bytes(indata)
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text and len(text) > 2:
                        _input_queue.put(text)
            except Exception as e:
                print(f"[LOCAL] Vosk callback error: {e}")

        with sd.RawInputStream(samplerate=16000, blocksize=8000, channels=1,
                                dtype="int16", callback=callback):
            while _running:
                sd.sleep(100)

    except Exception as e:
        print(f"[LOCAL] Error en Vosk: {e}")
        print("[LOCAL] Fallback a entrada por teclado.")
        while _running:
            try:
                text = input(">> ")
                if text.strip():
                    _input_queue.put(text.strip())
            except (EOFError, KeyboardInterrupt):
                break

# ── Main loop ──
def _local_loop():
    global _brain, _running
    brain = get_brain(OLLAMA_MODEL)

    tool_decls = _load_tool_declarations()
    brain.set_tools(tool_decls)

    # Pre-warm model (cold start loading)
    print(f"[LOCAL] Pre-calentando modelo {OLLAMA_MODEL}...")
    if _ui:
        _ui.write_log("SYS: Pre-calentando modelo...")
    try:
        t0 = time.time()
        brain.chat("Hola", tool_dispatch_fn=lambda n, a: "")
        print(f"[LOCAL] Modelo listo en {time.time()-t0:.0f}s")
        if _ui:
            _ui.write_log(f"SYS: Modelo listo ({time.time()-t0:.0f}s)")
        brain.reset_history()
    except Exception as e:
        print(f"[LOCAL] Warmup falló (no crítico): {e}")

    ready_msg = f"[ONYX] Cerebro local activo. Modelo: {OLLAMA_MODEL}. Bienvenido, Señor Cristian."
    print(ready_msg)
    if _ui:
        _ui.write_log(ready_msg)
    _speak("Bienvenido, Señor Cristian. ONYX modo local activado.")

    while _running:
        try:
            text = _input_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        if not text.strip():
            continue

        print(f"[LOCAL] Tú: {text}")
        if _ui:
            _ui.write_log(f"Tú: {text}")
            _ui.set_state("THINKING")

        try:
            response = brain.chat(text, tool_dispatch_fn=_dispatch_tool)

            if response.strip():
                print(f"[LOCAL] ONYX: {response}")
                if _ui:
                    _ui.write_log(f"ONYX: {response}")
                _speak(response)
            else:
                if _ui:
                    _ui.set_state("LISTENING")

        except Exception as e:
            err = f"Error: {e}"
            print(f"[LOCAL] {err}")
            if _ui:
                _ui.write_log(f"ERR: {err}")

# ── Entry point ──
def main():
    global _ui, _running
    _running = True

    ui = OnyxUI("face.png")
    _ui = ui
    ui.set_state("LISTENING")
    ui.write_log("SYS: ONYX Modo Local iniciando...")

    def runner():
        try:
            _local_loop()
        except Exception as e:
            print(f"[LOCAL] Fatal: {e}")
            import traceback
            traceback.print_exc()

    # Start Vosk listener thread
    listener_thread = threading.Thread(target=_vosk_listener, daemon=True)
    listener_thread.start()

    # Start main loop in background
    loop_thread = threading.Thread(target=runner, daemon=True)
    loop_thread.start()

    # Insert key global hotkey
    try:
        import keyboard
        keyboard.add_hotkey("insert", lambda: _input_queue.put("onyx"))
        print("[LOCAL] Hotkey Insert -> wake ONYX")
    except ImportError:
        pass

    ui.root.mainloop()
    _running = False
    print("[LOCAL] ONYX apagado.")

if __name__ == "__main__":
    main()
