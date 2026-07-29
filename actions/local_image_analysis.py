"""
local_image_analysis.py - Análisis de imágenes 100% LOCAL para ONYX.

No depende de Gemini ni de ningún API. Combina:
  1. BLIP (transformers)  -> descripción visual de la imagen.
  2. OCR (easyocr)        -> texto presente en la imagen (best-effort).
  3. LLM local (Ollama)   -> redacta la respuesta en español y contesta la
                             pregunta puntual del usuario (best-effort).

Si hay un modelo de visión REAL en Ollama (llava, moondream, llama3.2-vision,
etc.) se usa ese directamente por dar mejor calidad. BLIP es el respaldo que
funciona con las librerías ya instaladas (torch + transformers).
"""
from __future__ import annotations

import base64
import json
import os
import threading
import urllib.request
from pathlib import Path

OLLAMA_HOST = "http://localhost:11434"
_IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff")

# Modelos de Ollama que SÍ son de visión (gemma a secas NO es fiable para visión).
_OLLAMA_VISION = ("llava", "moondream", "bakllava", "llama3.2-vision",
                  "llama3-vision", "qwen2-vl", "qwen2.5-vl", "minicpm-v", "llava-llama3")

# ── BLIP (lazy, cargado una sola vez) ────────────────────────────────
_blip_lock = threading.Lock()
_blip = None  # (processor, model) | False si falló


def _get_blip():
    global _blip
    with _blip_lock:
        if _blip is None:
            try:
                from transformers import BlipProcessor, BlipForConditionalGeneration
                proc = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
                model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
                _blip = (proc, model)
            except Exception as e:
                print(f"[VISION-LOCAL] BLIP no disponible: {e}")
                _blip = False
        return _blip if _blip else None


def _blip_caption(image_path: str) -> str:
    pair = _get_blip()
    if not pair:
        return ""
    try:
        from PIL import Image
        proc, model = pair
        img = Image.open(image_path).convert("RGB")
        inputs = proc(img, return_tensors="pt")
        out = model.generate(**inputs, max_new_tokens=50)
        return proc.decode(out[0], skip_special_tokens=True).strip()
    except Exception as e:
        print(f"[VISION-LOCAL] Error BLIP: {e}")
        return ""


# ── OCR (lazy, best-effort) ──────────────────────────────────────────
_ocr_lock = threading.Lock()
_ocr_reader = None  # reader | False


def _get_ocr():
    global _ocr_reader
    with _ocr_lock:
        if _ocr_reader is None:
            try:
                import easyocr
                _ocr_reader = easyocr.Reader(["es", "en"], gpu=False, verbose=False)
            except Exception as e:
                print(f"[VISION-LOCAL] OCR no disponible: {e}")
                _ocr_reader = False
        return _ocr_reader if _ocr_reader else None


def _ocr_text(image_path: str) -> str:
    reader = _get_ocr()
    if not reader:
        return ""
    try:
        lines = reader.readtext(image_path, detail=0, paragraph=True)
        return " ".join(lines).strip()
    except Exception as e:
        print(f"[VISION-LOCAL] Error OCR: {e}")
        return ""


# ── Ollama vision (si hay modelo real instalado) ─────────────────────
def _ollama_vision_model() -> str | None:
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        for m in data.get("models", []):
            name = m.get("name", "")
            if any(v in name.lower() for v in _OLLAMA_VISION):
                return name
    except Exception:
        pass
    return None


def _ollama_vision(image_path: str, question: str) -> str:
    model = _ollama_vision_model()
    if not model:
        return ""
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        user_q = question.strip()
        prompt = (
            "Sos ONYX, un asistente. Mirá la imagen y respondé SIEMPRE en español, "
            "de forma clara y en primera persona. "
            + (f"Pregunta del usuario: {user_q}" if user_q
               else "Describí con detalle qué se ve en la imagen.")
        )
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        return (data.get("message", {}) or {}).get("content", "").strip()
    except Exception as e:
        print(f"[VISION-LOCAL] Error Ollama vision: {e}")
        return ""


# ── Búsqueda de la imagen por nombre ─────────────────────────────────
def _find_image_by_name(name: str) -> str:
    try:
        from core.file_utils import get_desktop_path, get_documents_path
        roots = [get_desktop_path(), get_documents_path(),
                 Path.home() / "Downloads", Path.home() / "Pictures"]
    except Exception:
        roots = [Path.home() / "Desktop", Path.home() / "Downloads", Path.home() / "Pictures"]
    name_l = name.lower()
    for root in roots:
        if not root or not Path(root).exists():
            continue
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                fl = f.lower()
                if fl.endswith(_IMG_EXTS) and (not name_l or name_l in fl):
                    return str(Path(dirpath) / f)
    return ""


def _compose_spanish(caption_en: str, ocr: str, question: str) -> str:
    """Usa el LLM local para redactar en español (best-effort)."""
    try:
        from core.llm_router import generate_local, local_available
        if not local_available():
            return ""
        facts = f"Descripción visual (en inglés): {caption_en or '(sin descripción)'}\n"
        facts += f"Texto detectado en la imagen: {ocr or '(sin texto)'}"
        q = question.strip() or "¿Qué se ve en la imagen?"
        prompt = (
            "Sos ONYX. Los siguientes datos provienen del análisis REAL de una imagen "
            "(visión por computadora + OCR). Son confiables. Respondé en español, breve, "
            "directo y en primera persona, describiendo lo que hay en la imagen. "
            "NO digas que no podés ver la imagen ni que necesitás verla.\n\n"
            f"Pregunta del usuario: {q}\n\n{facts}"
        )
        res = generate_local(prompt)
        return res.text if res and res.ok else ""
    except Exception:
        return ""


def local_image_analysis(parameters: dict, player=None) -> str:
    """Analiza una imagen de forma local. Args: path/file_path/image_path o name; question/prompt."""
    path = (parameters.get("path") or parameters.get("file_path")
            or parameters.get("image_path") or "").strip()
    name = (parameters.get("name") or "").strip()
    question = (parameters.get("question") or parameters.get("prompt")
                or parameters.get("value") or "").strip()

    if not path and name:
        path = _find_image_by_name(name)
    if not path and player is not None and getattr(player, "current_file", ""):
        cf = player.current_file
        if str(cf).lower().endswith(_IMG_EXTS):
            path = cf
    if not path:
        return ("Decime qué imagen analizar (nombre o ruta), Señor Cristian. "
                "Por ejemplo: 'analizá la imagen vacaciones'.")

    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"No encontré la imagen '{path}', Señor Cristian."

    # 1) Modelo de visión real en Ollama (mejor calidad si está disponible).
    via_ollama = _ollama_vision(path, question)
    if via_ollama:
        return f"[Visión local] {via_ollama}"

    # 2) BLIP + OCR.
    caption = _blip_caption(path)
    ocr = _ocr_text(path)
    if not caption and not ocr:
        return ("No pude analizar la imagen localmente. Para mejor calidad instalá un modelo "
                "de visión: 'ollama pull llava'. (BLIP requiere descargar su modelo la primera vez.)")

    # 3) Redacción en español con el LLM local (si está).
    spanish = _compose_spanish(caption, ocr, question)
    if spanish:
        return f"[Visión local] {spanish}"

    # 4) Respuesta directa sin LLM.
    partes = []
    if caption:
        partes.append(f"Descripción: {caption}")
    if ocr:
        partes.append(f"Texto en la imagen: {ocr}")
    return "[Visión local] " + " | ".join(partes)
