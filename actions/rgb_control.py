"""Hardware RGB/backlight control for ONYX."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


COLOR_NAMES = {
    "rojo": "ff0000",
    "red": "ff0000",
    "verde": "00ff00",
    "green": "00ff00",
    "azul": "0000ff",
    "blue": "0000ff",
    "blanco": "ffffff",
    "white": "ffffff",
    "negro": "000000",
    "black": "000000",
    "apagado": "000000",
    "off": "000000",
}


def _hex_color(value: str | None, brightness: int = 100) -> str:
    raw = (value or "ffffff").strip().lower().replace("#", "")
    raw = COLOR_NAMES.get(raw, raw)
    if len(raw) != 6 or any(ch not in "0123456789abcdef" for ch in raw):
        raw = "ffffff"

    brightness = max(0, min(100, int(brightness))) / 100.0
    parts = [int(raw[i : i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{int(part * brightness):02x}" for part in parts)


def _find_openrgb_exe() -> str | None:
    found = shutil.which("openrgb") or shutil.which("OpenRGB.exe")
    if found:
        return found

    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "OpenRGB" / "OpenRGB.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "OpenRGB" / "OpenRGB.exe",
        Path.cwd() / "OpenRGB.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _omen_app_path() -> str | None:
    base = Path(os.environ.get("ProgramFiles", "")) / "WindowsApps"
    candidates = sorted(base.glob("AD2F1837.OMENCommandCenter_*_x64__v10z8vjag6ke6"))
    if not candidates:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell:
            try:
                completed = subprocess.run(
                    [
                        powershell,
                        "-NoProfile",
                        "-Command",
                        "(Get-AppxPackage AD2F1837.OMENCommandCenter).InstallLocation",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                location = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
                if location:
                    app = Path(location) / "OmenCommandCenterApp"
                    return str(app) if app.exists() else None
            except Exception:
                return None
        return None
    app = candidates[-1] / "OmenCommandCenterApp"
    return str(app) if app.exists() else None


def _matches_device(device, wanted: str) -> bool:
    if not wanted:
        return True
    name = str(getattr(device, "name", "")).lower()
    dtype = str(getattr(device, "type", "")).lower()
    wanted = wanted.lower()
    aliases = {
        "teclado": ("keyboard", "teclado"),
        "keyboard": ("keyboard", "teclado"),
        "mouse": ("mouse",),
    }.get(wanted, (wanted,))
    return any(alias in name or alias in dtype for alias in aliases)


def _apply_openrgb_sdk(action: str, color_hex: str, device_filter: str, effect: str | None) -> str | None:
    try:
        from openrgb import OpenRGBClient
        from openrgb.utils import RGBColor

        client = OpenRGBClient()
        devices = [dev for dev in client.devices if _matches_device(dev, device_filter)]
        if action == "list":
            if not devices:
                return "OpenRGB SDK esta activo, pero no encontre dispositivos RGB."
            names = ", ".join(str(getattr(dev, "name", "dispositivo")) for dev in devices)
            return f"Dispositivos RGB detectados: {names}."
        if not devices:
            return f"OpenRGB SDK esta activo, pero no encontre dispositivos que coincidan con '{device_filter}'."

        rgb = RGBColor(
            int(color_hex[0:2], 16),
            int(color_hex[2:4], 16),
            int(color_hex[4:6], 16),
        )

        for dev in devices:
            if action == "effect" and effect:
                try:
                    dev.set_mode(effect)
                    continue
                except Exception:
                    pass
            try:
                dev.set_color(rgb)
            except Exception:
                for zone in getattr(dev, "zones", []) or []:
                    try:
                        zone.set_color(rgb)
                    except Exception:
                        pass

        return f"RGB aplicado en {len(devices)} dispositivo(s) via OpenRGB SDK."
    except Exception:
        return None


def _apply_openrgb_cli(action: str, color_hex: str, effect: str | None) -> str | None:
    exe = _find_openrgb_exe()
    if not exe:
        return None

    if action == "effect" and effect:
        args = [exe, "--mode", effect]
    else:
        args = [exe, "--mode", "static", "--color", color_hex]

    completed = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return f"OpenRGB respondio con error: {detail or completed.returncode}"
    return "RGB aplicado via OpenRGB."


def _apply_hp_omen_sdk(action: str, color_hex: str) -> str | None:
    app = _omen_app_path()
    if not app:
        return None

    escaped_app = app.replace("'", "''")
    script = f"""
