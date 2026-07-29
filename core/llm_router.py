"""
llm_router.py - Enrutador de modelos de lenguaje para ONYX.

Objetivo: reducir la dependencia de APIs externas (Gemini/OpenRouter)
proveyendo una capa unificada de generacion de texto con FALLBACK AUTOMATICO:

    nube (si hay API y conexion)  ->  local (Ollama, 100% offline)

Asi, si no hay internet, se acaba la cuota o falla la API, ONYX sigue
respondiendo con el cerebro local en lugar de cortarse.

Diseno:
- Sin dependencias pesadas: usa solo la stdlib (urllib) para hablar con Ollama.
- No importa main.py ni PyQt6, por lo que es testeable de forma aislada.
- El llamado a la nube se inyecta como callable (`cloud_fn`) para no acoplar
  este modulo a un proveedor concreto.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass

OLLAMA_HOST = "http://localhost:11434"

# Modelos locales preferidos, de menor a mayor costo. El primero instalado gana.
_PREFERRED_LOCAL_MODELS = (
    "qwen2.5:3b", "qwen2.5:1.5b", "llama3.2:3b", "llama3.2:1b",
    "phi3:mini", "gemma2:2b", "qwen3.5:2b",
)


@dataclass
class LLMResult:
    text: str
    source: str          # "cloud" | "local" | "none"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.error is None


def local_available(host: str = OLLAMA_HOST, timeout: float = 2.0) -> bool:
    """True si hay un servidor Ollama escuchando localmente."""
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_local_models(host: str = OLLAMA_HOST, timeout: float = 3.0) -> list[str]:
    """Lista los modelos disponibles en Ollama (vacio si no hay servidor)."""
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def pick_local_model(host: str = OLLAMA_HOST) -> str | None:
    """Elige el mejor modelo local instalado segun la lista de preferencia.

    Si no hay coincidencia exacta pero hay modelos instalados, devuelve el
    primero. Devuelve None si no hay ninguno.
    """
    installed = list_local_models(host)
    if not installed:
        return None
    installed_set = set(installed)
    for pref in _PREFERRED_LOCAL_MODELS:
        if pref in installed_set:
            return pref
    # Coincidencia por prefijo (ej: 'qwen2.5:3b-instruct').
    for pref in _PREFERRED_LOCAL_MODELS:
        base = pref.split(":")[0]
        for inst in installed:
            if inst.startswith(base):
                return inst
    return installed[0]


def generate_local(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    host: str = OLLAMA_HOST,
    timeout: float = 120.0,
) -> LLMResult:
    """Genera texto con el cerebro local (Ollama). No requiere internet."""
    if model is None:
        model = pick_local_model(host)
    if not model:
        return LLMResult(text="", source="none",
                         error="Ollama no esta disponible o no hay modelos instalados.")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 8192},
    }
    try:
        req = urllib.request.Request(
            f"{host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        text = (data.get("message", {}) or {}).get("content", "") or ""
        return LLMResult(text=text.strip(), source="local")
    except Exception as e:
        return LLMResult(text="", source="none", error=f"Error con Ollama: {e}")


def generate(
    prompt: str,
    system: str | None = None,
    cloud_fn=None,
    prefer_local: bool = False,
    local_model: str | None = None,
    host: str = OLLAMA_HOST,
) -> LLMResult:
    """Genera texto con fallback automatico nube -> local.

    Args:
        prompt: texto del usuario.
        system: instruccion de sistema opcional.
        cloud_fn: callable(prompt, system) -> str. Si es None o falla, se usa
            el cerebro local. Se inyecta para no acoplar a un proveedor.
        prefer_local: si True, intenta primero el modelo local (modo offline).
        local_model: forzar un modelo local concreto.
        host: host de Ollama.

    Returns:
        LLMResult con el texto y la fuente usada ("cloud" | "local" | "none").
    """
    # Modo offline explicito o sin proveedor de nube.
    if prefer_local or cloud_fn is None:
        local = generate_local(prompt, system=system, model=local_model, host=host)
        if local.ok:
            return local
        if cloud_fn is None:
            return local  # nada mas que intentar

    # Intentar nube primero.
    if cloud_fn is not None:
        try:
            text = cloud_fn(prompt, system)
            if text and str(text).strip():
                return LLMResult(text=str(text).strip(), source="cloud")
        except Exception as e:
            cloud_err = str(e)
        else:
            cloud_err = "La nube no devolvio texto."

        # Fallback a local.
        local = generate_local(prompt, system=system, model=local_model, host=host)
        if local.ok:
            return local
        return LLMResult(
            text="",
            source="none",
            error=f"Nube fallo ({cloud_err}) y local no disponible ({local.error}).",
        )

    return LLMResult(text="", source="none", error="Sin proveedor de nube ni local.")
