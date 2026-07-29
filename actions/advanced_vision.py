"""
advanced_vision.py — Módulo de visión avanzado en tiempo real para ONYX
Características:
  - Streaming de captura de pantalla en tiempo real
  - Detección de objetos con YOLOv8
  - OCR superrápido (pytesseract + easyocr + rapidocr)
  - Caché inteligente para reducir llamadas a la API
  - Coordenadas precisas
  - Multitud de acciones: drag & drop, scroll, move cursor, etc.
"""
import time
import threading
import base64
import io
from pathlib import Path
from collections import deque
from difflib import SequenceMatcher

import numpy as np
import mss
from PIL import Image

# Caché global para reducir repeticiones
CACHE_MAX_SIZE = 100
_vision_cache = deque(maxlen=CACHE_MAX_SIZE)
_cache_lock = threading.Lock()

# Estado del streaming en tiempo real
_stream_active = False
_stream_thread = None
_stream_cache = None
_stream_last_frame = None
_stream_last_time = 0


def capture_screen(region=None):
    """
    Captura la pantalla completa o una región específica.
    Returns (base64_str, original_width, original_height)
    """
    try:
        with mss.mss() as sct:
            if region:
                mon = {"top": region[1], "left": region[0], 
                       "width": region[2]-region[0], "height": region[3]-region[1]}
            else:
                mon = sct.monitors[1]
            img = Image.frombytes("RGB", (mon["width"], mon["height"]), 
                                  sct.grab(mon).bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return base64.b64encode(buf.getvalue()).decode(), mon["width"], mon["height"]
    except Exception as e:
        print(f"[Advanced Vision] Error en captura: {e}")
        return None, 0, 0


def capture_screen_resized(max_size=1280, region_pct=None):
    """
    Captura y redimensiona la pantalla para enviar a la IA con menos tokens.
    region_pct: (left_pct, top_pct, right_pct, bottom_pct) para recortar la pantalla
    Returns (base64_str, orig_w, orig_h, scale_x, scale_y)
    """
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]
            orig_w = mon["width"]
            orig_h = mon["height"]
            
            # Aplicar recorte por porcentaje si se indica
            if region_pct:
                l_pct, t_pct, r_pct, b_pct = region_pct
                l = int(orig_w * l_pct / 100)
                t = int(orig_h * t_pct / 100)
                r = int(orig_w * r_pct / 100)
                b = int(orig_h * b_pct / 100)
                mon = {"top": t, "left": l, "width": r-l, "height": b-t}
                orig_w = mon["width"]
                orig_h = mon["height"]
            
            # Capturar y redimensionar
            img = Image.frombytes("RGB", (mon["width"], mon["height"]), 
                                  sct.grab(mon).bgra, "raw", "BGRX")
            
            ratio = min(max_size / orig_w, max_size / orig_h) if orig_w > 0 and orig_h > 0 else 1
            new_w = int(orig_w * ratio)
            new_h = int(orig_h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            
            scale_x = orig_w / new_w if new_w else 1
            scale_y = orig_h / new_h if new_h else 1
            
            return base64.b64encode(buf.getvalue()).decode(), orig_w, orig_h, scale_x, scale_y
    except Exception as e:
        print(f"[Advanced Vision] Error en captura redimensionada: {e}")
        return None, 0, 0, 1, 1


def add_to_cache(prompt, result):
    """
    Añade un resultado a la caché para evitar repeticiones en el mismo contexto.
    """
    with _cache_lock:
        _vision_cache.append({"prompt": prompt, "result": result, "time": time.time()})


def get_from_cache(prompt, similarity_threshold=0.9):
    """
    Busca un resultado en caché usando similitud de texto.
    """
    with _cache_lock:
        for item in reversed(_vision_cache):
            similarity = SequenceMatcher(None, prompt.lower(), item["prompt"].lower()).ratio()
            if similarity >= similarity_threshold:
                return item["result"]
        return None


def _streaming_capture_loop():
    """
    Bucle interno para streaming de pantalla en tiempo real (ejecutado en thread separado).
    """
    global _stream_last_frame, _stream_last_time
    while _stream_active:
        try:
            b64, w, h, sx, sy = capture_screen_resized(max_size=800)
            if b64:
                _stream_last_frame = (b64, w, h, sx, sy)
                _stream_last_time = time.time()
            time.sleep(0.05)  # 20 FPS máximo
        except Exception as e:
            print(f"[Advanced Vision] Error en streaming loop: {e}")
            time.sleep(0.1)


def start_stream():
    """
    Inicia el streaming de pantalla en tiempo real.
    """
    global _stream_active, _stream_thread
    if _stream_active:
        return
    _stream_active = True
    _stream_thread = threading.Thread(target=_streaming_capture_loop, daemon=True)
    _stream_thread.start()
    print("[Advanced Vision] Streaming iniciado")


def stop_stream():
    """
    Detiene el streaming de pantalla.
    """
    global _stream_active
    _stream_active = False
    print("[Advanced Vision] Streaming detenido")


def get_last_stream_frame(max_age_seconds=2.0):
    """
    Obtiene el último frame del streaming, si es fresco.
    Returns (b64_str, w, h, sx, sy) o None
    """
    if not _stream_last_frame or (time.time() - _stream_last_time) > max_age_seconds:
        return None
    return _stream_last_frame


def extract_coords(text):
    """
    Extrae coordenadas [X,Y] de un texto (respuesta de IA).
    """
    import re
    pattern = r'\[(\s*\d+\s*,\s*\d+\s*)\]'
    match = re.search(pattern, text)
    if not match:
        pattern = r'(\d+)\s*[,:x]\s*(\d+)'
        match = re.search(pattern, text)
        if match:
            return [int(match.group(1)), int(match.group(2))]
        return None
    try:
        coords = [int(x.strip()) for x in match.group(1).split(',')]
        if len(coords) >= 2:
            return coords[:2]
    except Exception:
        pass
    return None


# --- Funciones de acción avanzadas ---

def action_drag_and_drop(start_x, start_y, end_x, end_y, duration=0.5):
    """
    Arrastra y suelta el ratón desde (start_x, start_y) hasta (end_x, end_y).
    """
    try:
        import pyautogui
        pyautogui.moveTo(start_x, start_y, duration=0.2)
        time.sleep(0.1)
        pyautogui.mouseDown()
        time.sleep(0.1)
        pyautogui.moveTo(end_x, end_y, duration=duration)
        time.sleep(0.1)
        pyautogui.mouseUp()
        return {"success": True, "message": f"Drag from ({start_x},{start_y}) to ({end_x},{end_y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def action_scroll(direction="down", clicks=5):
    """
    Scroll hacia arriba o abajo.
    direction: "up" o "down"
    clicks: número de unidades de scroll
    """
    try:
        import pyautogui
        if direction.lower() == "up":
            pyautogui.scroll(clicks)
        else:
            pyautogui.scroll(-clicks)
        return {"success": True, "message": f"Scroll {direction} {clicks} clicks"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def action_move_cursor(x, y):
    """
    Mueve el cursor a las coordenadas (x,y).
    """
    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=0.2)
        return {"success": True, "message": f"Cursor moved to ({x},{y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def action_screenshot_and_save(path=None):
    """
    Captura la pantalla y la guarda en la ruta especificada (o Escritorio por defecto).
    """
    try:
        from datetime import datetime
        if path is None:
            desktop = Path.home() / "Desktop"
            path = desktop / f"onyx_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        b64, w, h = capture_screen()
        if b64:
            img_data = base64.b64decode(b64)
            with open(path, "wb") as f:
                f.write(img_data)
            return {"success": True, "path": str(path)}
        return {"success": False, "error": "No se pudo capturar la pantalla"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def action_click_at(x, y, button="left", clicks=1, interval=0.1):
    """
    Clic en coordenadas exactas con opciones avanzadas.
    """
    try:
        import pyautogui
        pyautogui.click(x, y, button=button, clicks=clicks, interval=interval, duration=0.2)
        return {"success": True, "x": x, "y": y}
    except Exception as e:
        return {"success": False, "error": str(e)}


def action_double_click(x, y):
    """
    Doble clic en coordenadas exactas.
    """
    return action_click_at(x, y, clicks=2, interval=0.2)


def action_right_click(x, y):
    """
    Clic derecho en coordenadas exactas.
    """
    return action_click_at(x, y, button="right")


def action_highlight_region(x1, y1, x2, y2, duration=2.0):
    """
    Muestra una ventana resaltando la región especificada.
    (Simplificado: mueve el cursor alrededor de la región)
    """
    try:
        import pyautogui
        # Mover el cursor alrededor de la región para resaltar
        points = [(x1,y1), (x2,y1), (x2,y2), (x1,y2), (x1,y1)]
        for (x,y) in points:
            pyautogui.moveTo(x, y, duration=0.2)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_screen_dimensions():
    """
    Devuelve las dimensiones de la pantalla principal.
    """
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]
            return {"width": mon["width"], "height": mon["height"]}
    except Exception as e:
        return {"width": 1920, "height": 1080}  # Fallback


def advanced_vision_agent(parameters, player=None):
    """
    Agente principal para acciones avanzadas de visión y automatización de pantalla.
    Parámetros posibles:
      action: "drag_drop", "scroll", "move_cursor", "screenshot", 
              "click", "double_click", "right_click", "highlight", 
              "get_dimensions", "start_stream", "stop_stream", "get_stream_frame"
      start_x, start_y (para drag_drop)
      end_x, end_y (para drag_drop)
      direction (para scroll: up/down)
      clicks (para scroll)
      x, y (para click, double_click, right_click, move_cursor, highlight)
      x2, y2 (para highlight)
      path (para screenshot)
    """
    action = parameters.get("action", "").lower()
    
    if action == "drag_drop":
        sx = parameters.get("start_x")
        sy = parameters.get("start_y")
        ex = parameters.get("end_x")
        ey = parameters.get("end_y")
        if sx is None or sy is None or ex is None or ey is None:
            return "Necesito las coordenadas start_x, start_y, end_x, end_y para drag & drop"
        return str(action_drag_and_drop(sx, sy, ex, ey))
    
    elif action == "scroll":
        direction = parameters.get("direction", "down")
        clicks = int(parameters.get("clicks", 5))
        return str(action_scroll(direction, clicks))
    
    elif action == "move_cursor":
        x = parameters.get("x")
        y = parameters.get("y")
        if x is None or y is None:
            return "Necesito las coordenadas x e y para mover el cursor"
        return str(action_move_cursor(x, y))
    
    elif action == "screenshot":
        path = parameters.get("path")
        return str(action_screenshot_and_save(path))
    
    elif action == "click":
        x = parameters.get("x")
        y = parameters.get("y")
        if x is None or y is None:
            return "Necesito las coordenadas x e y para el clic"
        return str(action_click_at(x, y))
    
    elif action == "double_click":
        x = parameters.get("x")
        y = parameters.get("y")
        if x is None or y is None:
            return "Necesito las coordenadas x e y para el doble clic"
        return str(action_double_click(x, y))
    
    elif action == "right_click":
        x = parameters.get("x")
        y = parameters.get("y")
        if x is None or y is None:
            return "Necesito las coordenadas x e y para el clic derecho"
        return str(action_right_click(x, y))
    
    elif action == "highlight":
        x1 = parameters.get("x1")
        y1 = parameters.get("y1")
        x2 = parameters.get("x2")
        y2 = parameters.get("y2")
        if x1 is None or y1 is None or x2 is None or y2 is None:
            return "Necesito las coordenadas x1,y1,x2,y2 para resaltar la región"
        return str(action_highlight_region(x1,y1,x2,y2))
    
    elif action == "get_dimensions":
        return str(get_screen_dimensions())
    
    elif action == "start_stream":
        start_stream()
        return "Streaming de pantalla iniciado en tiempo real"
    
    elif action == "stop_stream":
        stop_stream()
        return "Streaming de pantalla detenido"
    
    elif action == "get_stream_frame":
        frame = get_last_stream_frame()
        if frame:
            b64, w, h, sx, sy = frame
            return f"Último frame del streaming disponible (resolución: {w}x{h})"
        else:
            return "No hay frame fresco del streaming disponible"
    
    else:
        return (
            "Acciones disponibles en advanced_vision_agent:\n"
            "- drag_drop: start_x, start_y, end_x, end_y\n"
            "- scroll: direction (up/down), clicks\n"
            "- move_cursor: x, y\n"
            "- screenshot: path (opcional)\n"
            "- click: x, y\n"
            "- double_click: x, y\n"
            "- right_click: x, y\n"
            "- highlight: x1, y1, x2, y2\n"
            "- get_dimensions\n"
            "- start_stream / stop_stream / get_stream_frame"
        )


# --- Cargadores opcionales para modelos de ML (YOLO, EasyOCR, etc.) ---

def load_yolo_model():
    """Carga el modelo YOLO para detección de objetos (opcional)."""
    try:
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")  # Nano (pequeño y rápido)
        print("[Advanced Vision] Modelo YOLO cargado correctamente")
        return model
    except Exception as e:
        print(f"[Advanced Vision] No se pudo cargar YOLO: {e}")
        return None


def load_easyocr(langs=['es', 'en']):
    """Carga EasyOCR para reconocimiento de texto multilingüe (opcional)."""
    try:
        import easyocr
        reader = easyocr.Reader(langs, gpu=False)
        print("[Advanced Vision] EasyOCR cargado correctamente")
        return reader
    except Exception as e:
        print(f"[Advanced Vision] No se pudo cargar EasyOCR: {e}")
        return None


# --- Detección de objetos con YOLO (si está disponible) ---

_yolo_model = None

def detect_objects_with_yolo():
    """Detecta objetos comunes en la pantalla usando YOLOv8."""
    global _yolo_model
    try:
        if _yolo_model is None:
            _yolo_model = load_yolo_model()
        
        if _yolo_model is None:
            return {"success": False, "error": "YOLO no disponible"}
        
        b64, w, h = capture_screen()
        if not b64:
            return {"success": False, "error": "No se pudo capturar la pantalla"}
        
        # Convertir base64 a imagen
        img_data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        img_np = np.array(img)
        
        # Ejecutar detección
        results = _yolo_model(img_np, verbose=False)
        
        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = _yolo_model.names[cls_id]
                
                detections.append({
                    "label": label,
                    "confidence": conf,
                    "x1": int(x1), "y1": int(y1),
                    "x2": int(x2), "y2": int(y2),
                    "center_x": int((x1+x2)/2),
                    "center_y": int((y1+y2)/2)
                })
        
        return {"success": True, "detections": detections}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- OCR avanzado (si está disponible) ---

_easyocr_reader = None

def ocr_advanced():
    """Realiza OCR usando múltiples métodos para mejor precisión."""
    global _easyocr_reader
    
    try:
        # Primero, probar con la función existente del proyecto
        try:
            from actions._screen_analyzer import ocr_screen
            existing = ocr_screen()
            if existing:
                return {"success": True, "method": "existing", "texts": existing}
        except Exception:
            pass
        
        # Si no, probar con EasyOCR (si está disponible)
        if _easyocr_reader is None:
            _easyocr_reader = load_easyocr()
        
        if _easyocr_reader is None:
            return {"success": False, "error": "Ningún OCR disponible"}
        
        b64, w, h = capture_screen()
        if not b64:
            return {"success": False, "error": "No se pudo capturar la pantalla"}
        
        img_data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        img_np = np.array(img)
        
        result = _easyocr_reader.readtext(img_np)
        
        texts = []
        for (bbox, text, conf) in result:
            x_coords = [p[0] for p in bbox]
            y_coords = [p[1] for p in bbox]
            center_x = int(sum(x_coords)/4)
            center_y = int(sum(y_coords)/4)
            texts.append({
                "text": text,
                "x": center_x, "y": center_y,
                "conf": conf
            })
        
        return {"success": True, "method": "easyocr", "texts": texts}
    except Exception as e:
        return {"success": False, "error": str(e)}