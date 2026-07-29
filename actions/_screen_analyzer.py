"""
_screen_analyzer.py — Advanced multi-strategy screen analysis engine.
Combines PyWinAuto (UIA tree), OCR (pytesseract), OpenCV (template/color),
and AI Vision (Gemini) to find ANY element on screen with maximum accuracy.
"""
import time
import re
from pathlib import Path
from collections import defaultdict

OCR_AVAILABLE = False
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    try:
        import easyocr
        OCR_AVAILABLE = True
    except ImportError:
        pass

CV_AVAILABLE = False
try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except ImportError:
    pass


# ── Window / Structure Analysis ─────────────────────────────────────

def get_active_window_info() -> dict:
    """Get active window bounds, title, and process."""
    try:
        import pygetwindow as gw
        win = gw.getActiveWindow()
        if win:
            b = win.box
            return {
                "title": win.title,
                "left": b.left, "top": b.top,
                "width": b.width, "height": b.height,
                "is_minimized": win.isMinimized,
            }
    except Exception:
        pass
    return {}


def get_all_windows() -> list[dict]:
    """Get all visible windows with bounds."""
    try:
        import pygetwindow as gw
        result = []
        for w in gw.getAllWindows():
            if w.visible and w.title.strip():
                b = w.box
                result.append({
                    "title": w.title.strip(),
                    "left": b.left, "top": b.top,
                    "width": b.width, "height": b.height,
                })
        return result
    except Exception:
        return []


def get_ui_tree() -> list[dict]:
    """
    Scan active window UI Automation tree (PyWinAuto).
    Returns list of elements with type, text, position.
    This is the FASTEST and most ACCURATE method for Windows native apps.
    """
    try:
        import pywinauto
    except ImportError:
        return []

    try:
        app = pywinauto.Application(backend='uia').connect(active_only=True, timeout=2)
        win = app.active()
        title = win.window_text()
        ctrls = win.descendants()
        elements = []
        for c in ctrls:
            try:
                ctrl_type = c.element_info.control_type
                ctrl_text = c.window_text() or ""
                rect = c.rectangle()
                cx, cy = rect.mid_point()
                elements.append({
                    "type": ctrl_type or "Unknown",
                    "text": ctrl_text[:100],
                    "x": cx, "y": cy,
                    "w": rect.width(), "h": rect.height(),
                    "left": rect.left, "top": rect.top,
                })
            except Exception:
                continue
        return elements
    except Exception:
        return []


def find_in_ui_tree(target: str, elements: list[dict] = None) -> list[dict]:
    """Find UI elements matching target text or type."""
    if elements is None:
        elements = get_ui_tree()
    target_lower = target.lower().strip()
    results = []
    for el in elements:
        text = el.get("text", "").lower()
        ctype = el.get("type", "").lower()
        if target_lower in text or target_lower in ctype:
            results.append(el)
    return results


# ── OCR (Local Text Detection) ──────────────────────────────────────

def ocr_screen(psm: int = 6) -> list[dict]:
    """
    Extract ALL text from screen using local OCR (pytesseract).
    Returns [{"text": "...", "x": center_x, "y": center_y, "conf": 0-100}]
    """
    if not OCR_AVAILABLE:
        return []

    try:
        import mss
        from PIL import Image
        import io

        with mss.mss() as sct:
            mon = sct.monitors[1]
            img = Image.frombytes("RGB", (mon["width"], mon["height"]),
                                  sct.grab(mon).bgra, "raw", "BGRX")

        if pytesseract:
            import pytesseract as ocr_lib
            config = f"--psm {psm} --oem 3"
            data = ocr_lib.image_to_data(img, config=config, output_type=ocr_lib.Output.DICT)
            results = []
            for i in range(len(data["text"])):
                text = (data["text"][i] or "").strip()
                if text and int(data["conf"][i]) > 20:
                    x = data["left"][i] + data["width"][i] // 2
                    y = data["top"][i] + data["height"][i] // 2
                    results.append({
                        "text": text,
                        "x": x, "y": y,
                        "conf": int(data["conf"][i]),
                        "w": data["width"][i],
                        "h": data["height"][i],
                    })
            return results
    except Exception:
        pass
    return []


