"""weather_report.py — Clean weather forecasting action."""
import urllib.request
import urllib.parse
import json

def weather_action(parameters: dict, player=None) -> str:
    """Fetch current weather report from wttr.in in clean text format."""
    city = parameters.get("city", "Urabá").strip()
    if not city:
        city = "Urabá"
        
    try:
        # Request text/json format from wttr.in
        encoded_city = urllib.parse.quote(city)
        url = f"https://wttr.in/{encoded_city}?format=%C+%t+%h+%w"
        
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0"}
        )
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read().decode("utf-8").strip()
            
        report = f"Current weather in {city}: {data}"
        if player:
            player.write_log(f"🌤️ {report}")
        return report
    except Exception as e:
        # Fallback response
        msg = f"Unable to fetch real-time weather details for {city}: {e}"
        if player:
            player.write_log(f"⚠️ {msg}")
        return f"Señor Cristian, tengo problemas para conectarme al servicio meteorológico en este momento. Sin embargo, puedo buscar en línea si lo desea."
