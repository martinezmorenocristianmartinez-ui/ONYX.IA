"""Local Brain — Cerebro local de ONYX usando Ollama (100% offline, sin API)."""
from __future__ import annotations

import json
import time
import threading
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OLLAMA_HOST = "http://localhost:11434"

# Lazy import to avoid circular dependency
_summarizer = None
_summarizer_lock = threading.Lock()

def _get_summarizer():
    global _summarizer
    with _summarizer_lock:
        if _summarizer is None:
            try:
                from memory.context_summarizer import get_summarizer
                _summarizer = get_summarizer()
            except Exception:
                _summarizer = False
        return _summarizer if _summarizer else None


class LocalBrain:
    def __init__(self, model: str = "qwen3.5:2b", host: str = OLLAMA_HOST):
        self.model = model
        self.host = host
        self.history: list[dict] = []
        self.system_prompt = self._load_system_prompt()
        self.tools: list[dict] = []

    def _load_system_prompt(self) -> str:
        prompt_file = BASE_DIR / "core" / "prompt.txt"
        if prompt_file.exists():
            full = prompt_file.read_text(encoding="utf-8")
            return full[:5000]  # Keep it short for local models
        return "Eres ONYX, asistente de IA para el Señor Cristian. Respondé en español, frases cortas. Tratá al usuario de 'Señor Cristian'."

    def set_tools(self, tool_declarations: list[dict]):
        self.tools = tool_declarations

    def _ollama_chat(self, messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
            }
        }
        if tools:
            payload["tools"] = [self._to_ollama_tool(t) for t in tools]

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())

    def _to_ollama_tool(self, tool_decl: dict) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool_decl["name"],
                "description": tool_decl.get("description", ""),
                "parameters": tool_decl.get("parameters", {})
            }
        }

    def _extract_tool_calls(self, message: dict) -> list[dict]:
        tools = message.get("tool_calls", [])
        results = []
        for tc in tools:
            fn = tc.get("function", {})
            results.append({
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", {})
            })
        return results

    def chat(self, user_text: str, tool_dispatch_fn=None) -> str:
        self.history.append({"role": "user", "content": user_text})
        summarizer = _get_summarizer()
        if summarizer:
            summarizer.add_turn("user", user_text)

        # Build system prompt with context summarizer compressed history
        sys_content = self.system_prompt
        if summarizer:
            try:
                ctx = summarizer.format_for_prompt(max_summaries=5, max_recent=5)
                if ctx:
                    sys_content = ctx + "\n\n" + sys_content
            except Exception:
                pass

        messages = [{"role": "system", "content": sys_content}]
        for h in self.history[-50:]:
            messages.append(h)

        max_iterations = 10
        for iteration in range(max_iterations):
            data = self._ollama_chat(messages, tools=self.tools if tool_dispatch_fn else None)
            msg = data.get("message", {})
            content = msg.get("content", "")
            tool_calls = self._extract_tool_calls(msg)

            if tool_calls and tool_dispatch_fn:
                self.history.append({"role": "assistant", "content": content, "tool_calls": msg.get("tool_calls")})

                for tc in tool_calls:
                    name = tc["name"]
                    args = tc["arguments"]
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    try:
                        result = tool_dispatch_fn(name, args)
                    except Exception as e:
                        result = f"Error: {e}"

                    self.history.append({
                        "role": "tool",
                        "name": name,
                        "content": str(result)[:3000]
                    })
                    messages.append({"role": "tool", "name": name, "content": str(result)[:3000]})
            else:
                self.history.append({"role": "assistant", "content": content})
                if summarizer:
                    summarizer.add_turn("assistant", content)
                return content

        return "No pude completar la tarea."

    def reset_history(self):
        self.history = []

    def set_model(self, model: str):
        self.model = model


_brain: LocalBrain | None = None
_brain_lock = threading.Lock()


def get_brain(model: str = "qwen3.5:2b") -> LocalBrain:
    global _brain
    with _brain_lock:
        if _brain is None:
            _brain = LocalBrain(model=model)
        return _brain


def local_brain(parameters: dict, player=None) -> str:
    action = str(parameters.get("action", "chat") or "chat").lower()
    text = parameters.get("text") or parameters.get("message") or ""
    model = parameters.get("model")

    # Verificar disponibilidad de Ollama y autoseleccionar modelo si hace falta.
    try:
        from core.llm_router import local_available, pick_local_model, list_local_models
    except Exception:
        local_available = pick_local_model = list_local_models = None

    if action == "models":
        if list_local_models is None:
            return "Router local no disponible."
        models = list_local_models()
        if not models:
            return ("No hay modelos locales. Instalá Ollama (https://ollama.com) y "
                    "descargá uno con: ollama pull qwen2.5:3b")
        return f"Modelos locales disponibles: {', '.join(models)}"

    # Para chat/reset/set_model necesitamos Ollama corriendo.
    if local_available is not None and not local_available():
        return ("El cerebro local (Ollama) no está corriendo. Iniciá Ollama y "
                "descargá un modelo con: ollama pull qwen2.5:3b")

    if not model and pick_local_model is not None:
        model = pick_local_model()
    if not model:
        model = "qwen2.5:3b"

    brain = get_brain(model)
    brain.set_model(model)

    if action == "chat":
        if not text:
            return "Decime algo, Señor Cristian."
        try:
            return brain.chat(text)
        except Exception as e:
            return f"Error en el cerebro local: {e}"

    if action == "reset":
        brain.reset_history()
        return "Memoria local reiniciada."

    if action == "set_model":
        brain.set_model(model)
        return f"Modelo cambiado a {model}."

    return "Usá: chat, reset, set_model, models."
