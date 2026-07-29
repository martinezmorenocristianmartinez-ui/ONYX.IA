"""Detección de intención de análisis de imágenes."""
from core.local_intents import detect_intent


def test_analizar_imagen_con_nombre():
    r = detect_intent("analizá la imagen vacaciones")
    assert r is not None
    assert r["tool"] == "local_image_analysis"
    assert "vacaciones" in r["args"].get("name", "")


def test_describir_foto():
    r = detect_intent("describí la foto de mi perro")
    assert r["tool"] == "local_image_analysis"
    assert "perro" in r["args"].get("name", "")


def test_que_hay_en_la_imagen():
    r = detect_intent("qué hay en la imagen logo")
    assert r["tool"] == "local_image_analysis"
    assert "logo" in r["args"].get("name", "")


def test_analizar_imagen_sin_nombre():
    r = detect_intent("analizá esta imagen")
    assert r is not None
    assert r["tool"] == "local_image_analysis"
    # sin nombre -> se usará el archivo actual de la UI
    assert not r["args"].get("name")


def test_analizar_por_ruta_extension():
    r = detect_intent("analizá foto_perro.jpg")
    assert r["tool"] == "local_image_analysis"
    assert ".jpg" in r["args"].get("name", "")


def test_buscar_imagen_no_es_analisis():
    # 'buscá la imagen X' debe seguir siendo BÚSQUEDA, no análisis.
    r = detect_intent("buscá la imagen vacaciones")
    assert r["tool"] == "file_controller"


def test_pregunta_sin_imagen_no_dispara():
    assert detect_intent("qué hay para comer") is None
