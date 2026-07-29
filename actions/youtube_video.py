"""YouTube video launching action with ad skipping using recorded positions."""
from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from actions._browser_launch import open_url
from actions._vision import get_api_key, capture_screen_resized, extract_coords, call_vision

# Importar la función para obtener posiciones grabadas
try:
    from actions.macros_control import get_position
except ImportError:
    get_position = None


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _is_url(text: str) -> bool:
    return text.startswith(("http://", "https://", "www."))


def _normalize_youtube_url(url: str) -> str:
    if url.startswith("www."):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    video_id = ""
    if parsed.netloc.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    elif "youtube.com" in parsed.netloc:
        video_id = query.get("v", [""])[0]
        if not video_id and parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/")[2]

    if VIDEO_ID_RE.match(video_id):
        return f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
    return url


def _request_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="ignore")


def _video_ids_from_json(value) -> list[str]:
    ids: list[str] = []
    if isinstance(value, dict):
        video_id = value.get("videoId")
        if isinstance(video_id, str) and VIDEO_ID_RE.match(video_id):
            ids.append(video_id)
        for child in value.values():
            ids.extend(_video_ids_from_json(child))
    elif isinstance(value, list):
        for child in value:
            ids.extend(_video_ids_from_json(child))
    return ids


def _extract_yt_initial_data(page: str) -> dict | None:
    marker = "var ytInitialData = "
    start = page.find(marker)
    if start < 0:
        marker = "ytInitialData = "
        start = page.find(marker)
    if start < 0:
        return None

    start += len(marker)
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(page)):
        ch = page[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = page[start : idx + 1]
                try:
                    return json.loads(raw)
                except Exception:
                    return None
    return None


def _dedupe(ids: list[str]) -> list[str]:
    seen = set()
    clean: list[str] = []
    for video_id in ids:
        if VIDEO_ID_RE.match(video_id) and video_id not in seen:
            seen.add(video_id)
            clean.append(video_id)
    return clean


def find_youtube_videos(query: str, max_results: int = 10) -> list[str]:
    """Return list of YouTube watch URLs for search results (top N)."""
    query = query.strip()
    if not query:
        return []
    if _is_url(query):
        return [_normalize_youtube_url(query)]

    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://www.youtube.com/results?search_query={encoded}&sp=EgIQAQ%253D%253D"
    page = _request_text(search_url)

    ids: list[str] = []
    initial_data = _extract_yt_initial_data(page)
    if initial_data:
        ids.extend(_video_ids_from_json(initial_data))

    ids.extend(re.findall(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', page))
    ids.extend(re.findall(r"watch\?v=([A-Za-z0-9_-]{11})", html.unescape(page)))

    ids = _dedupe(ids)
    return [f"https://www.youtube.com/watch?v={vid}&autoplay=1" for vid in ids[:max_results]]


def find_first_youtube_video(query: str) -> str | None:
    """Return a direct YouTube watch URL for the first video search result."""
    videos = find_youtube_videos(query, max_results=1)
    return videos[0] if videos else None


def _load_saved_positions() -> dict:
    pos_file = Path(__file__).resolve().parent.parent / "config" / "saved_positions.json"
    try:
        return json.loads(pos_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _try_skip_actions():
    """Solo un clic en la posición guardada. Nada más."""
    try:
        import pyautogui
    except ImportError:
        return

    saved = _load_saved_positions()
    pos = saved.get("saltar_anuncio")
    if pos:
        x, y = pos.get("x"), pos.get("y")
        if x and y:
            pyautogui.moveTo(x, y, duration=0.2)
            time.sleep(0.05)
            pyautogui.click()


def _skip_youtube_ads():
    """Saltar anuncios de YouTube SOLO cuando el botón está claramente visible."""
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        return

    time.sleep(3)

    target = None
    for win in gw.getAllWindows():
        title = win.title.strip().lower()
        if "youtube" in title and any(b in title for b in ("chrome", "edge", "firefox", "brave", "opera", " - ")):
            target = win
            break

    if not target:
        return

    try:
        if target.isMinimized:
            target.restore()
        target.activate()
    except Exception:
        pass

    time.sleep(1)

    if not get_api_key():
        return

    start_time = time.time()
    max_total_time = 30

    while (time.time() - start_time) < max_total_time:
        try:
            b64, _, _, scale_x, scale_y = capture_screen_resized(1280)
            if not b64:
                time.sleep(1.5)
                continue

            text = call_vision(
                'Contesta EXACTAMENTE y SOLAMENTE "SI" o "NO" (nada mas). '
                'Hay un boton de "Saltar", "Skip Ad" o "Saltar anuncio" claramente visible en la captura de pantalla de YouTube?',
                b64, max_tokens=100, temperature=0.0
            )
            if not text:
                time.sleep(1.5)
                continue

            if "SI" not in text.upper():
                time.sleep(1.5)
                continue

            # Botón detectado, obtener coordenadas
            text2 = call_vision(
                'Encuentra el boton de "Saltar", "Skip Ad" o "Saltar anuncio" en la captura de YouTube. '
                "Devuelve SOLAMENTE sus coordenadas [X,Y] como un array JSON. NADA MAS. "
                "Si no lo encuentra con 100% de seguridad, contesta [0,0].",
                b64, max_tokens=150, temperature=0.0
            )
            if not text2:
                time.sleep(1.5)
                continue

            coords = extract_coords(text2)
            if coords:
                x, y = int(coords[0] * scale_x), int(coords[1] * scale_y)
                pyautogui.moveTo(x, y, duration=0.25)
                time.sleep(0.15)
                pyautogui.click()
                time.sleep(3)
                break
        except Exception:
            pass
        time.sleep(1.5)


def _youtube_media_key(key):
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        return False
    for win in gw.getAllWindows():
        title = win.title.strip().lower()
        if "youtube" in title and any(b in title for b in ("chrome", "edge", "firefox", "brave", "opera", " - ")):
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
            except Exception:
                pass
            time.sleep(0.3)
            pyautogui.press(key)
            return True
    return False


def youtube_video(parameters: dict, response=None, player=None) -> str:
    """Search for and play the first YouTube video immediately (no auto ad-skipping anymore)."""
    action = str(parameters.get("action", "play") or "play").lower()
    query = (parameters.get("query") or parameters.get("url") or "").strip()

    if action in ("pause", "pausa", "pausar"):
        _youtube_media_key("space")
        return "Listo, Señor Cristian. Video pausado."

    if action in ("resume", "reanudar", "continuar"):
        _youtube_media_key("space")
        return "Listo, Señor Cristian. Video reanudado."

    if not query:
        return "Señor Cristian, dime qué video quieres ver en YouTube."

    try:
        direct_url = find_first_youtube_video(query)
        if direct_url:
            open_url(direct_url)
            msg = f"Reproduciendo '{query}' en YouTube: {direct_url}"
            if player:
                player.write_log(msg)
            return f"Listo, Señor Cristian. Reproduciendo el primer resultado de '{query}'."

        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        open_url(search_url)
        return (
            f"Abrí la busqueda de YouTube para '{query}', pero YouTube no entrego un video directo "
            "en la respuesta inicial."
        )
    except Exception as exc:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        try:
            open_url(search_url)
        except Exception:
            pass
        return f"No pude iniciar el video directo; abri la busqueda como respaldo. Detalle: {exc}"

def saltar_anuncios_youtube(parameters: dict, response=None, player=None) -> str:
    """
    Salta anuncios de YouTube.
    Primero intenta detección visual por IA.
    Si falla (sin API), usa la macro de posición guardada como respaldo.
    Si la IA confirmó que NO hay botón visible, no hace nada (el usuario ya lo saltó).
    """
    _saltado = False
    _ia_confirmo_no_hay_boton = False

    # Intento 1: detección visual por IA
    try:
        import pyautogui
        import pygetwindow as gw

        target = None
        for win in gw.getAllWindows():
            title = win.title.strip().lower()
            if "youtube" in title and any(b in title for b in ("chrome", "edge", "firefox", "brave", "opera", " - ")):
                target = win
                break

        if target and get_api_key():
            try:
                if target.isMinimized:
                    target.restore()
                target.activate()
            except Exception:
                pass
            time.sleep(1)

            b64, _, _, scale_x, scale_y = capture_screen_resized(1280)
            if b64:
                text = call_vision(
                    'Encuentra el boton de "Saltar", "Skip Ad" o "Saltar anuncio" visible en la captura de YouTube. '
                    "Devuelve SOLAMENTE sus coordenadas [X,Y] como un array JSON. "
                    "Si no ves ningun boton visible para saltar, devuelve [0,0].",
                    b64, max_tokens=150, temperature=0.0
                )
                if text:
                    coords = extract_coords(text)
                    if coords and coords[0] > 0 and coords[1] > 0:
                        x, y = int(coords[0] * scale_x), int(coords[1] * scale_y)
                        pyautogui.moveTo(x, y, duration=0.25)
                        time.sleep(0.15)
                        pyautogui.click()
                        _saltado = True
                    else:
                        _ia_confirmo_no_hay_boton = True
    except Exception:
        pass

    if _saltado:
        return "Listo, Senor Cristian. Anuncio saltado por deteccion visual."

    if _ia_confirmo_no_hay_boton:
        return "No hay anuncio visible, Senor Cristian. Parece que ya fue saltado."

    # Intento 2: macro de posicion guardada (sin IA disponible)
    try:
        import pyautogui
        pos = get_position("saltar_anuncio")
        if pos:
            pyautogui.moveTo(pos["x"], pos["y"], duration=0.3)
            time.sleep(0.2)
            pyautogui.click()
            return "Listo, Senor Cristian. Anuncio saltado con la macro guardada."
    except Exception:
        pass

    return "No pude saltar el anuncio, Senor Cristian. No hay API key configurada ni macro guardada."
