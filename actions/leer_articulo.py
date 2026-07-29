import os
import ctypes
import asyncio
import tempfile
import threading

from actions.web_search import web_search_raw, fetch_article_text

_tts_lock = threading.Lock()

_INTROS = [
    "Voy a contarte una historia. ",
    "Escucha con atención. ",
    "Te voy a leer algo interesante. ",
    "Acomódate y presta atención. ",
    "Esto te va a gustar. ",
    "",
]
_OUTROS = [
    " … y colorín colorado, este cuento se ha acabado.",
    " … y vivieron felices para siempre.",
    " … y ahí termina la historia.",
    "",
]


def _text_to_ssml(text: str) -> str:
    wrap = _INTROS and _OUTROS
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not paras:
        paras = [text.strip()]
    parts = ['<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-ES">']
    import random
    intro = random.choice(_INTROS)
    if intro:
        parts.append(f'{intro}<break time="400ms"/>')
    for i, para in enumerate(paras):
        if not para:
            continue
        r = random.randint(-3, 12)
        p = random.randint(-6, 6)
        phr = para
        if i == 0:
            phr = para
        elif i == len(paras) - 1:
            phr = f'<prosody rate="-5%" pitch="-3Hz">{para}</prosody>'
            parts.append(phr)
            continue
        parts.append(f'<prosody rate="{r:+.0f}%" pitch="{p:+.0f}Hz">{phr}</prosody>')
        if len(para) > 200:
            parts.append('<break time="300ms"/>')
        else:
            parts.append('<break time="100ms"/>')
    outro = random.choice(_OUTROS)
    if outro:
        parts.append(f'<prosody rate="-10%" pitch="-5Hz">{outro}</prosody>')
    parts.append("</speak>")
    return "\n".join(parts)


def _play_audio_async(text: str):
    """Generate TTS and play audio in a background thread. Only one at a time."""
    if not _tts_lock.acquire(blocking=False):
        return  # already playing, skip

    def _worker():
        mp3_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                mp3_path = fp.name

            import edge_tts
            import random
            voice = random.choice([
                "es-ES-AlvaroNeural",
                "es-ES-ElviraNeural",
                "es-MX-JorgeNeural",
                "es-MX-DaliaNeural",
                "es-AR-ElenaNeural",
                "es-CO-GonzaloNeural",
            ])
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                ssml = _text_to_ssml(text)
                loop.run_until_complete(
                    edge_tts.Communicate(
                        ssml, voice,
                        rate="+0%", pitch="+0Hz"
                    ).save(mp3_path)
                )
            finally:
                loop.close()

            if not os.path.exists(mp3_path):
                return
            if os.path.getsize(mp3_path) < 100:
                return

            ctypes.windll.winmm.mciSendStringW(
                f'open "{mp3_path}" type mpegvideo alias story', None, 0, 0)
            ctypes.windll.winmm.mciSendStringW('play story wait', None, 0, 0)
            ctypes.windll.winmm.mciSendStringW('close story', None, 0, 0)
        except Exception:
            pass
        finally:
            if mp3_path and os.path.exists(mp3_path):
                try:
                    os.unlink(mp3_path)
                except Exception:
                    pass
            _tts_lock.release()

    threading.Thread(target=_worker, daemon=True).start()


def _search_content(query: str, url: str = "") -> str:
    """Search for story/article content."""
    if url:
        content = fetch_article_text(url)
        if content and len(content) >= 100:
            return content

    if not query:
        return ""

    # Targeted story sites for better results
    story_sites = [
        "cuentoscortos.com", "chiquipedia.com", "bosquedefantasias.com",
        "cuentosinfantiles.net", "worldoftales.com", "pequelandia.org",
        "educapeques.com", "guiainfantil.com", "etapainfantil.com",
    ]
    for site in story_sites:
        results = web_search_raw(f"site:{site} {query}", max_results=5)
        if results:
            # Take best 2 as candidates
            candidates = results[:2]
            content = fetch_article_text(results[0]["url"])
            if content and len(content) >= 200:
                return content

    results = web_search_raw(query, max_results=3)
    for r in results:
        content = fetch_article_text(r["url"])
        if content and len(content) >= 100:
            return content

    return ""


def leer_articulo(parameters: dict, player=None) -> str:
    """
    Busca un artículo/cuento en la web, extrae su contenido,
    genera audio con edge-tts y lo reproduce al instante.
    Devuelve string vacío para que el LLM no interrumpa.
    """
    query = parameters.get("query", "").strip()
    url = parameters.get("url", "").strip()

    if not query and not url:
        return "Proporciona un 'query' de búsqueda o una 'url'."

    content = _search_content(query, url)

    if not content or len(content) < 100:
        return "No se pudo encontrar contenido para leer en la web."

    if len(content) > 120000:
        content = content[:120000] + "\n... [Fin del contenido]"

    # Fire-and-forget: play audio in background, return immediately
    _play_audio_async(content)

    return ""
