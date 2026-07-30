from onyx.brain.interfaces import BrainResult

_TOOL_DECLARATIONS = None
_LOCAL_TOOL_NAMES = None


def _set_tool_registry(declarations: list[dict], local_names: frozenset):
    global _TOOL_DECLARATIONS, _LOCAL_TOOL_NAMES
    _TOOL_DECLARATIONS = declarations
    _LOCAL_TOOL_NAMES = local_names


class Processor:

    def process(self, text: str, tool_dispatch_fn=None) -> BrainResult:
        from core.llm_router import local_available, pick_local_model
        from core.local_intents import detect_intent

        intent = detect_intent(text)
        if intent is not None:
            msg = tool_dispatch_fn(intent["tool"], intent["args"]) if tool_dispatch_fn else "Tool not available"
            return BrainResult(text=msg, speak=True, state="LISTENING")

        if not local_available():
            msg = (
                "El servicio en la nube no está disponible y no detecto Ollama "
                "corriendo localmente. Iniciá Ollama (ollama serve) y descargá un "
                "modelo con 'ollama pull qwen2.5:3b' para que pueda responderte sin internet, "
                "Señor Cristian."
            )
            return BrainResult(text=msg, speak=True, state="LISTENING")

        from actions.local_brain import get_brain

        model = pick_local_model() or "qwen2.5:3b"
        brain = get_brain(model)
        brain.set_model(model)
        if _TOOL_DECLARATIONS and _LOCAL_TOOL_NAMES:
            local_decls = [t for t in _TOOL_DECLARATIONS if t.get("name") in _LOCAL_TOOL_NAMES]
            brain.set_tools(local_decls)
        msg = brain.chat(text, tool_dispatch_fn=tool_dispatch_fn)
        if not msg:
            msg = "Listo, Señor Cristian."
        return BrainResult(text=msg, speak=True, state="LISTENING")