def find_text_on_screen(target: str) -> list[dict]:
    """
    Find a text fragment on screen via OCR.
    Returns list of matching text blocks with coordinates, sorted by confidence.
    """
    texts = ocr_screen()
    if not texts:
        return []

    target_lower = target.lower().strip()
    # Exact match first, then substring
    exact = []
    substring = []
    fuzzy = []

    for t in texts:
        t_lower = t["text"].lower().strip()
        if t_lower == target_lower:
            exact.append(t)
        elif target_lower in t_lower:
            substring.append(t)
        elif _fuzzy_match(target_lower, t_lower):
            fuzzy.append(t)

    exact.sort(key=lambda x: -x["conf"])
    substring.sort(key=lambda x: -x["conf"])
    fuzzy.sort(key=lambda x: -x["conf"])

    return exact + substring + fuzzy


def _fuzzy_match(a: str, b: str, threshold: float = 0.6) -> bool:
    """Simple word-overlap fuzzy matching."""
    if not a or not b:
        return False
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    return overlap / max(len(words_a), len(words_b)) >= threshold


# ── Active Window / Region Detection ────────────────────────────────

def get_active_window_region() -> tuple[int, int, int, int] | None:
    """
    Get the bounding box of the active window.
    Returns (left, top, right, bottom) or None.
    """
    info = get_active_window_info()
    if info and info.get("width", 0) > 100:
        l, t = info["left"], info["top"]
        return (l, t, l + info["width"], t + info["height"])
    return None


def crop_to_region(img, region: tuple[int, int, int, int] | None):
    """
    Crop a PIL Image to a region.
    If region is None or invalid, returns the original image.
    """
    if region is None:
        return img
    l, t, r, b = region
    try:
        return img.crop((l, t, r, b))
    except Exception:
        return img


def guess_region_from_description(description: str) -> tuple[int, int, int, int] | None:
    """
    Given an element description, guess which screen region to search.
    Returns (left, top, right, bottom) percentage-based or None.
    Used to crop screen before sending to AI, saving tokens and improving accuracy.
    """
    desc_lower = description.lower()

    # Top regions
    top_keywords = ["barra de busqueda", "search bar", "buscar", "search",
                    "barra de direcciones", "address bar", "menu superior",
                    "top", "arriba", "cabecera", "header", "titulo", "title",
                    "pestaña", "tab", "navegacion", "navigation"]
    if any(kw in desc_lower for kw in top_keywords):
        return (0, 0, 100, 25)

    # Bottom regions
    bottom_keywords = ["barra de tareas", "taskbar", "inicio", "start",
                       "notificaciones", "notification", "bandeja", "tray",
                       "abajo", "bottom", "footer", "barra inferior"]
    if any(kw in desc_lower for kw in bottom_keywords):
        return (0, 75, 100, 100)

    # Left regions
    left_keywords = ["menu lateral", "sidebar", "navegacion lateral",
                     "izquierda", "left", "panel izquierdo"]
    if any(kw in desc_lower for kw in left_keywords):
        return (0, 0, 30, 100)

    # Right regions
    right_keywords = ["derecha", "right", "panel derecho", "notificaciones"]
    if any(kw in desc_lower for kw in right_keywords):
        return (70, 0, 100, 100)

    # Center
    center_keywords = ["centro", "center", "central", "medio", "middle",
                       "contenido", "content", "principal", "main"]
    if any(kw in desc_lower for kw in center_keywords):
        return (15, 10, 85, 90)

    return None


# ── Multi-Strategy Element Finder ───────────────────────────────────

