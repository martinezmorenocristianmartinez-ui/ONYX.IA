"""
local_intents.py - Detección determinística de comandos para el modo LOCAL.

Los modelos locales pequeños (ej. qwen2.5:1.5b) no son fiables para
function-calling. Para que ONYX siga ejecutando comandos explícitos sin la
nube, este módulo detecta intenciones claras por patrones y devuelve la
herramienta + argumentos a ejecutar, sin depender del LLM.

Hoy cubre la necesidad reportada (búsqueda de archivos Word/PDF/etc.) y se
puede extender con más intenciones.
"""
from __future__ import annotations

import re

# Disparadores de búsqueda (con y sin tilde).
_SEARCH_TRIGGERS = (
    "busca", "buscá", "buscame", "buscáme", "buscar", "busque", "búscame",
    "encontra", "encontrá", "encontrame", "encontrar", "encuentra", "encuentrame",
    "halla", "hallá", "hallar", "ubica", "ubicá", "ubicar", "localiza", "localizá",
)

# Palabras clave de tipo de archivo -> extensión (puede ser múltiple, separada por coma).
_EXT_MAP = {
    "powerpoint": ".pptx", "presentación": ".pptx", "presentacion": ".pptx", "pptx": ".pptx",
    "documento de word": ".docx", "archivo de word": ".docx", "word": ".docx", "docx": ".docx",
    "hoja de cálculo": ".xlsx", "hoja de calculo": ".xlsx", "excel": ".xlsx", "xlsx": ".xlsx",
    "pdf": ".pdf",
    # Imágenes: buscar TODAS las extensiones comunes, no solo .png.
    "imagen": ".png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff",
    "imagenes": ".png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff",
    "foto": ".png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff",
    "fotos": ".png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff",
    "jpg": ".jpg,.jpeg", "jpeg": ".jpg,.jpeg", "png": ".png",
    "texto plano": ".txt", "bloc de notas": ".txt", "txt": ".txt",
    "video": ".mp4,.avi,.mkv,.mov", "videos": ".mp4,.avi,.mkv,.mov",
    "música": ".mp3,.wav,.flac,.m4a", "musica": ".mp3,.wav,.flac,.m4a",
    "cancion": ".mp3,.wav,.flac,.m4a", "canción": ".mp3,.wav,.flac,.m4a",
}

_FILE_WORDS = ("archivo", "archivos", "documento", "documentos", "fichero",
               "ficheros", "doc", "docs", "planilla", "planillas")

# Palabras de ubicación -> atajo de carpeta de file_controller.
# OJO: "documentos" NO se mapea acá a propósito — "los documentos de X" casi
# siempre significa "archivos llamados X" (búsqueda amplia), no la carpeta
# Documentos. Restringir ahí hacía que se perdieran archivos del Escritorio.
_LOCATION_MAP = {
    "escritorio": "desktop", "desktop": "desktop",
    "descargas": "downloads", "downloads": "downloads",
    "imagenes": "pictures", "imágenes": "pictures",
    "musica": "music", "música": "music",
    "videos": "videos", "vídeos": "videos",
    "proyecto": "project", "proyecto de onyx": "project",
}

# Indicadores de que la búsqueda es WEB (no de archivos locales).
_WEB_INDICATORS = (
    "internet", "google", "en la web", "online", "navegador", "buscador",
    "informacion sobre", "información sobre", "noticias", "que es ", "qué es ",
    "quien es", "quién es", "significado de", "definicion", "definición",
    "precio de", "cotizacion", "cotización", "clima", "weather",
)

# Tokens de relleno que se eliminan al extraer el nombre del archivo.
_FILLER = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "mi", "mis",
    "de", "del", "en", "que", "se", "llama", "llamado", "llamada", "titulado",
    "titulada", "nombrado", "formato", "tipo", "por", "favor", "porfa",
    "archivo", "documento", "fichero", "doc", "planilla", "llamada",
    "archivos", "documentos", "ficheros", "docs", "planillas", "documents",
    "onyx", "che", "dale", "buscame", "buscáme", "búscame",
    # Ubicaciones (se mapean a 'path', no son parte del nombre).
    "escritorio", "desktop", "descargas", "downloads",
    "imagenes", "fotos", "musica", "videos", "proyecto", "carpeta",
}


