"""Integridad del registro de despacho de herramientas y su acople con main.py.

Verifica, SIN ejecutar main.py (que arrastra PyQt6/API), que cada función
referenciada en SIMPLE_TOOL_SPECS exista realmente como nombre global en
main.py. Si no existiera, el handler genérico devolvería "no disponible" y la
herramienta dejaría de funcionar silenciosamente.
"""
import ast
from pathlib import Path

from core.tool_registry import SIMPLE_TOOL_SPECS, build_executor_kwargs
from core.tool_declarations import TOOL_DECLARATIONS

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


def _toplevel_bound_names(source: str) -> set[str]:
    """Nombres ligados a nivel de módulo: imports, asignaciones y defs."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(node, (ast.Try,)):
            # imports envueltos en try/except (patrón común en main.py)
            for sub in ast.walk(node):
                if isinstance(sub, ast.ImportFrom):
                    for a in sub.names:
                        names.add(a.asname or a.name)
                elif isinstance(sub, ast.Import):
                    for a in sub.names:
                        names.add((a.asname or a.name).split(".")[0])
                elif isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if isinstance(tgt, ast.Name):
                            names.add(tgt.id)
    return names


def test_specs_bien_formadas():
    validas = {"func", "default", "raw", "response", "speak", "session_memory"}
    for name, spec in SIMPLE_TOOL_SPECS.items():
        assert "func" in spec, f"{name} sin 'func'"
        assert isinstance(spec["func"], str)
        assert set(spec).issubset(validas), f"{name} tiene claves inválidas: {set(spec) - validas}"


def test_todas_las_funcs_existen_en_main():
    bound = _toplevel_bound_names(MAIN.read_text(encoding="utf-8"))
    faltantes = {spec["func"] for spec in SIMPLE_TOOL_SPECS.values()} - bound
    assert not faltantes, f"Funciones del registro ausentes en main.py: {faltantes}"


def test_tools_del_registro_estan_declaradas():
    declaradas = {t["name"] for t in TOOL_DECLARATIONS}
    # Handlers internos que existen en el dispatcher pero no se declaran como
    # function-calling (situación preexistente al refactor): alias y accesibilidad.
    INTERNOS = {"screen_vision", "screen_reader"}
    sin_declarar = set(SIMPLE_TOOL_SPECS) - declaradas - INTERNOS
    assert not sin_declarar, f"Tools en el registro sin declaración: {sin_declarar}"


def test_build_executor_kwargs():
    spec = {"func": "x", "response": True, "speak": True}
    kw = build_executor_kwargs(spec, {"a": 1}, ui="UI", speak_fn="SPEAK")
    assert kw == {"parameters": {"a": 1}, "player": "UI", "response": None, "speak": "SPEAK"}

    spec2 = {"func": "y"}
    kw2 = build_executor_kwargs(spec2, {}, ui="UI", speak_fn="SPEAK")
    assert kw2 == {"parameters": {}, "player": "UI"}
