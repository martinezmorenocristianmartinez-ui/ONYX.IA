"""Lógica de fallback del router de LLM (nube -> local)."""
from core import llm_router as r


def _cloud_ok(prompt, system):
    return "respuesta de la nube"


def _cloud_falla(prompt, system):
    raise RuntimeError("quota agotada")


def _cloud_vacio(prompt, system):
    return ""


def test_usa_nube_cuando_funciona():
    res = r.generate("hola", cloud_fn=_cloud_ok)
    assert res.source == "cloud"
    assert res.text == "respuesta de la nube"
    assert res.ok


def test_fallback_a_local_cuando_nube_falla(monkeypatch):
    # Simular cerebro local disponible sin depender de Ollama real.
    monkeypatch.setattr(
        r, "generate_local",
        lambda *a, **k: r.LLMResult(text="respuesta local", source="local"),
    )
    res = r.generate("hola", cloud_fn=_cloud_falla)
    assert res.source == "local"
    assert res.text == "respuesta local"


def test_sin_nube_ni_local_devuelve_none(monkeypatch):
    monkeypatch.setattr(
        r, "generate_local",
        lambda *a, **k: r.LLMResult(text="", source="none", error="sin Ollama"),
    )
    res = r.generate("hola", cloud_fn=None)
    assert res.source == "none"
    assert not res.ok


def test_prefer_local_intenta_local_primero(monkeypatch):
    llamado = {"local": False}

    def fake_local(*a, **k):
        llamado["local"] = True
        return r.LLMResult(text="local primero", source="local")

    monkeypatch.setattr(r, "generate_local", fake_local)
    res = r.generate("hola", cloud_fn=_cloud_ok, prefer_local=True)
    assert llamado["local"] is True
    assert res.source == "local"


def test_nube_vacia_hace_fallback(monkeypatch):
    monkeypatch.setattr(
        r, "generate_local",
        lambda *a, **k: r.LLMResult(text="rescate local", source="local"),
    )
    res = r.generate("hola", cloud_fn=_cloud_vacio)
    assert res.source == "local"


def test_pick_local_model_sin_ollama(monkeypatch):
    monkeypatch.setattr(r, "list_local_models", lambda *a, **k: [])
    assert r.pick_local_model() is None


def test_pick_local_model_elige_preferido(monkeypatch):
    monkeypatch.setattr(
        r, "list_local_models",
        lambda *a, **k: ["llama3.2:1b", "qwen2.5:3b", "mistral:7b"],
    )
    # qwen2.5:3b es el primero en la lista de preferencia.
    assert r.pick_local_model() == "qwen2.5:3b"