def _strip_accents(s: str) -> str:
    table = str.maketrans("áéíóúü", "aeiouu")
    return s.translate(table)


# ── Disparadores de otros comandos offline ──────────────────────────
_OPEN_TRIGGERS = (
    "abri", "abrir", "abre", "abrime", "abreme", "ejecuta", "ejecutar",
    "ejecutame", "lanza", "lanzar", "inicia", "iniciar", "arranca", "arrancar",
)
_CLOSE_TRIGGERS = (
    "cerra", "cerrar", "cierra", "cerrame", "cierrame", "cierre", "cierra el",
)
_PLAY_TRIGGERS = (
    "pone", "poner", "pon", "ponme", "poneme", "reproduci", "reproduce",
    "reproducir", "escucha", "escuchar", "escuchame", "quiero escuchar", "ponete",
)
_APP_FILLER = {
    "el", "la", "los", "las", "un", "una", "mi", "app", "aplicacion",
    "programa", "favor", "por", "porfavor", "onyx", "che", "dale", "me", "el",
    "de", "y", "ahora", "ya",
}
_PLAY_FILLER = _APP_FILLER | {
    "musica", "cancion", "tema", "video", "tema", "en", "youtube", "spotify",
    "play", "algo", "una", "un", "el", "la", "reproduccion", "sonido", "pista",
}


def _clean_tokens(text: str, drop: set) -> str:
    tokens = re.findall(r"[a-z0-9_]+", text)
    keep = [t for t in tokens if t not in drop and len(t) > 1]
    return " ".join(keep).strip()


def detect_system_control(low_na: str) -> dict | None:
    """Volumen y brillo (computer_settings) — todo local."""
    has_mute = any(w in low_na for w in ("silenci", "mutea", "mute"))
    has_vol = "volumen" in low_na or "volume" in low_na or "sonido" in low_na or has_mute
    has_bri = "brillo" in low_na or "brightness" in low_na
    if not (has_vol or has_bri):
        return None
    target = "volume" if has_vol else "brightness"

    if target == "volume" and any(w in low_na for w in ("silenci", "mutea", "mute", "sin sonido", "sin volumen")):
        return {"tool": "computer_settings", "args": {"action": "volume", "description": "silenciar"}}
    if target == "volume" and any(w in low_na for w in ("activa el sonido", "quita el silencio", "unmute", "con sonido")):
        return {"tool": "computer_settings", "args": {"action": "volume", "description": "unmute"}}

    m = re.search(r"\b(\d{1,3})\b", low_na)
    if m:
        return {"tool": "computer_settings", "args": {"action": target, "value": m.group(1)}}

    if any(w in low_na for w in ("subi", "sube", "subir", "subile", "aumenta", "aumentar", "incrementa", "arriba", "mas ")):
        return {"tool": "computer_settings", "args": {"action": target, "value": "subir"}}
    if any(w in low_na for w in ("baja", "bajar", "bajale", "reduce", "reducir", "disminuye", "abajo", "menos")):
        return {"tool": "computer_settings", "args": {"action": target, "value": "bajar"}}
    return None


def detect_media_control(low_na: str) -> dict | None:
    """Pausar / reanudar / siguiente / anterior (media_control)."""
    if any(w in low_na for w in ("pausa", "pausá", "pausar", "detene", "detené", "detener", "frena", "para la", "pará la")):
        return {"tool": "media_control", "args": {"action": "pause"}}
    if any(w in low_na for w in ("reanuda", "reanudá", "segui reproduciendo", "continua", "continúa", "resume", "despausa")):
        return {"tool": "media_control", "args": {"action": "resume"}}
    if any(w in low_na for w in ("siguiente cancion", "proxima cancion", "próxima", "siguiente tema", "siguiente pista", "salta la cancion", "next")):
        return {"tool": "media_control", "args": {"action": "next"}}
    if any(w in low_na for w in ("cancion anterior", "tema anterior", "pista anterior", "anterior cancion", "volve a la anterior")):
        return {"tool": "media_control", "args": {"action": "prev"}}
    return None


