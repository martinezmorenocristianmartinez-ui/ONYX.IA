"""Seguridad de auto_programmer: validación de nombres de herramienta."""
from actions.auto_programmer import _is_safe_tool_name, auto_programmer


def test_nombre_valido():
    assert _is_safe_tool_name("mi_herramienta")
    assert _is_safe_tool_name("weather_v2")
    assert _is_safe_tool_name("_privado")  # un guion bajo es un identificador válido


def test_dunder_rechazado():
    assert _is_safe_tool_name("__init__") is False
    assert _is_safe_tool_name("__main__") is False


def test_nombres_inseguros_rechazados():
    assert not _is_safe_tool_name("../../main")
    assert not _is_safe_tool_name("..\\..\\main")
    assert not _is_safe_tool_name("foo/bar")
    assert not _is_safe_tool_name("foo.bar")
    assert not _is_safe_tool_name("__init__")
    assert not _is_safe_tool_name("")
    assert not _is_safe_tool_name("MiTool con espacios")


def test_auto_programmer_rechaza_nombre_inseguro_sin_escribir():
    out = auto_programmer({
        "action": "create_tool",
        "tool_name": "../../evil",
        "python_code": "print('hola')",
    })
    assert "seguridad" in out.lower() or "inválido" in out.lower() or "invalido" in out.lower()
