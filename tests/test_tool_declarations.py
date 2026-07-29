"""Integridad de las declaraciones de herramientas de ONYX."""
from core.tool_declarations import TOOL_DECLARATIONS


def test_es_lista_no_vacia():
    assert isinstance(TOOL_DECLARATIONS, list)
    assert len(TOOL_DECLARATIONS) > 0


def test_cada_tool_tiene_nombre():
    for t in TOOL_DECLARATIONS:
        assert isinstance(t, dict), f"Tool no es dict: {t!r}"
        assert t.get("name"), f"Tool sin nombre: {t!r}"
        assert isinstance(t["name"], str)


def test_no_hay_nombres_duplicados():
    names = [t["name"] for t in TOOL_DECLARATIONS]
    duplicados = {n for n in names if names.count(n) > 1}
    assert not duplicados, f"Nombres de herramientas duplicados: {duplicados}"


def test_parameters_bien_formados():
    for t in TOOL_DECLARATIONS:
        params = t.get("parameters")
        if params is None:
            continue  # algunas tools no declaran parámetros
        assert isinstance(params, dict), f"{t['name']}: parameters no es dict"
        if "properties" in params:
            assert isinstance(params["properties"], dict)
        if "required" in params:
            assert isinstance(params["required"], list)
