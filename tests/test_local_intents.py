"""Detección determinística de comandos en modo local."""
from core.local_intents import detect_intent, detect_file_search


def test_buscar_pdf_por_nombre():
    r = detect_intent("Buscá el archivo de capacitacion en PDF")
    assert r is not None
    assert r["tool"] == "file_controller"
    assert r["args"]["action"] == "find"
    assert r["args"]["extension"] == ".pdf"
    assert "capacitacion" in r["args"].get("name", "")


def test_buscar_word():
    r = detect_intent("encontrá el documento de word llamado uraba")
    assert r is not None
    assert r["args"]["extension"] == ".docx"
    assert "uraba" in r["args"].get("name", "")


def test_buscar_excel():
    r = detect_intent("busca una hoja de cálculo de ventas")
    assert r is not None
    assert r["args"]["extension"] == ".xlsx"
    assert "ventas" in r["args"].get("name", "")


def test_buscar_archivo_sin_extension():
    r = detect_intent("buscá el archivo presupuesto")
    assert r is not None
    assert r["args"]["action"] == "find"
    assert "presupuesto" in r["args"].get("name", "")


def test_buscar_solo_por_tipo_sin_nombre():
    r = detect_intent("buscame los pdf")
    assert r is not None
    assert r["args"]["extension"] == ".pdf"


def test_ubicacion_va_a_path_no_a_nombre():
    r = detect_intent("buscame los pdf del escritorio")
    assert r is not None
    assert r["args"]["extension"] == ".pdf"
    assert r["args"].get("path") == "desktop"
    # 'escritorio' no debe quedar como nombre de archivo
    assert "escritorio" not in r["args"].get("name", "")


def test_no_es_busqueda():
    assert detect_intent("hola cómo estás") is None
    assert detect_intent("qué hora es") is None
    assert detect_intent("contame un chiste") is None


def test_buscar_sin_mencion_archivo_ni_tipo_no_dispara():
    # "buscá información sobre python" no es búsqueda de archivos.
    assert detect_file_search("buscá información sobre python") is None


def test_nombre_no_incluye_relleno():
    r = detect_intent("buscá el archivo llamado informe anual en pdf")
    assert r is not None
    name = r["args"].get("name", "")
    assert "informe" in name and "anual" in name
    assert "archivo" not in name
    assert "llamado" not in name
    assert "pdf" not in name


# ── Robustez de búsqueda de documentos (bugs reportados) ─────────────
def test_plural_archivos_no_contamina_nombre():
    r = detect_intent("busca los archivos de memorias")
    assert r["args"]["name"] == "memorias"


def test_documentos_no_restringe_a_carpeta():
    # "los documentos de X" debe buscar amplio, no solo en la carpeta Documentos.
    r = detect_intent("busca los documentos de uraba")
    assert r["args"].get("path") is None
    assert r["args"]["name"] == "uraba"


def test_nombre_multipalabra():
    r = detect_intent("buscá memorias de uraba")
    assert r is not None
    assert "memorias" in r["args"]["name"] and "uraba" in r["args"]["name"]
    assert "de" not in r["args"]["name"].split()


def test_busqueda_sin_palabra_archivo():
    # Antes devolvía None; ahora dispara búsqueda de archivos.
    r = detect_intent("encontrá el plan de capacitacion")
    assert r is not None
    assert r["tool"] == "file_controller"
    assert "plan" in r["args"]["name"] and "capacitacion" in r["args"]["name"]


def test_busqueda_web_no_es_archivo():
    assert detect_intent("buscá información sobre python") is None
    assert detect_intent("buscá en internet el clima") is None
    assert detect_intent("buscá qué es la fotosíntesis") is None
