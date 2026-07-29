import time
import threading
import hashlib
from actions._vision import get_api_key, call_vision as _call_vision_raw

DEFAULT_PROMPT = (
    "Analizá esta captura de pantalla. Decí qué está haciendo el usuario, "
    "qué ventanas/programas están abiertos, qué contenido visible hay, y si ves algo que necesite asistencia. "
    "Respondé en 1-2 oraciones en español."
)

_running = False
_thread = None
_interval = 0.3
_inject_fn = None
_speaking_fn = None
_last_hash = ""
_last_pywinauto_report = ""


def _image_hash():
    import mss
    from PIL import Image
    with mss.mss() as sct:
        mon = sct.monitors[1]
        sct_img = sct.grab(mon)
        img = Image.frombytes("RGB", (mon["width"], mon["height"]), sct_img.bgra, "raw", "BGRX")
        img.thumbnail((160, 120), Image.Resampling.BILINEAR)
        return hashlib.md5(img.tobytes()).hexdigest()


def _capture_base64():
    import mss
    from PIL import Image
    import io, base64
    with mss.mss() as sct:
        mon = sct.monitors[1]
        sct_img = sct.grab(mon)
        img = Image.frombytes("RGB", (mon["width"], mon["height"]), sct_img.bgra, "raw", "BGRX")
        img.thumbnail((800, 600), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()


def _call_vision(b64_image, prompt=None):
    if not get_api_key():
        return None
    prompt = prompt or DEFAULT_PROMPT
    return _call_vision_raw(prompt, b64_image, max_tokens=1000, temperature=0.1)


def _pywinauto_scan():
    """Escanea la ventana activa con PyWinAuto. Sin API. Devuelve descripción estructurada."""
    try:
        import pywinauto
    except ImportError:
        return None

    try:
        app = pywinauto.Application(backend='uia').connect(active_only=True, timeout=2)
        win = app.active()
        title = win.window_text()
        proc_id = win.process_id()
        class_name = win.element_info.class_name

        lines = []
        lines.append(f"Ventana activa: {title}")
        lines.append(f"Clase: {class_name}")

        ctrls = win.descendants()
        buttons = []
        edits = []
        texts = []
        links = []
        lists = []
        tabs = []
        others = []

        for c in ctrls:
            try:
                ctrl_type = c.element_info.control_type
                ctrl_text = c.window_text() or ""
                rect = c.rectangle()
                cx, cy = rect.mid_point()
                info = {
                    "type": ctrl_type,
                    "text": ctrl_text[:60],
                    "x": cx,
                    "y": cy,
                    "w": rect.width(),
                    "h": rect.height()
                }
                if ctrl_type == "Button" and ctrl_text:
                    buttons.append(info)
                elif ctrl_type == "Edit" and ctrl_text:
                    edits.append(info)
                elif ctrl_type == "Text" and ctrl_text.strip():
                    texts.append(info)
                elif ctrl_type == "Hyperlink" and ctrl_text:
                    links.append(info)
                elif ctrl_type in ("List", "ListBox", "DataGrid"):
                    lists.append(info)
                elif ctrl_type == "TabItem" and ctrl_text:
                    tabs.append(info)
                elif ctrl_text.strip():
                    others.append(info)
            except Exception:
                continue

        if buttons:
            lines.append(f"Botones: {', '.join(b['text'] for b in buttons[:15])}")
        if edits:
            lines.append(f"Campos: {', '.join(e['text'] for e in edits[:8])}")
        if links:
            lines.append(f"Enlaces: {', '.join(l['text'] for l in links[:8])}")
        if tabs:
            lines.append(f"Tabs: {', '.join(t['text'] for t in tabs[:8])}")
        if texts:
            lines.append(f"Textos visibles: {', '.join(t['text'] for t in texts[:10])}")

        return "\n".join(lines)

    except Exception:
        return None


def _opencv_diff():
    """Calcula porcentaje de cambio entre frame anterior y actual usando OpenCV."""
    import mss
    from PIL import Image
    import numpy as np

    if not hasattr(_opencv_diff, "_prev_frame"):
        _opencv_diff._prev_frame = None

    with mss.mss() as sct:
        mon = sct.monitors[1]
        sct_img = sct.grab(mon)
        img = Image.frombytes("RGB", (mon["width"], mon["height"]), sct_img.bgra, "raw", "BGRX")
        img.thumbnail((320, 240), Image.Resampling.BILINEAR)
        current = np.array(img, dtype=np.uint8)

    if _opencv_diff._prev_frame is not None:
        diff = np.mean(np.abs(current.astype(np.int16) - _opencv_diff._prev_frame.astype(np.int16)))
        max_diff = 255.0 * 3
        pct = (diff / max_diff) * 100
        _opencv_diff._prev_frame = current
        return pct

    _opencv_diff._prev_frame = current
    return 0.0


def _loop():
    global _last_hash, _last_pywinauto_report

    consecutive_errors = 0

    while _running:
        try:
            # ── Cambio visual con OpenCV ──
            has_changed = _image_hash() != _last_hash
            if has_changed:
                _last_hash = _image_hash()
                diff_pct = _opencv_diff()
            else:
                diff_pct = 0.0

            # ── Escaneo local con PyWinAuto (cada ciclo) ──
            local_report = _pywinauto_scan()

            if _speaking_fn and _speaking_fn():
                time.sleep(_interval)
                continue

            # ── Reportar cambios locales significativos ──
            if local_report and local_report != _last_pywinauto_report:
                _last_pywinauto_report = local_report
                if _inject_fn and has_changed:
                    _inject_fn(f"[Vision Guardian] {local_report}")

            # ── API call en CADA cambio significativo ──
            if has_changed and diff_pct > 0.3:
                if consecutive_errors > 0:
                    consecutive_errors = 0

                b64 = _capture_base64()
                result = _call_vision(b64)

                if result:
                    if _inject_fn:
                        _inject_fn(f"[Vision Guardian] {result}")
                else:
                    consecutive_errors += 1
                    # Reportamos lo local si falla API
                    if consecutive_errors > 5 and local_report and _inject_fn and has_changed:
                        _inject_fn(f"[Vision Guardian] {local_report}")

        except Exception:
            consecutive_errors += 1

        time.sleep(_interval)


def start(**kwargs):
    global _inject_fn, _speaking_fn, _running, _thread, _interval
    _inject_fn = kwargs.get("inject_fn")
    _speaking_fn = kwargs.get("speaking_fn")
    _interval = kwargs.get("interval", 1)
    if not _running:
        _running = True
        _thread = threading.Thread(target=_loop, daemon=True)
        _thread.start()


def stop():
    global _running
    _running = False


def _describe_local():
    """Descripción completa LOCAL sin API."""
    import pygetwindow as gw
    lines = []

    active = gw.getActiveWindow()
    if active:
        lines.append(f"Ventana activa: {active.title}")
    else:
        lines.append("No hay ventana activa.")

    windows = gw.getAllWindows()
    visible = [w for w in windows if w.visible]
    lines.append(f"Ventanas abiertas ({len(visible)}):")
    for w in visible[:15]:
        r = w.box
        lines.append(f"  • {w.title} [{r.left},{r.top} {r.width}x{r.height}]")

    local = _pywinauto_scan()
    if local:
        lines.append("")
        lines.append(local)

    return "\n".join(lines)


def vision_guardian(parameters: dict, player=None) -> str:
    action = str(parameters.get("action", "status") or "status").lower()
    global _interval, _running

    if action == "enable":
        if not _running:
            start(inject_fn=_inject_fn, speaking_fn=_speaking_fn)
        return "Guardian de Visión activado. Modo híbrido: PyWinAuto + OpenCV local, IA como respaldo."

    if action == "disable":
        stop()
        return "Guardian de Visión desactivado."

    if action == "status":
        if _running:
            return f"Guardian activo. Intervalo: {_interval}s. Modo: local (PyWinAuto+OpenCV) + API si necesario."
        return "Guardian inactivo."

    if action in ("check_now", "describe"):
        if action == "describe":
            local = _describe_local()
            b64 = _capture_base64()
            visual = _call_vision(b64, "Describí esta captura de pantalla en detalle. ¿Qué ventanas ves? ¿Qué está haciendo el usuario?")
            if visual:
                return f"--- LOCAL (PyWinAuto) ---\n{local}\n\n--- VISIÓN IA ---\n{visual}"
            return f"--- LOCAL (PyWinAuto) ---\n{local}\n\n(Sin conexión API - solo datos locales)"
        else:
            b64 = _capture_base64()
            result = _call_vision(b64)
            local = _pywinauto_scan()
            if result:
                return f"{result}\n\n---\n{local}" if local else result
            if local:
                return f"(Sin API) {local}"
            return "No pude analizar la pantalla."

    if action == "local":
        local = _describe_local()
        return f"--- Datos locales ---\n{local}"

    if action in ("set_interval", "interval"):
        seconds = float(parameters.get("seconds", 0.2))
        if seconds < 0.05:
            seconds = 0.05
        _interval = seconds
        return f"Intervalo cambiado a {_interval}s."

    return f"Acción '{action}' no reconocida. Usá: enable, disable, status, check_now, describe, local, set_interval."
