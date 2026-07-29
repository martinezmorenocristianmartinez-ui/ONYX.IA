import time
import pyautogui
import pygetwindow as gw
from actions._browser_launch import open_url, _find_browser_window, get_preferred_browser


def browser_control(parameters: dict, player=None) -> str:
    """
    Controla el navegador activo del usuario (Chrome, Edge, Firefox, etc.) mediante simulación de teclado.
    Si no hay navegador abierto, abre uno automáticamente.
    """
    action = parameters.get("action", "")
    query = parameters.get("query", "")
    url = parameters.get("url", "")
    
    # 1. Encontrar el navegador activo
    target_window = _find_browser_window()

    # Si no hay navegador, abrir uno
    if not target_window:
        browser_name = get_preferred_browser()
        opened = open_url("about:blank")
        if not opened:
            return f"No se encontró ningún navegador abierto y no pude abrir {browser_name}."
        # Buscar la ventana que se acaba de abrir
        for _ in range(5):
            time.sleep(1)
            target_window = _find_browser_window()
            if target_window:
                break
        if not target_window:
            # Si no encontramos la ventana, abrimos la URL/búsqueda directamente
            if action == "search" and query:
                open_url(f"https://www.google.com/search?q={query.replace(' ', '+')}")
                return f"Buscando '{query}' en {browser_name}."
            elif url:
                open_url(url)
                return f"Navegando a {url} en {browser_name}."
            return f"{browser_name} abierto."
        
    try:
        # 2. Restaurar y Enfocar la ventana del navegador
        if target_window.isMinimized:
            target_window.restore()
        target_window.activate()
        time.sleep(0.05) # Tiempo para que la ventana tome foco
        
        # 3. Ejecutar la acción mediante atajos de teclado universales
        if action == "go_to":
            url = parameters.get("url", "")
            if not url:
                return "Error: Falta la URL."
            # Foco en barra de direcciones
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(0.05)
            pyautogui.write(url, interval=0.001)
            pyautogui.press('enter')
            return f"Navegando a {url} en la ventana '{target_window.title}'."
            
        elif action == "search":
            query = parameters.get("query", "")
            if not query:
                return "Error: Falta la búsqueda (query)."
            # Foco en barra de direcciones
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(0.05)
            pyautogui.write(query, interval=0.001)
            pyautogui.press('enter')
            return f"Buscando '{query}' en la ventana '{target_window.title}'."
            
        elif action == "new_tab":
            url = parameters.get("url", "")
            pyautogui.hotkey('ctrl', 't')
            time.sleep(0.08)
            if url:
                pyautogui.write(url, interval=0.001)
                pyautogui.press('enter')
                return f"Nueva pestaña abierta y navegando a {url}."
            return "Nueva pestaña abierta."
            
        elif action == "close_tab":
            pyautogui.hotkey('ctrl', 'w')
            return "Pestaña actual cerrada."
            
        elif action == "scroll":
            direction = parameters.get("direction", "down")
            if direction == "down":
                pyautogui.press('pgdn')
            else:
                pyautogui.press('pgup')
            return f"Scroleo hacia {direction} completado."
            
        else:
            return f"Acción '{action}' no es compatible con el control de navegador activo. Usa atajos de teclado estándar."
            
    except Exception as e:
        return f"Error al intentar controlar el navegador: {str(e)}"
