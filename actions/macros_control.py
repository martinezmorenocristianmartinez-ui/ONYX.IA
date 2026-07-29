"""macros_control.py — Advanced macro management and execution for ONYX."""
import json
import time
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MACROS_FILE = BASE_DIR / "config" / "macros.json"
POSITIONS_FILE = BASE_DIR / "config" / "saved_positions.json"

def save_position(name: str, x: int, y: int):
    """Guarda una posición de pantalla con nombre."""
    if not POSITIONS_FILE.exists():
        POSITIONS_FILE.write_text(json.dumps({}), encoding="utf-8")
    positions = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
    positions[name] = {"x": x, "y": y}
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2), encoding="utf-8")

def get_position(name: str):
    """Obtiene una posición guardada."""
    if not POSITIONS_FILE.exists():
        return None
    positions = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
    return positions.get(name)

def macros_control(parameters: dict, player=None) -> str:
    """
    Manage and execute automation macros, and save/use mouse positions.
    Actions: run, create, list, delete, record_position, click_position, list_positions
    """
    action = parameters.get("action", "run").lower()
    macro_name = parameters.get("name", "").lower()
    position_name = parameters.get("position_name", "").lower()
    
    if not MACROS_FILE.exists():
        MACROS_FILE.write_text(json.dumps({}), encoding="utf-8")
        
    macros = json.loads(MACROS_FILE.read_text(encoding="utf-8"))

    if action == "record_position":
        try:
            import pyautogui
            if not position_name:
                position_name = "saltar_anuncio"  # default para el botón de YouTube
            # Esperar 3 segundos para que el usuario posicione el mouse
            if player:
                player.write_log(f"📸 Posiciona el mouse en el botón '{position_name}'... (3 segundos)")
            time.sleep(3)
            x, y = pyautogui.position()
            save_position(position_name, x, y)
            return f"Posición '{position_name}' guardada en X={x}, Y={y}, Señor Cristian!"
        except Exception as e:
            return f"Error guardando la posición, Señor Cristian: {e}"
    
    elif action == "click_position":
        try:
            import pyautogui
            if not position_name:
                position_name = "saltar_anuncio"
            pos = get_position(position_name)
            if pos:
                pyautogui.moveTo(pos["x"], pos["y"], duration=0.3)
                time.sleep(0.2)
                pyautogui.click()
                return f"Clic en posición '{position_name}' ({pos['x']}, {pos['y']}), Señor Cristian!"
            return f"No encontré la posición '{position_name}', Señor Cristian. Primero graba una posición!"
        except Exception as e:
            return f"Error haciendo clic en la posición, Señor Cristian: {e}"
    
    elif action == "list_positions":
        if not POSITIONS_FILE.exists():
            return "No hay posiciones guardadas, Señor Cristian."
        positions = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
        if not positions:
            return "No hay posiciones guardadas, Señor Cristian."
        msg = "Posiciones guardadas:\n"
        for name, coords in positions.items():
            msg += f"  • {name}: ({coords['x']}, {coords['y']})\n"
        return msg

    elif action == "create":
        steps = parameters.get("steps", [])
        if not macro_name or not steps:
            return "Señor Cristian, necesito un nombre y los pasos para crear el macro."
        macros[macro_name] = steps
        MACROS_FILE.write_text(json.dumps(macros, indent=2), encoding="utf-8")
        return f"Macro '{macro_name}' creado exitosamente, Señor Cristian."

    elif action == "list":
        if not macros:
            return "No hay macros registrados actualmente, Señor Cristian."
        names = ", ".join(macros.keys())
        return f"Macros disponibles, Señor Cristian: {names}"

    elif action == "delete":
        if macro_name in macros:
            del macros[macro_name]
            MACROS_FILE.write_text(json.dumps(macros, indent=2), encoding="utf-8")
            return f"Macro '{macro_name}' eliminado, Señor Cristian."
        return f"No encontré el macro '{macro_name}', Señor Cristian."

    elif action == "run":
        if not macro_name:
            return "Señor Cristian, ¿qué macro desea ejecutar?"
        
        if macro_name not in macros:
            return f"El macro '{macro_name}' no existe, Señor Cristian."

        steps = macros[macro_name]
        try:
            import pyautogui
            import subprocess
            
            if player:
                player.write_log(f"⚡ Ejecutando Macro: {macro_name}")
            
            for step in steps:
                stype = step.get("type")
                val = step.get("value")
                delay = step.get("delay", 0.5)
                
                if stype == "key":
                    pyautogui.press(val)
                elif stype == "hotkey":
                    if isinstance(val, list):
                        pyautogui.hotkey(*val)
                    else:
                        pyautogui.hotkey(val)
                elif stype == "write":
                    pyautogui.write(val, interval=0.05)
                elif stype == "open":
                    os.system(f'start "" "{val}"')
                elif stype == "wait":
                    time.sleep(float(val))
                    continue # skip standard delay
                elif stype == "click_position":
                    pos = get_position(val)
                    if pos:
                        pyautogui.moveTo(pos["x"], pos["y"], duration=0.3)
                        time.sleep(0.2)
                        pyautogui.click()
                
                time.sleep(delay)
                
            return f"Macro '{macro_name}' ejecutado por completo, Señor Cristian."
        except Exception as e:
            return f"Error ejecutando el macro, Señor Cristian: {e}"

    return f"Acción '{action}' no reconocida para macros."
