"""system_monitor.py — Clean system hardware metrics fetcher."""
import psutil

def system_monitor(parameters: dict = None, player=None) -> str:
    """Fetch detailed system metrics or manage processes."""
    action = parameters.get("action", "report") if parameters else "report"
    
    try:
        if action == "kill":
            name = parameters.get("name", "")
            if not name: return "Necesito el nombre del proceso, Señor Cristian."
            count = 0
            for proc in psutil.process_iter(['name']):
                if name.lower() in proc.info['name'].lower():
                    proc.kill()
                    count += 1
            return f"He finalizado {count} instancias de {name}, Señor Cristian."

        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        battery_msg = ""
        battery = psutil.sensors_battery()
        if battery:
            plugged = "conectado" if battery.power_plugged else "descargando"
            battery_msg = f" | Batería: {battery.percent}% ({plugged})"
            
        report = f"CPU: {cpu}% | RAM: {ram}% | Disco: {disk}%{battery_msg}"
        if player:
            player.write_log(f"💻 Métricas: {report}")
        return f"Informe del sistema, Señor Cristian: {report}"
    except Exception as e:
        return f"Error al monitorear, Señor Cristian: {e}"
