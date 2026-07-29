import time
from actions._vision import get_api_key, capture_screen_resized, extract_coords, call_vision


def visual_click(parameters: dict, player=None) -> str:
    """
    Toma una captura de pantalla, usa visión para encontrar las coordenadas del elemento descrito,
    y utiliza pyautogui para mover el mouse y hacer clic de forma nativa.
    """
    element_desc = parameters.get("element_description", "")
    if not element_desc:
        return "Error: No se especificó el elemento a cliquear."

    api_key = get_api_key()
    if not api_key:
        return "Error: No se encontró API key en config/api_keys.json."

    try:
        import pyautogui
    except ImportError:
        return "Error: Falta pyautogui."

    if player:
        player.write_log(f"Buscando coordenadas para: '{element_desc}'...")

    try:
        b64, orig_w, orig_h, scale_x, scale_y = capture_screen_resized(1280)
        if not b64:
            return "Error: No se pudo capturar la pantalla."

        prompt = (
            f"Localiza EXACTAMENTE el CENTRO del elemento descrito como '{element_desc}'. "
            "Devuelve ÚNICAMENTE las coordenadas [X, Y] del centro. "
            "Si el elemento no existe, devuelve [0, 0]. Sin texto adicional."
        )
        response = call_vision(prompt, b64, max_tokens=500, temperature=0.1)
        if not response:
            return "Error: No hubo respuesta de la IA."

        coords = extract_coords(response)
        if not coords:
            if "[]" in response or "[0, 0]" in response:
                return f"No se encontró el elemento '{element_desc}' en la pantalla."
            return f"Error al parsear coordenadas. Respuesta: {response[:200]}"

        ai_x, ai_y = coords
        real_x = int(ai_x * scale_x)
        real_y = int(ai_y * scale_y)

        if player:
            player.write_log(f"Coordenadas: [{ai_x},{ai_y}]→[{real_x},{real_y}]")

        pyautogui.moveTo(real_x, real_y, duration=0.5, tween=pyautogui.easeInOutQuad)
        time.sleep(0.2)
        pyautogui.click()

        return f"Clic visual ejecutado en '{element_desc}' (X={real_x}, Y={real_y})."

    except Exception as e:
        return f"Error en visual_click: {str(e)}"
