"""
_sandbox_exec.py — Restricted Python execution environment.
Runs as a subprocess. Only safe modules are allowed.
Usage: python _sandbox_exec.py <temp_file_with_code>
"""
import sys
import json
import ast
import traceback

# ── Patrones de escape prohibidos (análisis estático AST) ────────
# El enfoque de "builtins restringidos" por sí solo NO es seguro: se puede
# escapar con ().__class__.__bases__[0].__subclasses__() para alcanzar os,
# subprocess, etc. Bloqueamos esos vectores ANTES de ejecutar.
_FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "open", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "memoryview", "classmethod", "staticmethod", "super", "property",
    "__import__",
}

# Atributos dunder usados para escapar del sandbox.
_FORBIDDEN_ATTRS = {
    "__class__", "__bases__", "__base__", "__subclasses__", "__mro__",
    "__globals__", "__builtins__", "__import__", "__code__", "__dict__",
    "__getattribute__", "__getattr__", "__setattr__", "__delattr__",
    "__reduce__", "__reduce_ex__", "__init_subclass__", "__subclasshook__",
    "__closure__", "__func__", "__self__", "__loader__", "__spec__",
    "__builtin__", "__module__", "__qualname__",
}


class SandboxViolation(Exception):
    """El código intentó usar un patrón prohibido en el sandbox."""


def _scan_ast(code: str) -> None:
    """Analiza el AST y rechaza patrones peligrosos antes de ejecutar.

    Lanza SandboxViolation si encuentra acceso a dunders de escape, nombres
    prohibidos (eval/exec/open/getattr...) o sentencias import directas.
    """
    tree = ast.parse(code, "<sandbox>", "exec")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_ATTRS:
                raise SandboxViolation(f"Acceso prohibido al atributo '{node.attr}'.")
        elif isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES:
                raise SandboxViolation(f"Uso prohibido de '{node.id}'.")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # Los imports se validan también contra el whitelist en runtime,
            # pero rechazamos aquí cualquier nombre fuera de la lista segura.
            mods = (
                [a.name.split(".")[0] for a in node.names]
                if isinstance(node, ast.Import)
                else [(node.module or "").split(".")[0]]
            )
            for m in mods:
                if m and m not in _ALLOWED_MODULES:
                    raise SandboxViolation(f"Import no permitido: '{m}'.")

# ── Safe modules whitelist ───────────────────────────────────────
_ALLOWED_MODULES = {
    "math", "json", "random", "datetime", "collections",
    "itertools", "statistics", "typing", "re", "string",
    "decimal", "fractions", "time", "textwrap", "uuid",
    "dataclasses", "enum", "copy", "pprint",
}

# ── Restricted builtins ─────────────────────────────────────────
_ALLOWED_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray",
    "bytes", "chr", "complex", "dict", "dir", "divmod",
    "enumerate", "filter", "float", "format", "frozenset",
    "hash", "hex", "id", "int", "isinstance", "issubclass",
    "iter", "len", "list", "map", "max", "min", "next",
    "object", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "type", "vars", "zip",
    "True", "False", "None", "__import__",
}

_RESTRICTED_BUILTINS = {}
for _name in _ALLOWED_BUILTINS:
    _RESTRICTED_BUILTINS[_name] = __builtins__[_name] if isinstance(__builtins__, dict) else getattr(__builtins__, _name)


def _safe_import(name, *args, **kwargs):
    if name not in _ALLOWED_MODULES:
        raise ImportError(f"Module '{name}' is not allowed in sandbox.")
    return __import__(name, *args, **kwargs)


_RESTRICTED_BUILTINS["__import__"] = _safe_import


def execute_code(code: str) -> dict:
    """Execute code in restricted environment. Returns result dict."""
    stdout_lines = []
    stderr_lines = []

    def _print(*args, **kwargs):
        kwargs.pop("file", None)
        kwargs.pop("flush", None)
        stdout_lines.append(" ".join(str(a) for a in args))

    _RESTRICTED_BUILTINS["print"] = _print

    restricted_globals = {
        "__builtins__": _RESTRICTED_BUILTINS,
        "__name__": "__sandbox__",
    }

    try:
        _scan_ast(code)
        compiled = compile(code, "<sandbox>", "exec")
        exec(compiled, restricted_globals)
        return {"success": True, "stdout": "\n".join(stdout_lines), "stderr": "\n".join(stderr_lines)}
    except SandboxViolation as sv:
        stderr_lines.append(f"SandboxViolation: {sv}")
        return {"success": False, "stdout": "\n".join(stdout_lines), "stderr": "\n".join(stderr_lines)}
    except Exception:
        stderr_lines.append(traceback.format_exc())
        return {"success": False, "stdout": "\n".join(stdout_lines), "stderr": "\n".join(stderr_lines)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "stdout": "", "stderr": "No code file provided."}))
        sys.exit(1)
    try:
        code = open(sys.argv[1], "r", encoding="utf-8").read()
    except Exception as e:
        print(json.dumps({"success": False, "stdout": "", "stderr": f"Error reading code file: {e}"}))
        sys.exit(1)
    result = execute_code(code)
    print(json.dumps(result))
