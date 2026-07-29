"""Windows settings actions used by ONYX."""
from __future__ import annotations

import os
import subprocess

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


SETTINGS_PAGES = {
    "display": "ms-settings:display",
    "brightness": "ms-settings:display",
    "brillo": "ms-settings:display",
    "sound": "ms-settings:sound",
    "audio": "ms-settings:sound",
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "apps": "ms-settings:appsfeatures",
    "power": "ms-settings:powersleep",
    "energia": "ms-settings:powersleep",
    "privacy": "ms-settings:privacy",
}


def _as_text(parameters: dict) -> str:
    return " ".join(
        str(parameters.get(key, ""))
        for key in ("action", "value", "value2", "name", "description")
        if parameters.get(key)
    ).lower()


def _open_settings(page: str) -> str:
    uri = SETTINGS_PAGES.get(page.lower(), SETTINGS_PAGES.get("display"))
    os.startfile(uri)
    return f"Abriendo Configuracion de Windows: {page}."


def windows_settings(parameters: dict, player=None) -> str:
    action = str(parameters.get("action", "")).lower().strip()
    value = parameters.get("value", "")
    text = _as_text(parameters)
    monitor = parameters.get("monitor")

    try:
        if action in ("get_volume", "volume", "volumen") or ("volumen" in text and not value):
            return f"Volumen actual: {get_volume()}%."

        if action in ("set_volume", "volume_up", "volume_down") or "subir volumen" in text or "bajar volumen" in text:
            if str(value).strip().isdigit():
                msg = set_volume(value)
            else:
                direction = direction_from(action, value, text)
                msg = change_volume(direction) if direction else f"Volumen actual: {get_volume()}%."
            if player:
                player.write_log(msg)
            return msg

        if action == "mute":
            return set_mute(True)
        if action == "unmute":
            return set_mute(False)
        if action == "toggle_mute" or "silenciar" in text:
            return toggle_mute()

        if action in ("get_brightness", "brightness", "brillo") or ("brillo" in text and not value):
            return f"Brillo actual: {get_brightness(monitor=monitor)}%."

        if action in ("set_brightness", "brightness_up", "brightness_down") or "subir brillo" in text or "bajar brillo" in text:
            if str(value).strip().isdigit():
                msg = set_brightness(value, monitor=monitor)
            else:
                direction = direction_from(action, value, text)
                msg = change_brightness(direction, monitor=monitor) if direction else f"Brillo actual: {get_brightness(monitor=monitor)}%."
            if player:
                player.write_log(msg)
            return msg

        if "teclado" in text and any(word in text for word in ("luz", "luces", "rgb", "backlight", "iluminacion")):
            from actions.rgb_control import rgb_control

            rgb_action = "off" if any(word in text for word in ("apagar", "apaga", "off", "desactivar")) else "on"
            return rgb_control({"action": rgb_action, "device": "keyboard"}, player=player)

        if action == "open" or action.startswith("open_settings"):
            return _open_settings(str(value or parameters.get("name") or "display"))

        if action in SETTINGS_PAGES:
            return _open_settings(action)

        if action == "lock":
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
            return "Equipo bloqueado."

    except Exception as exc:
        return f"No pude aplicar la configuracion de Windows '{action}': {exc}"

    return f"Accion de Windows no implementada todavia: {action}"
