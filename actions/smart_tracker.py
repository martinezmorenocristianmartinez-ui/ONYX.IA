import time
from actions._screen_analyzer import (
    find_element_advanced, analyze_screen_structure, format_structure_report,
    ocr_screen, find_text_on_screen, get_ui_tree, find_in_ui_tree,
    get_active_window_info, describe_screen_advanced,
)
from actions._vision import vision_find, call_vision, get_api_key


def smart_tracker(parameters: dict, response=None, player=None) -> str:
    """
    RASTREADOR INTELIGENTE DE PANTALLA con múltiples estrategias.
    Usa OCR local + UI Automation + Visión IA para encontrar elementos.
    """
    try:
        import pyautogui
    except ImportError:
        return "Error: Falta pyautogui."

    action = str(parameters.get("action", "find") or "find").lower()
    target = parameters.get("target") or parameters.get("element") or parameters.get("description") or ""
    click = str(parameters.get("click", "false") or "false").lower() in ("true", "yes", "si", "1")

    # ── Structure scan ──
    if action == "scan":
        try:
            structure = analyze_screen_structure()
            return format_structure_report(structure)
        except Exception as e:
            return f"Error al escanear pantalla: {e}"

    # ── Full screen description ──
    if action == "describe":
        try:
            return describe_screen_advanced()
        except Exception as e:
            return f"Error al describir pantalla: {e}"

    # ── OCR text extraction ──
    if action == "ocr":
        try:
            texts = ocr_screen()
            if not texts:
                return "No se detecto texto en la pantalla."
            lines = [f"Textos detectados ({len(texts)} bloques):"]
            for t in texts[:30]:
                lines.append(f"  '{t['text']}' conf={t['conf']} en ({t['x']},{t['y']})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error en OCR: {e}"

    # ── UI Tree scan ──
    if action == "ui_tree":
        try:
            elements = get_ui_tree()
            if not elements:
                return "No se detectaron elementos UI."
            by_type = {}
            for el in elements:
                t = el.get("type", "Unknown")
                by_type.setdefault(t, []).append(el)
            lines = [f"Elementos UI ({len(elements)} total):"]
            for t, els in sorted(by_type.items(), key=lambda x: -len(x[1]))[:15]:
                lines.append(f"  {t}: {len(els)}")
                for el in els[:3]:
                    if el.get("text"):
                        lines.append(f"    '{el['text'][:50]}' en ({el['x']},{el['y']})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error en UI tree: {e}"

    # ── Active window info ──
    if action == "window":
        try:
            info = get_active_window_info()
            if not info:
                return "No se pudo detectar la ventana activa."
            lines = [f"Ventana activa: {info.get('title', '?')}"]
            lines.append(f"Posicion: ({info.get('left', 0)},{info.get('top', 0)})")
            lines.append(f"Tamano: {info.get('width', 0)}x{info.get('height', 0)}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # ── Find / Locate element ──
    if action in ("find", "locate", "buscar", "ubicar"):
        if not target:
            return "Necesito una descripcion del elemento a buscar."

        strategy = parameters.get("strategy", "auto").lower()

        if strategy == "ocr":
            matches = find_text_on_screen(target)
            if not matches:
                return f"No encontre '{target}' en la pantalla por OCR."
            best = matches[0]
            if click:
                pyautogui.moveTo(best["x"], best["y"], duration=0.3)
                time.sleep(0.1)
                pyautogui.click()
                return f"Encontre y cliquee '{target}' en ({best['x']},{best['y']}) con OCR (conf={best['conf']})."
            return f"'{target}' encontrado en ({best['x']},{best['y']}) con OCR (conf={best['conf']})."

        if strategy == "ui":
            matches = find_in_ui_tree(target)
            if not matches:
                return f"No encontre '{target}' en el arbol UI."
            best = matches[0]
            x, y = best.get("x", 0), best.get("y", 0)
            if click:
                pyautogui.moveTo(x, y, duration=0.3)
                time.sleep(0.1)
                pyautogui.click()
                return f"Encontre y cliquee '{target}' en ({x},{y}) via UI Automation."
            return f"'{target}' encontrado en ({x},{y}) via UI Automation."

        # ── Auto strategy (try all) ──
        result = find_element_advanced(target)
        if result.get("found"):
            x, y = result["x"], result["y"]
            strat = result["strategy"]
            conf = result["confidence"]
            if player:
                player.write_log(f"'{target}' encontrado via {strat} (conf={conf}) en ({x},{y})")
            if click:
                pyautogui.moveTo(x, y, duration=0.3)
                time.sleep(0.1)
                pyautogui.click()
                return f"Encontre y cliquee '{target}' en ({x},{y}) via {strat}."
            return f"'{target}' ubicado en ({x},{y}) via {strat} (confianza: {conf})."
        return f"No encontre '{target}' en la pantalla."

    # ── Click element ──
    if action in ("click", "cliquear", "clic"):
        if not target:
            return "Necesito una descripcion del elemento a cliquear."

        result = find_element_advanced(target)
        if not result.get("found"):
            return f"No encontre '{target}' en la pantalla."
        x, y = result["x"], result["y"]
        pyautogui.moveTo(x, y, duration=0.3)
        time.sleep(0.1)
        pyautogui.click()
        if player:
            player.write_log(f"Clic en '{target}' -> ({x},{y}) via {result['strategy']}")
        return f"Cliquee '{target}' en ({x},{y}) via {result['strategy']}."

    # ── Right click ──
    if action in ("right_click", "rightclick", "clic_derecho"):
        if not target:
            return "Necesito una descripcion."
        result = find_element_advanced(target)
        if not result.get("found"):
            return f"No encontre '{target}'."
        x, y = result["x"], result["y"]
        pyautogui.moveTo(x, y, duration=0.3)
        time.sleep(0.1)
        pyautogui.rightClick()
        if player:
            player.write_log(f"Clic derecho en '{target}' -> ({x},{y}) via {result['strategy']}")
        return f"Clic derecho en '{target}' en ({x},{y}) via {result['strategy']}."

    # ── Double click ──
    if action in ("double_click", "doubleclick", "doble_clic"):
        if not target:
            return "Necesito una descripcion."
        result = find_element_advanced(target)
        if not result.get("found"):
            return f"No encontre '{target}'."
        x, y = result["x"], result["y"]
        pyautogui.moveTo(x, y, duration=0.3)
        time.sleep(0.1)
        pyautogui.doubleClick()
        if player:
            player.write_log(f"Doble clic en '{target}' -> ({x},{y}) via {result['strategy']}")
        return f"Doble clic en '{target}' en ({x},{y}) via {result['strategy']}."

    # ── Click at specific coordinates ──
    if action == "click_at":
        x = int(parameters.get("x", 0))
        y = int(parameters.get("y", 0))
        if x <= 0 or y <= 0:
            return "Coordenadas invalidas."
        pyautogui.moveTo(x, y, duration=0.2)
        time.sleep(0.1)
        pyautogui.click()
        return f"Clic en coordenadas ({x},{y})."

    return (f"Accion '{action}' no reconocida. Usa: find, scan, ocr, ui_tree, window, "
            f"click, right_click, double_click, click_at, describe. "
            f"Para find podes usar strategy=ocr | ui | auto (default: auto).")