def detect_play(text: str, low_na: str) -> dict | None:
    """Reproducir música/video (youtube_video play)."""
    if not any(re.search(r"\b" + re.escape(t) + r"\b", low_na) for t in _PLAY_TRIGGERS):
        return None
    # Debe sugerir reproducción de contenido (no "poné el volumen", ya cubierto antes).
    query = _strip_play_prefix(text)
    if not query:
        return None
    return {"tool": "youtube_video", "args": {"action": "play", "query": query}}


def _strip_play_prefix(text: str) -> str:
    low = _strip_accents(text.lower())
    work = low
    for t in _PLAY_TRIGGERS:
        work = re.sub(r"\b" + re.escape(t) + r"\b", " ", work)
    # Mantener el orden original de las palabras significativas.
    tokens = re.findall(r"[a-z0-9_]+", work)
    keep = [tok for tok in tokens if tok not in _PLAY_FILLER and len(tok) > 1]
    return " ".join(keep).strip()


def detect_open_app(text: str, low_na: str) -> dict | None:
    """Abrir una aplicación (open_app)."""
    if not any(re.search(r"\b" + re.escape(t) + r"\b", low_na) for t in _OPEN_TRIGGERS):
        return None
    # No confundir con búsqueda de archivos.
    if any(w in low_na for w in _FILE_WORDS):
        return None
    work = low_na
    for t in _OPEN_TRIGGERS:
        work = re.sub(r"\b" + re.escape(t) + r"\b", " ", work)
    name = _clean_tokens(work, _APP_FILLER)
    if not name:
        return None
    return {"tool": "open_app", "args": {"app_name": name}}


def detect_close_app(text: str, low_na: str) -> dict | None:
    """Cerrar una aplicación/ventana (close_app)."""
    if not any(re.search(r"\b" + re.escape(t) + r"\b", low_na) for t in _CLOSE_TRIGGERS):
        return None
    work = low_na
    for t in _CLOSE_TRIGGERS:
        work = re.sub(r"\b" + re.escape(t) + r"\b", " ", work)
    name = _clean_tokens(work, _APP_FILLER | {"ventana", "ventanas", "esto", "todo"})
    args = {"app_name": name} if name else {}
    return {"tool": "close_app", "args": args}


# ── Análisis de imágenes (local_image_analysis) ──────────────────────
_IMG_ANALYZE_TRIGGERS = (
    "analiza", "analizame", "analiza", "describi", "describe", "describime",
    "reconoce", "interpreta", "examina", "que ves en",
)
_IMG_QUESTION = (
    "que hay en", "que se ve", "que muestra", "que dice", "que aparece",
    "que contiene", "que es esta", "que es esa",
)
_IMG_WORDS = ("imagen", "imagenes", "foto", "fotos", "captura", "screenshot", "dibujo", "grafico")
_IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|gif|webp|bmp|tiff)\b")
_IMG_NAME_FILLER = {
    "esta", "este", "esa", "ese", "esto", "imagen", "imagenes", "foto", "fotos",
    "captura", "screenshot", "dibujo", "grafico", "que", "hay", "ve", "se", "ves",
    "muestra", "dice", "aparece", "contiene", "es", "del", "la", "el", "los", "las",
    "un", "una", "mi", "de", "en", "por", "favor", "onyx", "esto",
}


def detect_image_analysis(text: str, low_na: str) -> dict | None:
    has_trigger = (
        any(re.search(r"\b" + re.escape(t) + r"\b", low_na) for t in _IMG_ANALYZE_TRIGGERS)
        or any(q in low_na for q in _IMG_QUESTION)
    )
    has_img = any(w in low_na for w in _IMG_WORDS) or bool(_IMG_EXT_RE.search(low_na))
    if not (has_trigger and has_img):
        return None

    # Extraer nombre/ruta del archivo de imagen, si se menciona.
    name = ""
    m = re.search(r"([\w\-. ]+\.(?:jpg|jpeg|png|gif|webp|bmp|tiff))", low_na)
    if m:
        name = m.group(1).strip()
    else:
        work = low_na
        for t in _IMG_ANALYZE_TRIGGERS:
            work = re.sub(r"\b" + re.escape(t) + r"\b", " ", work)
        for q in _IMG_QUESTION:
            work = work.replace(q, " ")
        name = _clean_tokens(work, _IMG_NAME_FILLER)

    args: dict = {"question": text}
    if name:
        args["name"] = name
    return {"tool": "local_image_analysis", "args": args}


