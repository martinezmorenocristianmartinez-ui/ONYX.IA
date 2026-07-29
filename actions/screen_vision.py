from actions._vision import get_api_key, capture_screen, call_vision


def screen_vision(parameters: dict, player=None) -> str:
    """
    Toma una captura de pantalla y la analiza usando OpenRouter (multimodal).
    """
    if not get_api_key():
        return (
            "Error: No se encontró una clave de API en config/api_keys.json. "
            "Asegúrate de haber configurado tu clave."
        )

    query = parameters.get("query") or parameters.get("text") or parameters.get("question") or "¿Qué ves en mi pantalla?"

    if player:
        player.write_log("Capturando pantalla...")

    b64, _, _ = capture_screen()
    if not b64:
        return "Error al capturar la pantalla."

    result = call_vision(f"Esta es una captura de mi pantalla. {query}", b64, max_tokens=4000, temperature=0.1)
    if not result:
        return "Error al conectar con OpenRouter para la visión."
    return result
