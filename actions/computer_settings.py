"""computer_settings.py - Win32/system setting controls."""
from __future__ import annotations

from actions.system_controls import (
    change_brightness,
    change_volume,
    direction_from,
    get_brightness,
    get_volume,
    set_brightness,
    set_mute,
    set_volume,
    toggle_mute,
)


def _text(parameters: dict) -> str:
    return " ".join(
        str(parameters.get(key, ""))
        for key in ("action", "value", "description")
        if parameters.get(key)
    ).lower()


def computer_settings(parameters: dict, response=None, player=None) -> str:
    """Adjust common system settings like volume, brightness, and window state."""
    action = str(parameters.get("action", "")).lower().strip()
    value = parameters.get("value", "")
    description = parameters.get("description", "")
    text = _text(parameters)

    if action in ("volume", "volumen", "set_volume", "volume_up", "volume_down") or "volumen" in text or "volume" in text:
        try:
            if "toggle_mute" in action or "alternar mute" in text:
                msg = toggle_mute()
            elif "unmute" in action or "activar sonido" in text or "quitar silencio" in text:
                msg = set_mute(False)
            elif "mute" in action or "silenciar" in text:
                msg = set_mute(True)
            elif str(value).strip().isdigit():
                msg = set_volume(value)
            else:
                direction = direction_from(action, value, description)
                msg = change_volume(direction) if direction else f"Volumen actual: {get_volume()}%."
            if player:
                player.write_log(msg)
            return f"{msg}, Senor Cristian."
        except Exception as exc:
            return f"Fallo al ajustar el volumen: {exc}"

    if action in ("brightness", "brillo", "set_brightness", "brightness_up", "brightness_down") or "brillo" in text or "brightness" in text:
        try:
            monitor = parameters.get("monitor")
            if str(value).strip().isdigit():
                msg = set_brightness(value, monitor=monitor)
            else:
                direction = direction_from(action, value, description)
                msg = change_brightness(direction, monitor=monitor) if direction else f"Brillo actual: {get_brightness(monitor=monitor)}%."
            if player:
                player.write_log(msg)
            return f"{msg}, Senor Cristian."
        except Exception as exc:
            return f"Fallo al ajustar el brillo: {exc}"

    if action in ("minimize", "window_minimize"):
        try:
            import pygetwindow as gw

            window = gw.getActiveWindow()
            if window:
                window.minimize()
                return "Ventana activa minimizada."
            return "No encontre una ventana activa."
        except Exception as exc:
            return f"Fallo al minimizar la ventana: {exc}"

    if action in ("maximize", "window_maximize"):
        try:
            import pygetwindow as gw

            window = gw.getActiveWindow()
            if window:
                window.maximize()
                return "Ventana activa maximizada."
            return "No encontre una ventana activa."
        except Exception as exc:
            return f"Fallo al maximizar la ventana: {exc}"

    return f"Accion de configuracion no soportada: {action}"
