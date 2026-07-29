"""
local_vision.py — 100% local screen vision using Ollama vision models.
No API keys needed, no internet required.
"""
from actions._vision import (
    capture_screen,
    capture_screen_resized,
    capture_active_window,
    call_vision_local,
    _list_ollama_vision_models,
)


def local_vision(parameters: dict, player=None) -> str:
    """Analyze the screen using a local Ollama vision model (no API)."""
    prompt = parameters.get("value", parameters.get("description", "")).strip()
    if not prompt:
        prompt = "Describe lo que ves en esta pantalla en detalle."
    mode = (parameters.get("mode", "") or "").strip().lower()

    models = _list_ollama_vision_models()
    if not models:
        return "No hay modelo de visión local disponible. Asegúrate de tener Ollama corriendo y un modelo como 'llava' instalado (ollama pull llava)."

    if mode in ("window", "ventana", "active"):
        b64, ow, oh, _, _ = capture_active_window()
        label = "ventana activa"
    elif mode in ("region", "area", "cropped", "recorte"):
        b64, ow, oh, _, _ = capture_screen_resized(max_size=800, region_pct=(5, 5, 95, 95))
        label = "pantalla (recortada)"
    else:
        b64, ow, oh = capture_screen()
        label = "pantalla completa"

    if not b64:
        return "No se pudo capturar la pantalla."

    result = call_vision_local(prompt, b64, temperature=0.1)
    if not result:
        return f"La visión local no respondió. Verifica que Ollama esté corriendo y tenga un modelo de visión."

    return f"[VISION LOCAL - {label}] {result}"
