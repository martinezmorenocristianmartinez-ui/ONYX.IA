"""
tool_registry.py - Registro declarativo de herramientas "simples" de ONYX.

Extraido del dispatcher gigante de main.py (_execute_tool). Cada entrada
describe una herramienta cuyo despacho sigue el patron uniforme:

    r = await loop.run_in_executor(
        _TOOL_EXECUTOR,
        lambda: <func>(parameters=args, player=self.ui[, **extra])
    )
    result = r or "<default>"

En lugar de ~44 ramas elif identicas, main.py construye este mapa una vez y
las despacha con un unico handler generico. Las herramientas con logica
especial (computer_settings, screen_analyze, onyx_ui_control, plan_task, etc.)
siguen manejandose con sus propias ramas en main.py.

Campos de cada spec:
    func   : nombre del callable (global en main.py) que implementa la tool.
    default: mensaje a devolver si la funcion retorna un valor "falsy".
    raw    : si True, se devuelve el resultado crudo sin default (puede ser "").
    response       : si True, se pasa response=None al callable.
    speak          : si True, se pasa speak=self.speak al callable.
    session_memory : si True, se pasa session_memory=None al callable.
"""
from __future__ import annotations

_DONE = "Done."

SIMPLE_TOOL_SPECS: dict[str, dict] = {
    # name                      func (global en main.py)         opciones
    "close_app":               {"func": "close_app", "response": True, "default": _DONE},
    "weather_report":          {"func": "weather_action", "default": "Weather delivered."},
    "browser_control":         {"func": "browser_control", "default": _DONE},
    "smart_tracker":           {"func": "smart_tracker", "default": _DONE},
    "epic_fortnite_control":   {"func": "epic_fortnite_control", "default": "Operación de Epic/Fortnite completada."},
    "leer_articulo":           {"func": "leer_articulo", "raw": True},
    "file_controller":         {"func": "file_controller", "default": _DONE},
    "reminder":                {"func": "reminder", "response": True, "default": "Reminder set."},
    "youtube_video":           {"func": "youtube_video", "response": True, "default": _DONE},
    "saltar_anuncios_youtube": {"func": "saltar_anuncios_youtube", "response": True, "default": _DONE},
    "screen_process":          {"func": "screen_vision", "default": "No pude analizar la imagen/pantalla."},
    "screen_vision":           {"func": "screen_vision", "default": "No pude analizar la imagen/pantalla."},
    "desktop_control":         {"func": "desktop_control", "default": _DONE},
    "code_helper":             {"func": "code_helper", "speak": True, "default": _DONE},
    "dev_agent":               {"func": "dev_agent", "speak": True, "default": _DONE},
    "web_search":              {"func": "web_search_action", "default": _DONE},
    "computer_control":        {"func": "computer_control", "default": _DONE},
    "game_updater":            {"func": "game_updater", "speak": True, "default": _DONE},
    "flight_finder":           {"func": "flight_finder", "default": _DONE},
    "google_calendar":         {"func": "google_calendar", "default": _DONE},
    "spotify_control":         {"func": "spotify_control", "default": _DONE},
    "scheduler":               {"func": "scheduler", "speak": True, "default": _DONE},
    "google_drive":            {"func": "google_drive", "default": _DONE},
    "google_maps":             {"func": "google_maps", "default": _DONE},
    "gmail_control":           {"func": "gmail_control", "default": _DONE},
    "rules_engine":            {"func": "rules_engine", "default": _DONE},
    "user_profile":            {"func": "user_profile", "default": _DONE},
    "goals":                   {"func": "goals", "default": _DONE},
    "git_control":             {"func": "git_control", "default": _DONE},
    "codebase":                {"func": "codebase", "default": _DONE},
    "knowledge_base":          {"func": "knowledge_base", "default": _DONE},
    "whatsapp":                {"func": "whatsapp", "default": _DONE},
    "social_media":            {"func": "social_media", "default": _DONE},
    "windows_settings":        {"func": "windows_settings", "default": _DONE},
    "document_creator":        {"func": "document_creator", "default": _DONE},
    "image_generation":        {"func": "image_generation", "default": _DONE},
    "smart_home":              {"func": "smart_home", "default": _DONE},
    "system_monitor":          {"func": "system_monitor", "default": _DONE},
    "tiktok_analyzer":         {"func": "tiktok_analyzer", "default": _DONE},
    "arca_invoice":            {"func": "arca_invoice", "default": _DONE},
    "accessibility":           {"func": "accessibility", "default": _DONE},
    "morning_brief":           {"func": "morning_brief", "default": "Aquí está tu informe del día."},
    "vision_guardian":         {"func": "vision_guardian", "default": _DONE},
    "screen_reader":           {"func": "screen_reader", "default": _DONE},
    "accessibility_overlay":   {"func": "accessibility_overlay", "default": _DONE},
}


def build_executor_kwargs(spec: dict, args: dict, ui, speak_fn) -> dict:
    """Construye los kwargs para invocar la herramienta segun su spec."""
    kwargs = {"parameters": args, "player": ui}
    if spec.get("response"):
        kwargs["response"] = None
    if spec.get("speak"):
        kwargs["speak"] = speak_fn
    if spec.get("session_memory"):
        kwargs["session_memory"] = None
    return kwargs


# Herramientas que funcionan SIN la nube (Gemini). Se exponen al cerebro local
# (Ollama) en modo offline para que pueda, por ejemplo, BUSCAR ARCHIVOS, abrir
# apps o leer documentos cuando el API no está disponible. Se mantiene acotada
# porque los modelos locales pequeños eligen mejor con pocas herramientas.
LOCAL_TOOL_NAMES = {
    "file_controller",   # buscar / listar / leer / mover archivos (Word, PDF, etc.)
    "file_processor",    # resumir / extraer texto de PDF y Word
    "open_app",
    "close_app",
    "web_search",        # DuckDuckGo, no requiere API key de Gemini
    "computer_control",
    "computer_settings",  # volumen / brillo / ventanas (local)
    "system_monitor",
    "knowledge_base",
    "document_creator",
    "desktop_control",
    "weather_report",
    "youtube_video",
    "spotify_control",
    "media_control",
    "local_image_analysis",  # analizar/describir imágenes sin API (BLIP + OCR)
}
