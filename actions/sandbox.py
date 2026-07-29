"""
sandbox.py — Safe code execution sandbox for ONYX.
Runs Python/JS in a restricted subprocess with timeout.
No file I/O, no network, no dangerous imports.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_python(code: str, timeout: int = 30) -> dict:
    """Run Python code in restricted sandbox subprocess."""
    exec_path = Path(__file__).resolve().parent / "_sandbox_exec.py"
    if not exec_path.exists():
        return {"success": False, "stdout": "", "stderr": "Sandbox executor not found."}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, str(exec_path), tmp_path],
            capture_output=True, text=True, timeout=timeout,
            env={},  # no environment variables
        )
        if proc.stdout:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                return {"success": False, "stdout": proc.stdout[:2000], "stderr": proc.stderr[:2000]}
        return {"success": False, "stdout": "", "stderr": proc.stderr[:2000] or "No output from sandbox."}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Execution timed out after {timeout}s."}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)[:2000]}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _run_javascript(code: str, timeout: int = 30) -> dict:
    """Run JavaScript code via Node.js if available."""
    try:
        proc = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            return {"success": False, "stdout": "", "stderr": "Node.js no está instalado."}
    except Exception:
        return {"success": False, "stdout": "", "stderr": "Node.js no está disponible."}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            ["node", tmp_path],
            capture_output=True, text=True, timeout=timeout,
        )
        stdout = proc.stdout[:5000] if proc.stdout else ""
        stderr = proc.stderr[:2000] if proc.stderr else ""
        return {
            "success": proc.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Execution timed out after {timeout}s."}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)[:2000]}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def sandbox(parameters: dict, player=None) -> str:
    """Execute code in a restricted sandbox. Supports Python and JavaScript."""
    action = (parameters.get("action", "") or "").strip().lower()
    code = parameters.get("code", parameters.get("value", ""))
    timeout = int(parameters.get("timeout", 30))

    if not code:
        return "No se proporcionó código para ejecutar."

    code = code.strip()

    if action in ("python", "py", ""):
        result = _run_python(code, timeout)
    elif action in ("javascript", "js", "node"):
        result = _run_javascript(code, timeout)
    else:
        return f"Lenguaje '{action}' no soportado. Usa 'python' o 'javascript'."

    lines = []
    if result["stdout"]:
        lines.append("[STDOUT]")
        lines.append(result["stdout"][:5000])
    if result["stderr"]:
        lines.append("[STDERR]")
        lines.append(result["stderr"][:2000])
    if not lines:
        if result["success"]:
            lines.append("[OK] Código ejecutado sin salida.")
        else:
            lines.append("[ERROR] Error desconocido.")

    status = "✅" if result["success"] else "❌"
    return f"{status} Sandbox\n" + "\n".join(lines)
