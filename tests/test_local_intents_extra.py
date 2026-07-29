"""Detección de comandos offline extendidos: apps, sistema, música, imágenes."""
from core.local_intents import detect_intent


# ── Imágenes (bug corregido: múltiples extensiones) ──────────────────
def test_buscar_imagen_multiples_extensiones():
    r = detect_intent("buscá la imagen de mi perro")
    assert r is not None
    assert r["tool"] == "file_controller"
    ext = r["args"]["extension"]
    assert ".jpg" in ext and ".png" in ext and ".jpeg" in ext
    assert "perro" in r["args"].get("name", "")


def test_buscar_fotos_en_escritorio():
    r = detect_intent("buscame las fotos del escritorio")
    assert r["args"].get("path") == "desktop"
    assert ".jpg" in r["args"]["extension"]


# ── Abrir / cerrar apps ──────────────────────────────────────────────
def test_abrir_app():
    r = detect_intent("abrí el chrome")
    assert r is not None
    assert r["tool"] == "open_app"
    assert r["args"]["app_name"] == "chrome"


def test_abrir_app_ejecuta():
    r = detect_intent("ejecutá la calculadora")
    assert r["tool"] == "open_app"
    assert "calculadora" in r["args"]["app_name"]


def test_cerrar_app():
    r = detect_intent("cerrá spotify")
    assert r is not None
    assert r["tool"] == "close_app"
    assert "spotify" in r["args"].get("app_name", "")


def test_abrir_no_confunde_con_archivo():
    # "abrí el archivo X" no debe ir a open_app (tiene 'archivo').
    r = detect_intent("abrí el archivo informe")
    assert r is None or r["tool"] != "open_app"


# ── Volumen / brillo ─────────────────────────────────────────────────
def test_subir_volumen():
    r = detect_intent("subí el volumen")
    assert r["tool"] == "computer_settings"
    assert r["args"]["action"] == "volume"
    assert r["args"]["value"] == "subir"


def test_bajar_volumen():
    r = detect_intent("bajá el volumen")
    assert r["args"]["value"] == "bajar"


def test_volumen_a_numero():
    r = detect_intent("poné el volumen al 50")
    assert r["tool"] == "computer_settings"
    assert r["args"]["action"] == "volume"
    assert r["args"]["value"] == "50"


def test_silenciar():
    r = detect_intent("silenciá el sonido")
    assert r["tool"] == "computer_settings"
    assert r["args"].get("description") == "silenciar"


def test_brillo():
    r = detect_intent("subí el brillo")
    assert r["args"]["action"] == "brightness"
    assert r["args"]["value"] == "subir"


# ── Reproducir música / control multimedia ───────────────────────────
def test_reproducir_youtube():
    r = detect_intent("poné bohemian rhapsody en youtube")
    assert r is not None
    assert r["tool"] == "youtube_video"
    assert r["args"]["action"] == "play"
    assert "bohemian" in r["args"]["query"]


def test_pausar():
    r = detect_intent("pausá la música")
    assert r["tool"] == "media_control"
    assert r["args"]["action"] == "pause"


def test_siguiente_cancion():
    r = detect_intent("siguiente canción")
    assert r["tool"] == "media_control"
    assert r["args"]["action"] == "next"


# ── Conversación normal no dispara comandos ──────────────────────────
def test_charla_no_dispara():
    assert detect_intent("hola, cómo andás") is None
    assert detect_intent("contame algo interesante") is None
