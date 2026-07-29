"""Seguridad de self_edit: contención de rutas dentro del proyecto ONYX."""
import pytest

from actions.self_edit import _resolve_path, PathEscapeError, ONYX_ROOT, self_edit


def test_ruta_relativa_valida_resuelve_dentro():
    p = _resolve_path("main.py")
    assert str(p).startswith(str(ONYX_ROOT.resolve()))


def test_ruta_absoluta_windows_es_rechazada():
    with pytest.raises(PathEscapeError):
        _resolve_path(r"C:\Windows\System32\drivers\etc\hosts")


def test_traversal_con_puntos_es_rechazado():
    with pytest.raises(PathEscapeError):
        _resolve_path("../../../algun_archivo.txt")


def test_subcarpeta_valida_es_permitida():
    p = _resolve_path("core/prompt.txt")
    assert str(p).startswith(str(ONYX_ROOT.resolve()))


def test_self_edit_devuelve_error_sin_crashear_ante_ruta_absoluta():
    # No debe lanzar excepción: el error de seguridad se devuelve como texto.
    out = self_edit({"action": "read_file", "file": r"C:\Windows\win.ini"})
    assert isinstance(out, str)
    assert "Error" in out or "denegado" in out.lower() or "permitida" in out.lower()
