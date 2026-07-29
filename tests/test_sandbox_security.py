"""Seguridad del sandbox: bloqueo de escapes y ejecución de código legítimo."""
import sys
from pathlib import Path

# El ejecutor del sandbox vive en actions/ y se importa por ruta directa.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "actions"))
import _sandbox_exec as sb  # noqa: E402


def test_bloquea_escape_subclasses():
    r = sb.execute_code("x = ().__class__.__bases__[0].__subclasses__()")
    assert r["success"] is False
    assert "SandboxViolation" in r["stderr"]


def test_bloquea_import_peligroso():
    r = sb.execute_code("import os\nos.system('echo hi')")
    assert r["success"] is False


def test_bloquea_eval():
    r = sb.execute_code("eval('1+1')")
    assert r["success"] is False


def test_bloquea_getattr_dunder():
    r = sb.execute_code("o = object\nprint(getattr(o, '__bases__'))")
    assert r["success"] is False


def test_permite_codigo_legitimo():
    r = sb.execute_code("import math\nprint(math.sqrt(16))\nprint(sum([1, 2, 3]))")
    assert r["success"] is True
    assert "4.0" in r["stdout"]
    assert "6" in r["stdout"]


def test_permite_modulos_whitelist():
    r = sb.execute_code("import json\nprint(json.dumps({'a': 1}))")
    assert r["success"] is True
    assert '"a": 1' in r["stdout"]
