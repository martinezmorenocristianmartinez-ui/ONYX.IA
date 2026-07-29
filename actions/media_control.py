import time
from actions._browser_launch import open_url, _find_browser_window
from actions._vision import get_api_key, vision_click as _vision_click


_PLATFORM_URLS = {
    "youtube": "https://www.youtube.com",
    "tiktok": "https://www.tiktok.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "crunchyroll": "https://www.crunchyroll.com",
    "prime video": "https://www.primevideo.com",
}


def _ensure_platform(platform: str):
    """If no browser is open, launch one with the platform URL."""
    if not platform:
        return
    if _find_browser_window():
        return  # hay navegador abierto
    url = _PLATFORM_URLS.get(platform)
    if url:
        open_url(url)
        time.sleep(3)


def _focus_window(title_contains: str) -> bool:
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            t = win.title.strip().lower()
            if title_contains in t:
                try:
                    if win.isMinimized:
                        win.restore()
                    win.activate()
                    return True
                except Exception:
                    pass
    except Exception:
        pass
    return False





def media_control(parameters: dict, player=None) -> str:
    """
    Controla cualquier multimedia: pausar, reanudar, reproducir, deslizar,
    dar like, comentar, compartir. Funciona en YouTube, TikTok, etc.
    TikTok usa k para pausa (no space que desliza), flechas para deslizar.
    """
    action = parameters.get("action", "").lower().strip()
    platform = parameters.get("platform", "").lower().strip()

    if not action:
        return "Necesito una acción: pause, resume, play, next, prev, swipe_up, swipe_down, like, comment, share."

    try:
        import pyautogui

        # ── Like / Comentar / Compartir (TikTok y otros) ──
        _VISION_DESCS = {
            "like":    ["botón de me gusta", "corazón like", "botón like", "like button"],
            "comment": ["botón de comentarios", "botón comentar", "comments button"],
            "share":   ["botón de compartir", "compartir video", "share button"],
        }

        if action in _VISION_DESCS:
            _ensure_platform(platform or "tiktok")
            _focus_window(platform or "tiktok")
            time.sleep(0.3)
            # Intento 1: tecla 'l' para like en TikTok web
            if action == "like":
                pyautogui.press("l")
                time.sleep(0.5)
            # Intento 2: visión por IA
            for desc in _VISION_DESCS[action]:
                if _vision_click(desc):
                    break
            msgs = {"like": "Like dado, Señor Cristian.", "comment": "Comentarios abiertos, Señor Cristian.", "share": "Compartir abierto, Señor Cristian."}
            return msgs.get(action, f"{action} ejecutado, Señor Cristian.")

        # ── Swipe (deslizar en TikTok) ──
        if action in ("swipe_down", "swipe_next", "down"):
            _ensure_platform("tiktok")
            _focus_window("tiktok")
            time.sleep(0.3)
            pyautogui.press("down")
            return "Deslizado al siguiente video, Señor Cristian."
        if action in ("swipe_up", "swipe_prev", "up"):
            _ensure_platform("tiktok")
            _focus_window("tiktok")
            time.sleep(0.3)
            pyautogui.press("up")
            return "Deslizado al video anterior, Señor Cristian."

        # ── Next / Prev (pistas en Spotify, video en YouTube) ──
        if action in ("next", "skip"):
            if "tiktok" in platform:
                _ensure_platform("tiktok")
                _focus_window("tiktok")
                time.sleep(0.3)
                pyautogui.press("down")
                return "Siguiente video de TikTok, Señor Cristian."
            pyautogui.press("nexttrack")
            return "Listo, Señor Cristian. Siguiente."
        if action in ("prev", "previous", "back"):
            if "tiktok" in platform:
                _ensure_platform("tiktok")
                _focus_window("tiktok")
                time.sleep(0.3)
                pyautogui.press("up")
                return "Video anterior de TikTok, Señor Cristian."
            pyautogui.press("prevtrack")
            return "Listo, Señor Cristian. Anterior."

        # ── Pause / Resume / Play ──
        # Intento 1: tecla multimedia universal
        pyautogui.press("playpause")
        time.sleep(0.3)

        # Intento 2: tecla específica por plataforma
        # TikTok usa k para pausa (space desliza al siguiente video)
        # YouTube usa space o k
        if "tiktok" in platform:
            _ensure_platform("tiktok")
            _focus_window("tiktok")
            time.sleep(0.3)
            pyautogui.press("k")
        elif "youtube" in platform:
            _ensure_platform("youtube")
            _focus_window("youtube")
            time.sleep(0.3)
            pyautogui.press("space")
        elif not platform:
            _ensure_platform("youtube")
            for kw, key in (("youtube", "space"), ("tiktok", "k"),
                            ("netflix", "space"), ("crunchyroll", "space"),
                            ("prime video", "space")):
                if _focus_window(kw):
                    time.sleep(0.3)
                    pyautogui.press(key)
                    break

        # Intento 3: visión por IA para encontrar botón play/pausa
        if parameters.get("vision", False):
            descs = ["botón de pausa", "botón de play", "botón de pausa || reproducir"]
            for desc in descs:
                if _vision_click(desc):
                    break

        msg = "Reproducción reanudada." if action in ("play", "resume", "reanudar", "continuar") else "Reproducción pausada."
        return msg

    except Exception as e:
        return f"Error controlando multimedia: {e}"
