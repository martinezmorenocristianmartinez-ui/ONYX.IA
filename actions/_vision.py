"""
_vision.py — Shared vision utility for ONYX.
Unified screen capture, AI vision API calls, element detection, and clicking.
All vision-using tools should import from here to avoid code duplication.
"""
import base64, io, json, re, time, urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

VISION_MODEL = "google/gemini-2.5-flash"
VISION_TIMEOUT = 120
LOCAL_VISION_MODEL = "llava"
OLLAMA_HOST = "http://localhost:11434"


# ── API Key ───────────────────────────────────────────────────────────

def get_api_key() -> str:
    """Read API key from config/api_keys.json."""
    try:
        data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("openrouter_api_key", "") or data.get("google_api_key", "") or data.get("gemini_api_key", "")
    except Exception:
        return ""


def _get_gemini_client():
    """Create a Gemini client using the API key from config."""
    try:
        import google.genai as genai
        from google.genai import types
        data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        key = data.get("gemini_api_key", "")
        if key:
            return genai.Client(api_key=key, http_options={"api_version": "v1beta"})
    except Exception:
        pass
    return None


# ── Screen Capture ────────────────────────────────────────────────────

def capture_screen() -> tuple[str, int, int] | tuple[None, None, None]:
    """Full-resolution screenshot of main monitor. Returns (b64, w, h)."""
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            mon = sct.monitors[1]
            orig_w, orig_h = mon["width"], mon["height"]
            img = Image.frombytes("RGB", (orig_w, orig_h), sct.grab(mon).bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode(), orig_w, orig_h
    except Exception:
        return None, None, None


def capture_screen_resized(max_size: int = 1280,
                           region_pct: tuple[int, int, int, int] | None = None
                           ) -> tuple[str, int, int, float, float] | tuple[None, None, None, None, None]:
    """
    Capture monitor, optionally crop to a percentage-based region, then resize.
    region_pct: (left_pct, top_pct, right_pct, bottom_pct) as percentages (0-100).
    Returns (b64, orig_w, orig_h, scale_x, scale_y).
    """
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            mon = sct.monitors[1]
            mon_w, mon_h = mon["width"], mon["height"]
            img = Image.frombytes("RGB", (mon_w, mon_h), sct.grab(mon).bgra, "raw", "BGRX")

            # Apply region crop
            if region_pct:
                l = int(mon_w * region_pct[0] / 100)
                t = int(mon_h * region_pct[1] / 100)
                r = int(mon_w * region_pct[2] / 100)
                b = int(mon_h * region_pct[3] / 100)
                l = max(0, l); t = max(0, t)
                r = min(mon_w, r); b = min(mon_h, b)
                if r > l and b > t:
                    img = img.crop((l, t, r, b))

            orig_w, orig_h = img.size
            ratio = min(max_size / orig_w, max_size / orig_h)
            new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            scale_x = orig_w / new_w if new_w else 1
            scale_y = orig_h / new_h if new_h else 1
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode(), orig_w, orig_h, scale_x, scale_y
    except Exception:
        return None, None, None, None, None


def capture_active_window(max_size: int = 1280
                          ) -> tuple[str, int, int, float, float] | tuple[None, None, None, None, None]:
    """Capture only the active window. Falls back to full screen."""
    try:
        from actions._screen_analyzer import get_active_window_region
        region = get_active_window_region()
        if region:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                mon = sct.monitors[1]
                full = Image.frombytes("RGB", (mon["width"], mon["height"]),
                                       sct.grab(mon).bgra, "raw", "BGRX")
                l, t, r, b = region
                l = max(0, l); t = max(0, t)
                r = min(mon["width"], r); b = min(mon["height"], b)
                if r > l and b > t:
                    img = full.crop((l, t, r, b))
                    ow, oh = img.size
                    ratio = min(max_size / ow, max_size / oh)
                    nw, nh = int(ow * ratio), int(oh * ratio)
                    img = img.resize((nw, nh), Image.LANCZOS)
                    sx = ow / nw if nw else 1
                    sy = oh / nh if nh else 1
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    return base64.b64encode(buf.getvalue()).decode(), ow, oh, sx, sy
    except Exception:
        pass
    return capture_screen_resized(max_size)


# ── Local Vision (Ollama) ─────────────────────────────────────────────

def _ollama_available() -> bool:
    """Check if Ollama is running and has a real vision model."""
    return bool(_list_ollama_vision_models())


_VISION_MODEL_KEYS = ("llava", "moondream", "bakllava", "llama3.2-vision",
                      "llama3-vision", "qwen2-vl", "qwen2.5-vl", "minicpm-v", "llava-llama3")


def _list_ollama_vision_models() -> list[str]:
    """Return available REAL vision model names from Ollama."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])
                    if any(v in m.get("name", "").lower() for v in _VISION_MODEL_KEYS)]
    except Exception:
        return []


def call_vision_local(prompt: str, base64_img: str, temperature: float = 0.0) -> str:
    """Send a vision prompt + image to local Ollama vision model (formato nativo Ollama)."""
    if not base64_img:
        return ""
    models = _list_ollama_vision_models()
    if not models:
        return ""
    model = models[0]
    try:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [base64_img],
            }],
            "stream": False,
            "options": {"temperature": temperature},
        }
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result["message"]["content"].strip()
    except Exception:
        return ""


# ── AI Vision Call ────────────────────────────────────────────────────

def call_vision(prompt: str, base64_img: str, max_tokens: int = 4000, temperature: float = 0.0) -> str:
    """Send a vision prompt + image to the AI model.
    Tries local Ollama first, then Gemini, then OpenRouter."""
    if not base64_img:
        return ""
    # Try local Ollama first
    local_result = call_vision_local(prompt, base64_img, temperature)
    if local_result:
        return local_result
    # Try Gemini
    try:
        gemini_client = _get_gemini_client()
        if gemini_client:
            from google.genai import types
            import base64 as _b64
            img_bytes = _b64.b64decode(base64_img)
            resp = gemini_client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=[
                    types.Content(parts=[
                        types.Part(text=prompt),
                        types.Part(inline_data=types.Blob(data=img_bytes, mime_type="image/jpeg")),
                    ])
                ],
                config={"max_output_tokens": max_tokens, "temperature": temperature},
            )
            if resp and resp.text:
                return resp.text.strip()
    except Exception:
        pass
    # Fall back to OpenRouter
    api_key = get_api_key()
    if not api_key:
        return ""
    try:
        payload = {
            "model": VISION_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]
            }]
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=VISION_TIMEOUT) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


# ── Coordinate Parsing ────────────────────────────────────────────────

def extract_coords(text: str) -> list[int] | None:
    """Extract a single [X, Y] coordinate pair from AI response text."""
    m = re.search('\\[(\\s*\\d+\\s*,\\s*\\d+\\s*)\\]', text)
    if not m:
        return None
    try:
        coords = json.loads(f"[{m.group(1)}]")
        if len(coords) == 2 and coords[0] > 0 and coords[1] > 0:
            return coords
    except Exception:
        pass
    return None


def extract_all_coords(text: str) -> list[list[int]]:
    """Extract all [X, Y] coordinate pairs from AI response text."""
    results = []
    for m in re.finditer('\\[(\\s*\\d+\\s*,\\s*\\d+\\s*)\\]', text):
        try:
            coords = json.loads(f"[{m.group(1)}]")
            if len(coords) == 2 and coords[0] > 0 and coords[1] > 0:
                results.append(coords)
        except Exception:
            pass
    return results


# ── High-Level Actions ────────────────────────────────────────────────

def vision_find(description: str, max_size: int = 1280,
                region_pct: tuple[int, int, int, int] | None = None,
                use_active_window: bool = False) -> tuple[int, int] | None:
    """
    Find an element on screen by description using AI vision.
    Supports region cropping and active-window-only capture.
    """
    if use_active_window:
        b64, orig_w, orig_h, scale_x, scale_y = capture_active_window(max_size)
    else:
        b64, orig_w, orig_h, scale_x, scale_y = capture_screen_resized(max_size, region_pct)
    if not b64:
        return None

    prompt = (
        f"Find EXACTLY on this screen: '{description}'. "
        f"Return ONLY the center coordinates as [X,Y] of the element. "
        f"If you are not completely sure, return [0,0]."
    )
    response = call_vision(prompt, b64)
    if not response:
        return None

    coords = extract_coords(response)
    if not coords:
        return None

    screen_x = int(coords[0] * scale_x)
    screen_y = int(coords[1] * scale_y)
    return (screen_x, screen_y)


def vision_find_advanced(description: str) -> dict:
    """
    Find element using ALL available strategies (OCR, UI tree, AI vision).
    Returns dict with found, x, y, confidence, strategy, text.
    """
    try:
        from actions._screen_analyzer import find_element_advanced
        return find_element_advanced(description)
    except ImportError:
        # Fallback: AI vision only
        coords = vision_find(description)
        if coords:
            return {"found": True, "x": coords[0], "y": coords[1],
                    "confidence": "medium", "strategy": "ai_vision", "text": ""}
        return {"found": False, "x": 0, "y": 0, "confidence": "low",
                "strategy": "none", "text": ""}


def vision_click(description: str, button: str = "left") -> bool:
    """Find element and click."""
    coords = vision_find(description)
    if not coords:
        return False
    try:
        import pyautogui
        pyautogui.moveTo(coords[0], coords[1], duration=0.2)
        time.sleep(0.1)
        pyautogui.click(button=button)
        return True
    except Exception:
        return False


def vision_click_advanced(description: str, button: str = "left") -> bool:
    """Find element using ALL strategies, then click."""
    result = vision_find_advanced(description)
    if not result.get("found"):
        return False
    try:
        import pyautogui
        pyautogui.moveTo(result["x"], result["y"], duration=0.2)
        time.sleep(0.1)
        pyautogui.click(button=button)
        return True
    except Exception:
        return False


def vision_get_text(question: str = "¿Qué ves en esta pantalla?") -> str:
    """Ask a question about the current screen."""
    b64, _, _ = capture_screen()
    if not b64:
        return ""
    return call_vision(question, b64, max_tokens=1000, temperature=0.1)
