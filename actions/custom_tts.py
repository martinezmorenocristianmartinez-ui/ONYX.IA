"""custom_tts.py — Módulo para tu propio modelo de Text-to-Speech personalizado
Para agregar tu propio modelo de voz, sigue las instrucciones dentro de este archivo!
"""

import os
import tempfile
import ctypes
from pathlib import Path

# Ruta para guardar configuraciones de tu modelo TTS personalizado
CONFIG_PATH = Path(__file__).parent.parent / "config" / "custom_tts_config.json"

# Cargar configuración por defecto
DEFAULT_CONFIG = {
    "enabled": False,  # Cambia a True cuando tengas tu modelo listo
    "model_type": "custom",  # Tipo de modelo: custom, coqui, openvoice, etc.
    "model_path": "",  # Ruta al directorio de tu modelo
    "voice_name": "Mi Voz Personalizada",
    "rate": 1.0,
    "pitch": 1.0,
    "volume": 1.0
}

def load_config():
    """Carga la configuración de TTS personalizado"""
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    
    try:
        import json
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            # Merge con defaults
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Guarda la configuración de TTS personalizado"""
    try:
        import json
        os.makedirs(CONFIG_PATH.parent, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def custom_tts_speak(text: str) -> bool:
    """
    Implementa aquí tu propio motor TTS personalizado!
    Esta función debe:
    1. Convertir el texto a audio
    2. Guardarlo temporalmente como MP3/WAV
    3. Reproducirlo usando mciSendString (como en leer_articulo)
    4. Limpiar el archivo temporal
    """
    config = load_config()
    
    if not config["enabled"]:
        # Si el TTS personalizado está desactivado, retornamos False
        # para que ONYX use el sistema de voz predeterminado
        return False
    
    mp3_path = None
    try:
        # 1. Crear archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            mp3_path = fp.name
        
        # ========================================================
        # AQUÍ DEBES IMPLEMENTAR TU MODELO TTS PERSONALIZADO
        # Ejemplos de integraciones:
        # - Coqui TTS: https://github.com/coqui-ai/TTS
        # - OpenVoice: https://github.com/myshell-ai/OpenVoice
        # - SpeechT5: https://huggingface.co/microsoft/speecht5
        # - O cualquier otro modelo que prefieras!
        #
        # Ejemplo de cómo sería con Coqui TTS:
        # from TTS.api import TTS
        # tts = TTS(config["model_path"])
        # tts.tts_to_file(text=text, file_path=mp3_path)
        #
        # Por ahora, esta es una plantilla vacía — ¡llenala con tu código!
        # ========================================================
        
        # Por defecto, retornamos False para que use el TTS predeterminado
        return False
        
    except Exception as e:
        print(f"[Custom TTS] Error: {e}")
        return False
    finally:
        # Limpiar archivo temporal
        if mp3_path and os.path.exists(mp3_path):
            try:
                os.unlink(mp3_path)
            except Exception:
                pass

def play_audio_file(file_path: str):
    """Función auxiliar para reproducir archivos de audio (MP3/WAV) en Windows"""
    try:
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            return False
        
        ctypes.windll.winmm.mciSendStringW(
            f'open "{file_path}" type mpegvideo alias custom_tts', None, 0, 0)
        ctypes.windll.winmm.mciSendStringW(
            'play custom_tts wait', None, 0, 0)
        ctypes.windll.winmm.mciSendStringW(
            'close custom_tts', None, 0, 0)
        return True
    except Exception as e:
        print(f"[Custom TTS] Error playing audio: {e}")
        return False
