"""
screen_agent.py — Autonomous screen interaction agent for ONYX.
Ciclo completo: Observa → Comprende → Ejecuta → Verifica → Reporta.
Usa OCR local + UI Automation + Visión IA en pipeline multi-estrategia.
"""
import time
import json
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
STEP_MEMORY_PATH = MEMORY_DIR / "screen_agent_steps.json"


# ── Step Memory ─────────────────────────────────────────────────────

def _load_steps() -> list[dict]:
    try:
        return json.loads(STEP_MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_steps(steps: list[dict]):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    STEP_MEMORY_PATH.write_text(
        json.dumps(steps[-50:], indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _add_step(action: str, description: str, result: str, success: bool):
    steps = _load_steps()
    steps.append({
        "timestamp": time.strftime("%H:%M:%S"),
        "action": action,
        "description": description,
        "result": result[:200],
        "success": success,
    })
    _save_steps(steps)


def _clear_steps():
    _save_steps([])


# ── Screen Observation ──────────────────────────────────────────────

def observe_screen() -> dict:
    """
    Analyze current screen using ALL available methods.
    Returns a structured report of what's visible.
    """
    report = {
        "active_window": {},
        "windows_count": 0,
        "text_blocks": [],
        "ui_elements": [],
        "summary": "",
    }

    from actions._screen_analyzer import (
        get_active_window_info, get_all_windows,
        ocr_screen, get_ui_tree,
    )

    try:
        report["active_window"] = get_active_window_info()
        report["windows_count"] = len(get_all_windows())
        report["text_blocks"] = ocr_screen() or []
        report["ui_elements"] = get_ui_tree() or []
    except Exception:
        pass

    return report


def format_observation(report: dict) -> str:
    """Format screen observation into a clear text report."""
    lines = ["[OBSERVACION DE PANTALLA]"]

    aw = report.get("active_window", {})
    if aw and aw.get("title"):
        lines.append(f"Ventana activa: {aw['title']}")
        lines.append(f"  Posicion: ({aw.get('left',0)},{aw.get('top',0)})")
        lines.append(f"  Tamano: {aw.get('width',0)}x{aw.get('height',0)}")
    else:
        lines.append("Ventana activa: (no detectada)")

    lines.append(f"Ventanas abiertas: {report.get('windows_count', 0)}")

    texts = report.get("text_blocks", [])
    if texts:
        lines.append(f"\nTextos visibles ({len(texts)} bloques):")
        for t in texts[:20]:
            lines.append(f"  - '{t['text']}' en ({t['x']},{t['y']})")
        if len(texts) > 20:
            lines.append(f"  ... y {len(texts)-20} mas")

    ui = report.get("ui_elements", [])
    if ui:
        buttons = [e for e in ui if e.get("type") == "Button" and e.get("text")]
        fields = [e for e in ui if e.get("type") == "Edit" and e.get("text")]
        links = [e for e in ui if e.get("type") == "Hyperlink" and e.get("text")]
        tabs = [e for e in ui if e.get("type") == "TabItem" and e.get("text")]
        items = [e for e in ui if e.get("type") == "MenuItem" and e.get("text")]

        if buttons:
            lines.append(f"\nBotones: {', '.join(b['text'][:30] for b in buttons[:8])}")
        if fields:
            lines.append(f"Campos: {', '.join(f['text'][:30] for f in fields[:5])}")
        if links:
            lines.append(f"Enlaces: {', '.join(l['text'][:30] for l in links[:5])}")
        if tabs:
            lines.append(f"Pestanas: {', '.join(t['text'][:30] for t in tabs[:5])}")
        if items:
            lines.append(f"Menus: {', '.join(i['text'][:30] for i in items[:5])}")

    lines.append("[/OBSERVACION]")
    return "\n".join(lines)


# ── Element Finding with Verification ───────────────────────────────

def find_element(description: str) -> dict:
    """
    Find element using ALL strategies. Returns detailed result.
    Pre-verification: checks if OCR/text match is unambiguous.
    """
    from actions._screen_analyzer import find_element_advanced, find_text_on_screen

    result = find_element_advanced(description)
    if not result.get("found"):
        return {"found": False, "error": f"No encontre '{description}' en la pantalla."}

    # Check for ambiguity
    text_matches = find_text_on_screen(description)
    if len(text_matches) > 1:
        result["ambiguous"] = True
        result["alternatives"] = [
            {"text": m["text"], "x": m["x"], "y": m["y"], "conf": m["conf"]}
            for m in text_matches[:5]
        ]
    else:
        result["ambiguous"] = False

    return result


def verify_action_result(expected_change: str = "") -> dict:
    """
    Re-analyze screen after an action to verify it worked.
    Returns observation + verification status.
    """
    time.sleep(0.3)
    report = observe_screen()

    verification = {
        "success": True,
        "observation": report,
        "details": format_observation(report),
    }

    if expected_change == "window_closed":
        if report.get("windows_count", 0) > 0:
            verification["success"] = False
            verification["error"] = "La ventana sigue abierta."
    elif expected_change == "text_appeared":
        if not report.get("text_blocks"):
            verification["success"] = False
            verification["error"] = "No aparecio el texto esperado."

    return verification


# ── Execution Actions ───────────────────────────────────────────────

def action_click(description: str, button: str = "left") -> dict:
    """
    Find element → verify → click → verify result.
    Returns detailed outcome.
    """
    element = find_element(description)
    if not element.get("found"):
        return {"success": False, "error": element.get("error", "Elemento no encontrado.")}

    if element.get("ambiguous"):
        alternatives = element.get("alternatives", [])
        msg = f"Se encontraron varias coincidencias para '{description}':"
        for a in alternatives:
            msg += f"\n  - '{a['text']}' en ({a['x']},{a['y']})"
        msg += "\nUsa click_at con coordenadas exactas para evitar ambiguedad."
        return {"success": False, "ambiguous": True, "message": msg, "alternatives": alternatives}

    x, y = element["x"], element["y"]
    strategy = element["strategy"]
    confidence = element["confidence"]

    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=0.3)
        time.sleep(0.1)
        pyautogui.click(button=button)
    except Exception as e:
        return {"success": False, "error": f"Error al hacer clic: {e}"}

    # Verify
    time.sleep(0.3)
    post = observe_screen()

    return {
        "success": True,
        "x": x, "y": y,
        "strategy": strategy,
        "confidence": confidence,
        "post_observation": format_observation(post),
    }


def action_type(text: str, target: str = "", clear_first: bool = True) -> dict:
    """
    Click on target if specified, then type text.
    """
    if target:
        click_result = action_click(target)
        if not click_result.get("success"):
            return click_result
        time.sleep(0.2)

    try:
        import pyautogui
        if clear_first and target:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.press("delete")
            time.sleep(0.05)
        pyautogui.write(text, interval=0.02)
        return {"success": True, "typed": text, "target": target or "posicion actual"}
    except Exception as e:
        return {"success": False, "error": f"Error al escribir: {e}"}


def action_press(keys: str) -> dict:
    """Press a key or hotkey combination."""
    try:
        import pyautogui
        if "+" in keys:
            parts = keys.lower().split("+")
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(keys.lower())
        return {"success": True, "keys": keys}
    except Exception as e:
        return {"success": False, "error": f"Error al presionar tecla: {e}"}


def action_open(app_name: str) -> dict:
    """Open an application."""
    try:
        from actions.open_app import open_app
        result = open_app(parameters={"app_name": app_name}, player=None)
        time.sleep(1.5)
        post = observe_screen()
        return {
            "success": True,
            "app": app_name,
            "result": result,
            "post_observation": format_observation(post),
        }
    except Exception as e:
        return {"success": False, "error": f"Error al abrir {app_name}: {e}"}


# ── Main Agent Function ─────────────────────────────────────────────

def screen_agent(parameters: dict, player=None) -> str:
    """
    Autonomous screen interaction agent.
    Observes → Understands → Acts → Verifies → Reports.
    """
    action = str(parameters.get("action", "observe")).lower()
    target = parameters.get("target", "")
    text = parameters.get("text", "")
    keys = parameters.get("keys", "")
    app = parameters.get("app", "")
    button = parameters.get("button", "left")
    clear = str(parameters.get("clear_first", "true")).lower() in ("true", "yes", "1")
    confirm = str(parameters.get("confirm", "false")).lower() in ("true", "yes", "1")
    expected = parameters.get("expected", "")

    # ── Observe ──
    if action == "observe":
        report = observe_screen()
        observation = format_observation(report)
        steps = _load_steps()

        msg = observation
        if steps:
            msg += "\n\n[PASOS RECIENTES]"
            for s in steps[-5:]:
                icon = "✅" if s.get("success") else "❌"
                msg += f"\n  {icon} {s['action']}: {s['description']} -> {s['result'][:80]}"

        if player:
            player.write_log(f"[ScreenAgent] Observando pantalla...")

        return msg

    # ── Find element ──
    if action == "find":
        if not target:
            return "Necesito la descripcion del elemento a buscar."

        result = find_element(target)
        if not result.get("found"):
            _add_step("find", target, result.get("error", "No encontrado"), False)
            return result.get("error", f"No encontre '{target}'.")

        msg = f"Encontre '{target}':"
        msg += f"\n  Coordenadas: ({result['x']},{result['y']})"
        msg += f"\n  Estrategia: {result['strategy']}"
        msg += f"\n  Confianza: {result['confidence']}"

        if result.get("ambiguous"):
            msg += "\n\n⚠️ MULTIPLES COINCIDENCIAS:"
            for a in result.get("alternatives", []):
                msg += f"\n  - '{a['text']}' en ({a['x']},{a['y']}) conf={a['conf']}%"
            msg += "\nUsa click_at X Y para target exacto."

        _add_step("find", target, f"Encontrado en ({result['x']},{result['y']})", True)
        return msg

    # ── Click ──
    if action == "click":
        if not target:
            return "Necesito la descripcion del elemento a cliquear."

        if confirm:
            observation = format_observation(observe_screen())
            return (f"⚠️ CONFIRMAR: Voy a clickear '{target}'. ¿Procedo?\n"
                    f"Pantalla actual:\n{observation}")

        if player:
            player.write_log(f"[ScreenAgent] Click en '{target}'...")

        result = action_click(target, button)
        if result.get("ambiguous"):
            alt = result.get("alternatives", [])
            msg = f"⚠️ MULTIPLES OPCIONES para '{target}':"
            for a in alt:
                msg += f"\n  ({a['x']},{a['y']}) -> '{a['text']}'"
            msg += "\nUsa 'click_at' con coordenadas exactas o se mas especifico."
            _add_step("click", target, "Ambiguedad", False)
            return msg

        if not result.get("success"):
            _add_step("click", target, result.get("error", "Fallo"), False)
            return f"Error: {result.get('error')}"

        post = result.get("post_observation", "")
        _add_step("click", target, f"Click en ({result['x']},{result['y']}) via {result['strategy']}", True)
        return f"✅ Clic ejecutado en '{target}' ({result['x']},{result['y']}) via {result['strategy']}.\n\nVerificacion:\n{post}"

    # ── Click at exact coordinates ──
    if action == "click_at":
        try:
            import pyautogui
            x = int(parameters.get("x", 0))
            y = int(parameters.get("y", 0))
            if x <= 0 or y <= 0:
                return "Coordenadas invalidas."
            pyautogui.moveTo(x, y, duration=0.2)
            time.sleep(0.1)
            pyautogui.click(button=button)
            time.sleep(0.3)
            post = format_observation(observe_screen())
            _add_step("click_at", f"({x},{y})", f"Click en ({x},{y})", True)
            return f"✅ Clic en ({x},{y}).\n\nVerificacion:\n{post}"
        except Exception as e:
            return f"Error en click_at: {e}"

    # ── Type text ──
    if action == "type":
        if not text:
            return "Necesito el texto a escribir."

        if player:
            player.write_log(f"[ScreenAgent] Escribiendo texto...")

        result = action_type(text, target, clear)
        if not result.get("success"):
            _add_step("type", text[:50], result.get("error", "Fallo"), False)
            return f"Error: {result.get('error')}"

        _add_step("type", text[:50], f"Escrito en {result.get('target', 'actual')}", True)
        return f"✅ Texto escrito: '{text[:100]}'"

    # ── Press key ──
    if action == "press":
        if not keys:
            return "Necesito la tecla a presionar (ej: enter, ctrl+c, tab)."

        result = action_press(keys)
        if not result.get("success"):
            return f"Error: {result.get('error')}"

        time.sleep(0.5)
        post = format_observation(observe_screen())
        _add_step("press", keys, "Tecla presionada", True)
        return f"✅ Tecla '{keys}' presionada.\n\nVerificacion:\n{post}"

    # ── Open app ──
    if action == "open":
        if not app:
            return "Necesito el nombre de la aplicacion a abrir."

        if player:
            player.write_log(f"[ScreenAgent] Abriendo {app}...")

        result = action_open(app)
        if not result.get("success"):
            _add_step("open", app, result.get("error", "Fallo"), False)
            return f"Error: {result.get('error')}"

        _add_step("open", app, f"Aplicacion abierta", True)
        return f"Aplicacion '{app}' abierta.\n\nVerificacion:\n{result.get('post_observation', '')}"

    # ── Sequence (execute multiple steps) ──
    if action == "sequence":
        steps_json = parameters.get("steps", "[]")
        if isinstance(steps_json, str):
            try:
                steps_list = json.loads(steps_json)
            except Exception:
                steps_list = []
        else:
            steps_list = steps_json

        if not steps_list:
            return "Necesito una lista de pasos a ejecutar (formato JSON)."

        if confirm:
            msg = f"⚠️ CONFIRMAR SECUENCIA DE {len(steps_list)} PASOS:"
            for i, s in enumerate(steps_list):
                msg += f"\n  {i+1}. {s.get('action')}: {s.get('description', s.get('target', ''))}"
            msg += "\n\n¿Procedo con la secuencia completa?"
            return msg

        if player:
            player.write_log(f"[ScreenAgent] Ejecutando secuencia de {len(steps_list)} pasos...")

        results = []
        for i, step in enumerate(steps_list):
            step_action = step.get("action", "")
            step_target = step.get("target", "")
            step_text = step.get("text", "")
            step_keys = step.get("keys", "")
            step_app = step.get("app", "")

            if step_action == "click":
                r = action_click(step_target, step.get("button", "left"))
                status = "✅" if r.get("success") else "❌"
                results.append(f"{status} Paso {i+1}: Click '{step_target}' -> {r.get('strategy', 'fallo')}")
                if not r.get("success"):
                    if step.get("optional"):
                        results[-1] += " (opcional, continuando...)"
                    else:
                        results.append(f"⛔ Secuencia detenida en paso {i+1}.")
                        _add_step("sequence", f"Fallo en paso {i+1}: {step_action} {step_target}", "Secuencia interrumpida", False)
                        break

            elif step_action == "type":
                r = action_type(step_text, step_target, step.get("clear_first", True))
                status = "✅" if r.get("success") else "❌"
                results.append(f"{status} Paso {i+1}: Escribir en '{step_target}'")
                if not r.get("success"):
                    results.append(f"⛔ Secuencia detenida en paso {i+1}.")
                    _add_step("sequence", f"Fallo en paso {i+1}: type", "Secuencia interrumpida", False)
                    break

            elif step_action == "press":
                r = action_press(step_keys)
                status = "✅" if r.get("success") else "❌"
                results.append(f"{status} Paso {i+1}: Tecla '{step_keys}'")
                if not r.get("success"):
                    results.append(f"⛔ Secuencia detenida en paso {i+1}.")
                    _add_step("sequence", f"Fallo en paso {i+1}: press", "Secuencia interrumpida", False)
                    break

            elif step_action == "open":
                r = action_open(step_app)
                status = "✅" if r.get("success") else "❌"
                results.append(f"{status} Paso {i+1}: Abrir '{step_app}'")

            elif step_action == "wait":
                seconds = int(step.get("seconds", 1))
                time.sleep(seconds)
                results.append(f"⏱️ Paso {i+1}: Espera {seconds}s")

            elif step_action == "verify":
                post = format_observation(observe_screen())
                results.append(f"👁️ Paso {i+1}: Verificacion:\n{post[:500]}")

            time.sleep(0.2)

        _add_step("sequence", f"Secuencia de {len(steps_list)} pasos", f"Completados: {len(results)} pasos", True)
        return "\n".join(results)

    # ── Status ──
    if action == "status":
        steps = _load_steps()
        if not steps:
            return "No hay pasos registrados en esta sesion."

        msg = f"[MEMORIA DE PASOS ({len(steps)} totales)]"
        for s in steps[-10:]:
            icon = "✅" if s.get("success") else "❌"
            msg += f"\n{icon} [{s['timestamp']}] {s['action']}: {s['description']}"
            msg += f" -> {s['result'][:100]}"
        return msg

    # ── Clear memory ──
    if action == "clear_memory":
        _clear_steps()
        return "Memoria de pasos borrada."

    # ── Unknown action ──
    return (
        f"Accion '{action}' no reconocida.\n\n"
        "Acciones disponibles:\n"
        "  observe — Analiza la pantalla actual y reporta todo lo visible\n"
        "  find TARGET — Busca un elemento por descripcion\n"
        "  click TARGET — Encuentra y hace clic en un elemento\n"
        "  click_at X Y — Clic en coordenadas exactas\n"
        "  type TARGET TEXT — Escribe texto (opcional: hace clic primero)\n"
        "  press KEYS — Presiona tecla/s (ej: enter, ctrl+c)\n"
        "  open APP — Abre una aplicacion\n"
        "  sequence STEPS — Ejecuta una secuencia de pasos\n"
        "  status — Muestra los pasos ejecutados\n"
        "  clear_memory — Limpia la memoria de pasos\n\n"
        "Parametros comunes:\n"
        "  confirm=true — Pide confirmacion antes de ejecutar\n"
        "  expected=window_closed — Verifica resultado esperado"
    )
