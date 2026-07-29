"""Shared Windows controls for volume and display brightness."""
from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from typing import Any


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def clamp_percent(value: Any, default: int | None = None) -> int:
    try:
        if isinstance(value, str):
            match = re.search(r"-?\d+", value)
            if not match:
                raise ValueError(value)
            value = match.group(0)
        return max(0, min(100, int(float(value))))
    except Exception:
        if default is None:
            raise
        return default


def direction_from(*values: Any) -> str:
    text = " ".join(_norm(v) for v in values if v is not None)
    if any(word in text for word in ("down", "bajar", "baja", "bajalo", "menos", "reduce", "reducir", "disminuye")):
        return "down"
    if any(word in text for word in ("up", "subir", "sube", "subilo", "mas", "aumenta", "aumentar", "incrementa")):
        return "up"
    return ""


def _endpoint_volume():
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL, CoInitialize
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    CoInitialize()
    devices = AudioUtilities.GetSpeakers()
    if hasattr(devices, "EndpointVolume"):
        return devices.EndpointVolume
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume() -> int:
    from comtypes import CoUninitialize

    try:
        volume = _endpoint_volume()
        return int(round(volume.GetMasterVolumeLevelScalar() * 100))
    finally:
        try:
            CoUninitialize()
        except Exception:
            pass


def set_volume(percent: Any) -> str:
    from comtypes import CoUninitialize

    target = clamp_percent(percent)
    try:
        volume = _endpoint_volume()
        volume.SetMasterVolumeLevelScalar(target / 100.0, None)
        return f"Volumen ajustado al {target}%."
    finally:
        try:
            CoUninitialize()
        except Exception:
            pass


def change_volume(direction: str, step: int = 10) -> str:
    direction = direction_from(direction) or _norm(direction)
    if direction not in ("up", "down"):
        return f"Direccion de volumen no reconocida: {direction}"

    try:
        current = get_volume()
        target = current + step if direction == "up" else current - step
        return set_volume(target)
    except Exception:
        import pyautogui

        pyautogui.press("volumeup" if direction == "up" else "volumedown", presses=max(1, step // 2))
        return "Volumen subido." if direction == "up" else "Volumen bajado."


def set_mute(muted: bool) -> str:
    from comtypes import CoUninitialize

    try:
        volume = _endpoint_volume()
        volume.SetMute(1 if muted else 0, None)
        return "Volumen silenciado." if muted else "Volumen activado."
    finally:
        try:
            CoUninitialize()
        except Exception:
            pass


def toggle_mute() -> str:
    from comtypes import CoUninitialize

    try:
        volume = _endpoint_volume()
        muted = bool(volume.GetMute())
        volume.SetMute(0 if muted else 1, None)
        return "Volumen activado." if muted else "Volumen silenciado."
    finally:
        try:
            CoUninitialize()
        except Exception:
            pass


def _brightness_with_sbc(percent: Any | None = None, monitor: int | None = None) -> int | None:
    import screen_brightness_control as sbc

    kwargs = {}
    if monitor is not None:
        kwargs["display"] = monitor
    if percent is not None:
        sbc.set_brightness(clamp_percent(percent), **kwargs)
    values = sbc.get_brightness(**kwargs)
    if isinstance(values, list):
        return int(values[0]) if values else None
    return int(values)


def _powershell() -> str:
    return shutil.which("powershell.exe") or shutil.which("powershell") or "powershell"


def _run_ps(script: str) -> str:
    completed = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"PowerShell salio con codigo {completed.returncode}")
    return completed.stdout.strip()


def _brightness_with_wmi(percent: Any | None = None) -> int | None:
    if percent is not None:
        target = clamp_percent(percent)
        _run_ps(
            "$ErrorActionPreference='Stop'; "
            "$m=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods; "
            f"$m | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={target}}} | Out-Null"
        )
    output = _run_ps(
        "$ErrorActionPreference='Stop'; "
        "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | "
        "Select-Object -First 1 -ExpandProperty CurrentBrightness"
    )
    match = re.search(r"\d+", output)
    return int(match.group(0)) if match else None


def get_brightness(monitor: int | None = None) -> int:
    errors: list[str] = []
    try:
        value = _brightness_with_sbc(monitor=monitor)
        if value is not None:
            return clamp_percent(value)
    except Exception as exc:
        errors.append(f"sbc: {exc}")

    try:
        value = _brightness_with_wmi()
        if value is not None:
            return clamp_percent(value)
    except Exception as exc:
        errors.append(f"wmi: {exc}")

    raise RuntimeError(
        "No pude leer el brillo. En monitores externos puede hacer falta DDC/CI o el software del fabricante. "
        + " | ".join(errors)
    )


def set_brightness(percent: Any, monitor: int | None = None) -> str:
    target = clamp_percent(percent)
    errors: list[str] = []
    try:
        _brightness_with_sbc(target, monitor=monitor)
        return f"Brillo ajustado al {target}%."
    except Exception as exc:
        errors.append(f"sbc: {exc}")

    try:
        _brightness_with_wmi(target)
        return f"Brillo ajustado al {target}%."
    except Exception as exc:
        errors.append(f"wmi: {exc}")

    raise RuntimeError(
        "No pude cambiar el brillo. Si es un monitor externo, activa DDC/CI en el menu del monitor "
        "o usa el software del fabricante. " + " | ".join(errors)
    )


def change_brightness(direction: str, step: int = 10, monitor: int | None = None) -> str:
    direction = direction_from(direction) or _norm(direction)
    if direction not in ("up", "down"):
        return f"Direccion de brillo no reconocida: {direction}"
    current = get_brightness(monitor=monitor)
    target = current + step if direction == "up" else current - step
    return set_brightness(target, monitor=monitor)