def find_element_advanced(description: str, use_ocr: bool = True,
                          use_ui_tree: bool = True, use_ai: bool = True,
                          max_size: int = 1280) -> dict:
    """
    Find an element on screen using MULTIPLE strategies in order of speed.
    Returns dict with:
      found: bool
      x, y: center coordinates (screen pixels)
      confidence: "high" | "medium" | "low"
      strategy: "ocr" | "ui_tree" | "ai_vision" | "none"
      text: matched text (if any)
      region: region used for search

    Strategy order: OCR → UI Tree → AI Vision
    """
    result = {"found": False, "x": 0, "y": 0, "confidence": "low",
              "strategy": "none", "text": "", "region": None}

    # ── Strategy 1: OCR (local, fast) ──
    if use_ocr:
        try:
            matches = find_text_on_screen(description)
            if matches:
                best = matches[0]
                result.update({
                    "found": True,
                    "x": best["x"],
                    "y": best["y"],
                    "confidence": "high" if best["conf"] > 80 else "medium",
                    "strategy": "ocr",
                    "text": best["text"],
                })
                return result
        except Exception:
            pass

    # ── Strategy 2: UI Automation Tree (local, fast) ──
    if use_ui_tree:
        try:
            elements = get_ui_tree()
            if elements:
                matches = find_in_ui_tree(description, elements)
                if matches:
                    best = matches[0]
                    # If OCR found nothing but UI tree has a text match,
                    # try OCR on just the region to verify
                    result.update({
                        "found": True,
                        "x": best.get("x", 0),
                        "y": best.get("y", 0),
                        "confidence": "medium",
                        "strategy": "ui_tree",
                        "text": best.get("text", ""),
                    })
                    return result
        except Exception:
            pass

    # ── Strategy 3: AI Vision (server, expensive) ──
    if use_ai:
        try:
            from actions._vision import capture_screen_resized, vision_find, call_vision

            # Try smart region cropping first
            region_pct = guess_region_from_description(description)
            b64, orig_w, orig_h, scale_x, scale_y = capture_screen_resized(max_size, region_pct)
            if b64:
                # Use vision_find for coordinate extraction
                ai_coords = _ai_find_with_context(description, b64, scale_x, scale_y)
                if ai_coords:
                    result.update({
                        "found": True,
                        "x": ai_coords[0],
                        "y": ai_coords[1],
                        "confidence": "medium",
                        "strategy": "ai_vision",
                    })
                    return result
        except Exception:
            pass

    return result


def _ai_find_with_context(description: str, b64: str, scale_x: float, scale_y: float) -> tuple[int, int] | None:
    """Use AI vision to find an element, with contextual hints."""
    from actions._vision import call_vision, extract_coords

    # First, get a general description of what's visible
    context_prompt = (
        "Describí esta pantalla en 1-2 oraciones: ¿qué programa/app está abierto, "
        "y qué elementos principales ves (botones, barras, texto)?"
    )
    context = call_vision(context_prompt, b64, max_tokens=200, temperature=0.0)

    # Then, find the specific element with context
    find_prompt = (
        f"En la siguiente pantalla ({context if context else 'analizada'}), "
        f"encontrá EXACTAMENTE: '{description}'. "
        "Devolvé SOLO las coordenadas [X,Y] del CENTRO del elemento. "
        "Si no existe, devolvé [0,0]."
    )
    response = call_vision(find_prompt, b64, max_tokens=100, temperature=0.0)
    if not response:
        return None

    coords = extract_coords(response)
    if not coords or coords[0] == 0 or coords[1] == 0:
        return None

    return (int(coords[0] * scale_x), int(coords[1] * scale_y))


# ── Screen Structure Analysis ───────────────────────────────────────

def analyze_screen_structure() -> dict:
    """
    Full screen structure analysis combining multiple sources.
    Returns a structured dict of what's on screen.
    No API calls — purely local.
    """
    result = {
        "windows": [],
        "active_window": {},
        "ui_elements": [],
        "text_elements": [],
        "total_text_blocks": 0,
    }

    try:
        result["windows"] = get_all_windows()
        result["active_window"] = get_active_window_info()
        result["ui_elements"] = get_ui_tree()

        try:
            texts = ocr_screen()
            result["text_elements"] = texts[:50]
            result["total_text_blocks"] = len(texts)
        except Exception:
            pass
    except Exception:
        pass

    return result