$ErrorActionPreference='Stop'
$base='{escaped_app}'
Set-Location $base
[AppDomain]::CurrentDomain.add_AssemblyResolve({{
    param($sender,$e)
    $name=($e.Name -split ',')[0]+'.dll'
    $path=Join-Path $base $name
    if(Test-Path $path){{ return [Reflection.Assembly]::LoadFrom($path) }}
    return $null
}}) | Out-Null
$ok=$false
try {{
    # McuSDK2 for newer OMEN/Victus keyboards
    [Reflection.Assembly]::LoadFrom((Join-Path $base 'McuSDK2.dll')) | Out-Null
    [Reflection.Assembly]::LoadFrom((Join-Path $base 'HIDSDK.dll')) | Out-Null
    $m=[Hp.Bridge.Client.SDKs.McuSDK2.McuKeyboardHelper]
    $open=$m::OpenDevice(0x4E81, 0x3938, 'McuKeyboard')
    if($open.Wait(3000) -and $open.Result -ge 0) {{
        if('{action}' -eq 'off') {{
            $t=$m::SetKeyBoardLightingOff($open.Result)
        }} else {{
            $t=$m::SetKeyBoardLightingOn($open.Result)
        }}
        if($t.Wait(3000)){{ $ok = [bool]$t.Result }}
    }}
}} catch {{}}
if(-not $ok) {{
    try {{
        # McuKeyboardLightingSDK legacy
        [Reflection.Assembly]::LoadFrom((Join-Path $base 'McuKeyboardLightingSDK.dll')) | Out-Null
        [Reflection.Assembly]::LoadFrom((Join-Path $base 'HIDSDK.dll')) | Out-Null
        $m=[Hp.Bridge.Client.SDKs.McuKeyboardLightingSDK.McuKeyboardLightingHelper]
        try {{ $m::IsHP=$true }} catch {{ [Hp.Bridge.Client.SDKs.HIDSDK.HIDHelper]::IsHP=$true }}
        if('{action}' -eq 'off') {{
            $t=$m::SetKeyBoardLightingOff(0)
        }} else {{
            $t=$m::SetKeyBoardLightingOn(0)
        }}
        if($t.Wait(2500)){{ $ok = [bool]$t.Result }}
    }} catch {{}}
}}
if(-not $ok) {{
    try {{
        # Typhon chassis lighting fallback
        [Reflection.Assembly]::LoadFrom((Join-Path $base 'TyphonChasisLightingSDK.dll')) | Out-Null
        if('{action}' -eq 'off') {{
            $t=[TyphonChasisLightingSDK.TyphonChasisLightingHelper]::SetLightingOff(0,0,0,0)
            if($t.Wait(2500)){{ $ok = [bool]$t.Result }}
        }}
    }} catch {{}}
}}
if($ok){{ Write-Output 'OK' }} else {{ Write-Output 'NOOP' }}
"""
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return None

    try:
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return None

    if completed.returncode == 0 and "OK" in completed.stdout:
        return "RGB del teclado aplicado via HP OMEN SDK."
    return None


def _fallback_keyboard_toggle(action: str) -> str:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        VK_F4 = 0x73

        # Press F4 down
        user32.keybd_event(VK_F4, 0, KEYEVENTF_EXTENDEDKEY, 0)
        # Release F4
        user32.keybd_event(VK_F4, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

        return (
            "No encontre OpenRGB ni el SDK de OMEN. Simule la tecla F4 como intento "
            "de alternar la luz del teclado."
        )
    except Exception as exc:
        return f"No pude enviar el atajo de teclado: {exc}"


def rgb_control(parameters: dict, player=None) -> str:
    """Control RGB lights for keyboards and peripherals."""
    action = str(parameters.get("action", "off")).lower().strip()
    device = str(parameters.get("device", "") or parameters.get("target", "")).strip()
    effect = parameters.get("effect")
    brightness = parameters.get("brightness", 100)

    action_text = " ".join(str(v).lower() for v in parameters.values() if v is not None)

    if any(word in action_text for word in ("apagar", "apaga", "apagalo", "off", "desactivar")):
        action = "off"
    elif any(word in action_text for word in ("encender", "enciende", "prender", "prende", "on", "activar")):
        action = "on"

    if action == "list":
        sdk_result = _apply_openrgb_sdk("list", "ffffff", device, None)
        return sdk_result or "No pude listar RGB: abre OpenRGB y activa el servidor SDK en puerto 6742."

    color_hex = "000000" if action == "off" else _hex_color(parameters.get("color"), brightness)
    if action == "brightness" and not parameters.get("color"):
        color_hex = _hex_color("white", brightness)
    if action == "rainbow":
        action = "effect"
        effect = effect or "rainbow"

    result = None
    if device.lower() in ("keyboard", "teclado", "") and action in ("off", "on"):
        result = _apply_hp_omen_sdk(action, color_hex)
    if not result:
        result = _apply_openrgb_sdk(action, color_hex, device, effect)
    if not result:
        result = _apply_openrgb_cli(action, color_hex, effect)
    if not result:
        result = _fallback_keyboard_toggle(action)

    if player:
        player.write_log(result)
    return f"{result}, Senor Cristian."
