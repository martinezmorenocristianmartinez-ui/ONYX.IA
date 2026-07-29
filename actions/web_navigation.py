import traceback
import urllib.parse
from actions._browser_launch import open_url


def web_navigation(parameters: dict, player=None) -> str:
    """Handle web navigation, especially direct YouTube playback."""
    action = parameters.get("action", "").lower()
    query = parameters.get("query", "")

    if not action or not query:
        return "Error: Faltan parametros ('action' o 'query')."

    try:
        if action in ("play_youtube", "youtube"):
            from actions.youtube_video import youtube_video

            return youtube_video({"action": "play", "query": query}, player=player)

        if action == "search":
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
            open_url(search_url)
            return f"He abierto una busqueda en Google para '{query}'."

        return f"Error: Accion web '{action}' desconocida."

    except Exception as exc:
        return f"Error al navegar: {exc}\n{traceback.format_exc()}"