def format_structure_report(structure: dict) -> str:
    """Format screen structure analysis into human-readable text."""
    lines = ["[ESTRUCTURA DE PANTALLA]"]

    aw = structure.get("active_window", {})
    if aw:
        lines.append(f"Ventana activa: {aw.get('title', '?')}  ({aw.get('width', 0)}x{aw.get('height', 0)})")

    windows = structure.get("windows", [])
    if windows:
        lines.append(f"Ventanas abiertas ({len(windows)}):")
        for w in windows[:8]:
            lines.append(f"  - {w['title'][:60]}")

    ui_elements = structure.get("ui_elements", [])
    if ui_elements:
        # Group by type
        by_type = defaultdict(list)
        for el in ui_elements:
            by_type[el["type"]].append(el)

        counts = {t: len(v) for t, v in by_type.items()}
        lines.append(f"Elementos UI ({len(ui_elements)} total):")
        for t, c in sorted(counts.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"  - {t}: {c}")

        # Show buttons/links/tabs with text
        interactives = [el for el in ui_elements
                        if el.get("text") and el["type"] in ("Button", "Hyperlink", "TabItem", "MenuItem")]
        if interactives:
            lines.append(f"Elementos interactivos con texto:")
            for el in interactives[:12]:
                lines.append(f"  [{el['type']}] '{el['text'][:50]}' en ({el['x']},{el['y']})")

    texts = structure.get("text_elements", [])
    if texts:
        lines.append(f"Textos detectados por OCR ({len(texts)} bloques):")
        for t in texts[:10]:
            lines.append(f"  '{t['text'][:60]}' conf={t['conf']} en ({t['x']},{t['y']})")

    lines.append("[/ESTRUCTURA DE PANTALLA]")
    return "\n".join(lines)


# ── Higher-level combined analysis ──────────────────────────────────

def describe_screen_advanced() -> str:
    """
    Describe the current screen using ALL available data sources.
    Falls back gracefully when components are missing.
    """
    parts = []

    try:
        structure = analyze_screen_structure()
        parts.append(format_structure_report(structure))
    except Exception:
        pass

    try:
        from actions._vision import capture_screen, call_vision
        b64, _, _ = capture_screen()
        if b64:
            vision_result = call_vision(
                "Describí esta captura de pantalla en detalle. "
                "¿Qué programa está abierto? ¿Qué elementos ves? "
                "¿Hay algo notable o importante en la pantalla?",
                b64, max_tokens=800, temperature=0.1
            )
            if vision_result:
                parts.append(f"[VISION IA]\n{vision_result}\n[/VISION IA]")
    except Exception:
        pass

    return "\n\n".join(parts) if parts else "No se pudo analizar la pantalla."


# ── Fallback: capture only active window ────────────────────────────

def capture_active_window() -> tuple[str, int, int, float, float] | tuple[None, None, None, None, None]:
    """
    Capture ONLY the active window (not full screen).
    Returns same format as capture_screen_resized.
    Much more token-efficient for AI analysis.
    """
    region = get_active_window_region()
    if not region:
        from actions._vision import capture_screen_resized
        return capture_screen_resized()

    try:
        import mss
        from PIL import Image
        import io, base64

        with mss.mss() as sct:
            mon = sct.monitors[1]
            full = Image.frombytes("RGB", (mon["width"], mon["height"]),
                                   sct.grab(mon).bgra, "raw", "BGRX")
            l, t, r, b = region
            # Clamp to monitor bounds
            l = max(0, l); t = max(0, t)
            r = min(mon["width"], r); b = min(mon["height"], b)
            if r <= l or b <= t:
                from actions._vision import capture_screen_resized
                return capture_screen_resized()
            img = full.crop((l, t, r, b))
            orig_w, orig_h = img.size
            max_size = 1280
            ratio = min(max_size / orig_w, max_size / orig_h) if orig_w > 0 and orig_h > 0 else 1
            new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            scale_x = orig_w / new_w if new_w else 1
            scale_y = orig_h / new_h if new_h else 1
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode(), orig_w, orig_h, scale_x, scale_y
    except Exception:
        from actions._vision import capture_screen_resized
        return capture_screen_resized()