def detect_file_search(text: str) -> dict | None:
    """Detecta un comando de búsqueda de archivos.

    Devuelve {"tool": "file_controller", "args": {...}} o None.
    """
    if not text:
        return None
    raw = text.strip()
    low = raw.lower()
    low_na = _strip_accents(low)

    if not any(_strip_accents(t) in low_na for t in _SEARCH_TRIGGERS):
        return None

    # Si es claramente una búsqueda WEB, no es búsqueda de archivos.
    if any(_strip_accents(w) in low_na for w in _WEB_INDICATORS):
        return None

    # Detectar extensión por palabra clave (la más específica primero).
    ext = ""
    for kw in sorted(_EXT_MAP, key=len, reverse=True):
        if re.search(r"\b" + re.escape(_strip_accents(kw)) + r"\b", low_na):
            ext = _EXT_MAP[kw]
            break

    name = _extract_name(low_na, ext)

    # Detectar ubicación explícita (escritorio, descargas, etc.) -> path.
    path = ""
    for kw in sorted(_LOCATION_MAP, key=len, reverse=True):
        if re.search(r"\b" + re.escape(_strip_accents(kw)) + r"\b", low_na):
            path = _LOCATION_MAP[kw]
            break

    mentions_file = any(w in low_na for w in _FILE_WORDS) or bool(ext) or bool(path)
    # Disparar si menciona archivo/tipo/ubicación, o si quedó un nombre concreto
    # (ej: "buscá memorias de uraba"). Si no hay nada de eso, es muy vago.
    if not (mentions_file or name):
        return None

    args: dict = {"action": "find"}
    if name:
        args["name"] = name
    if ext:
        args["extension"] = ext
    if path:
        args["path"] = path
    return {"tool": "file_controller", "args": args}


def _extract_name(low_na: str, ext: str) -> str:
    """Extrae el posible nombre del archivo quitando disparadores y relleno."""
    text = low_na
    # Quitar disparadores de búsqueda.
    for t in _SEARCH_TRIGGERS:
        text = re.sub(r"\b" + re.escape(_strip_accents(t)) + r"\b", " ", text)
    # Quitar palabras clave de extensión.
    for kw in _EXT_MAP:
        text = re.sub(r"\b" + re.escape(_strip_accents(kw)) + r"\b", " ", text)
    # Tokenizar y quitar relleno.
    tokens = re.findall(r"[a-z0-9_]+", text)
    keep = [tok for tok in tokens if tok not in _FILLER and len(tok) > 1]
    return " ".join(keep).strip()


def detect_intent(text: str) -> dict | None:
    """Punto de entrada: devuelve la primera intención detectada o None.

    Orden de prioridad pensado para evitar colisiones (ej: 'poné el volumen'
    cae en control de sistema, no en reproducir música).
    """
    if not text or not text.strip():
        return None
    low = text.strip().lower()
    low_na = _strip_accents(low)

    # 1) Búsqueda de archivos (verbos buscar/encontrar + archivo/tipo).
    fs = detect_file_search(text)
    if fs is not None:
        return fs

    # 2) Análisis de imágenes (analizá/describí/qué hay en la imagen).
    ia = detect_image_analysis(text, low_na)
    if ia is not None:
        return ia

    # 3) Volumen / brillo.
    sc = detect_system_control(low_na)
    if sc is not None:
        return sc

    # 4) Control de reproducción (pausar/reanudar/siguiente).
    mc = detect_media_control(low_na)
    if mc is not None:
        return mc

    # 5) Cerrar app/ventana.
    cl = detect_close_app(text, low_na)
    if cl is not None:
        return cl

    # 6) Abrir app.
    op = detect_open_app(text, low_na)
    if op is not None:
        return op

    # 7) Reproducir música/video.
    pl = detect_play(text, low_na)
    if pl is not None:
        return pl

    return None
