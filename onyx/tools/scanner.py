"""
tools/scanner.py — Auto-discovers and wraps ``actions/`` modules as ``Tool``.

Scans the existing ``actions/`` directory, imports each module,
inspects its main function signature, and creates a lightweight
``Tool`` wrapper that preserves the original calling convention.

Does **not** modify or move any file in ``actions/``.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
from pathlib import Path
from typing import Any, Callable

from onyx.tools.interfaces import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

# ── Name overrides for modules where the main function != module name ──
_NAME_MAP: dict[str, str] = {
    "desktop": "desktop_control",
    "weather_report": "weather_action",
}

# ── Modules to skip (private, infrastructure, or non-tools) ──
_SKIP_MODULES: set[str] = {
    "__init__",
    "_action_executor",
    "_browser_launch",
    "_chrome_launch",
    "_evaluator",
    "_planner",
    "_sandbox_exec",
    "_screen_analyzer",
    "_vision",
    "custom_stt",
    "custom_tts",
    "dictation_processor",
    "local_brain",
    "plugin_loader",
    "proactive_automation",
    "self_edit",
    "tool_creator",
    "train_onyx",
}


def _category_from_module(name: str) -> str:
    """Heuristic category assignment based on module name."""
    desktop = {
        "open_app", "close_app", "desktop", "computer_control",
        "computer_settings", "contextual_control", "system_controls",
        "windows_settings", "macros_control",
    }
    web = {
        "web_search", "browser_control", "web_navigation",
        "youtube_video", "flight_finder", "leer_articulo",
    }
    office = {
        "office_automation", "office_control", "document_creator",
        "document_manager",
    }
    communication = {
        "whatsapp", "send_message", "gmail_control", "social_media",
        "unified_communications",
    }
    media = {
        "spotify_control", "media_control", "rgb_control",
        "image_generation", "tiktok_analyzer",
    }
    development = {
        "code_helper", "dev_agent", "git_control", "codebase",
        "sandbox", "terminal_agent",
    }
    system = {
        "system_monitor", "scheduler", "reminder", "rules_engine",
        "smart_home", "smart_file_organizer",
    }
    vision = {
        "screen_vision", "local_vision", "local_image_analysis",
        "visual_click", "smart_tracker", "screen_agent",
        "advanced_vision", "vision_guardian",
    }
    ai = {
        "openrouter_agent", "evolve", "knowledge_base",
        "user_profile", "goals", "morning_brief",
    }

    for category, names in [
        ("desktop", desktop),
        ("web", web),
        ("office", office),
        ("communication", communication),
        ("media", media),
        ("development", development),
        ("system", system),
        ("vision", vision),
        ("ai", ai),
    ]:
        if name in names:
            return category
    return "general"


def _build_standard_wrapper(
    func: Callable,
    params_in_sig: bool = True,
    extra_kwargs: dict[str, Any] | None = None,
) -> Callable[[dict[str, Any]], ToolResult]:
    """Create an execute wrapper for a function with a ``(parameters, …)`` signature."""
    sig = inspect.signature(func)
    known = set(sig.parameters.keys())
    base: dict[str, Any] = {}

    if params_in_sig and "parameters" in known:
        base["parameters"] = None
    if "player" in known:
        base["player"] = None
    if "response" in known:
        base["response"] = None
    if "speak" in known:
        base["speak"] = None
    if extra_kwargs:
        base.update(extra_kwargs)

    def wrapper(params: dict[str, Any]) -> ToolResult:
        t0 = __import__("time").perf_counter()
        kwargs = dict(base)
        kwargs["parameters"] = params
        try:
            result = func(**kwargs)
            output = str(result) if result is not None else ""
            dur = (__import__("time").perf_counter() - t0) * 1000
            return ToolResult(success=True, output=output, duration_ms=dur)
        except Exception as e:
            dur = (__import__("time").perf_counter() - t0) * 1000
            return ToolResult(success=False, output="", error=str(e), duration_ms=dur)

    return wrapper


def _build_openrouter_wrapper(func: Callable) -> Callable[[dict[str, Any]], ToolResult]:
    """Special wrapper for ``openrouter_agent(query, model)``."""
    def wrapper(params: dict[str, Any]) -> ToolResult:
        t0 = __import__("time").perf_counter()
        try:
            result = func(
                query=params.get("query", ""),
                model=params.get("model", "google/gemini-2.5-flash"),
            )
            output = str(result) if result is not None else ""
            dur = (__import__("time").perf_counter() - t0) * 1000
            return ToolResult(success=True, output=output, duration_ms=dur)
        except Exception as e:
            dur = (__import__("time").perf_counter() - t0) * 1000
            return ToolResult(success=False, output="", error=str(e), duration_ms=dur)
    return wrapper


# ── Special-case wrappers for non-standard tool signatures ──
_SPECIAL_WRAPPERS: dict[str, Callable[[Callable], Callable[[dict], ToolResult]]] = {
    "openrouter_agent": _build_openrouter_wrapper,
}


def _tool_param_schema_from_func(func: Callable) -> dict[str, Any]:
    """Infer a minimal JSON Schema from the function's signature docstring."""
    sig = inspect.signature(func)
    # Prefer the 'parameters' dict annotation — most tools accept **anything
    # and validate internally.  We return a minimal open schema.
    params: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "description": "Parameters accepted by this tool.",
    }

    for pname, param in sig.parameters.items():
        if pname in ("self", "cls", "parameters", "player", "response", "speak", "session_memory"):
            continue
        # Infer type from annotation when possible
        ann = param.annotation
        if ann is inspect.Parameter.empty:
            js_type = "string"
        elif ann is int:
            js_type = "integer"
        elif ann is bool:
            js_type = "boolean"
        elif ann is float:
            js_type = "number"
        elif ann is list or getattr(ann, "__origin__", None) is list:
            js_type = "array"
        elif ann is dict or getattr(ann, "__origin__", None) is dict:
            js_type = "object"
        else:
            js_type = "string"

        required = param.default is inspect.Parameter.empty
        entry: dict[str, Any] = {"type": js_type}
        if not required:
            entry["default"] = param.default if param.default is not inspect.Parameter.empty else None
        params["properties"][pname] = entry
        if required:
            params.setdefault("required", []).append(pname)

    return params


class _WrappedTool(Tool):
    """Adapter that wraps an ``actions/`` function as a ``Tool``."""

    def __init__(
        self,
        spec: ToolSpec,
        execute_fn: Callable[[dict[str, Any]], ToolResult],
    ) -> None:
        self._spec = spec
        self._execute_fn = execute_fn

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    def execute(self, params: dict[str, Any]) -> ToolResult:
        return self._execute_fn(params)


def scan_actions(actions_dir: str | Path | None = None) -> list[Tool]:
    """Scan the ``actions/`` directory and return a list of ``Tool`` wrappers.

    Args:
        actions_dir: Path to the actions directory.  Defaults to
                     ``<project_root>/actions``.

    Returns:
        A list of ``Tool`` instances, one per discoverable action module.
    """
    if actions_dir is None:
        actions_dir = Path(__file__).resolve().parent.parent.parent / "actions"
    else:
        actions_dir = Path(actions_dir)

    if not actions_dir.is_dir():
        logger.warning("actions directory not found: %s", actions_dir)
        return []

    tools: list[Tool] = []
    seen: set[str] = set()

    for entry in sorted(actions_dir.iterdir()):
        if entry.suffix != ".py":
            continue
        mod_name = entry.stem
        if mod_name in _SKIP_MODULES:
            continue
        if mod_name.startswith("_"):
            continue

        try:
            tool = _build_tool_from_module(mod_name, actions_dir)
            if tool is not None and tool.spec.name not in seen:
                tools.append(tool)
                seen.add(tool.spec.name)
        except Exception as e:
            logger.debug("Skipping %s: %s", mod_name, e)

    logger.info("Scanner found %d tools in %s", len(tools), actions_dir)
    return tools


def _build_tool_from_module(mod_name: str, actions_dir: Path) -> Tool | None:
    """Build a single Tool wrapper from an actions module."""
    spec_name = _NAME_MAP.get(mod_name, mod_name)

    # Import the module from the actions package
    spec = importlib.util.spec_from_file_location(
        f"actions.{mod_name}",
        actions_dir / f"{mod_name}.py",
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Locate the main function
    func: Callable | None = getattr(module, spec_name, None)
    if func is None:
        logger.debug("Function %s not found in %s", spec_name, mod_name)
        return None
    if not callable(func):
        logger.debug("%s in %s is not callable", spec_name, mod_name)
        return None

    # Build the description from docstring
    raw_doc = (func.__doc__ or "").strip()
    description = raw_doc.split("\n")[0] if raw_doc else f"Tool: {mod_name}"
    description = description[:300]

    # Build parameter schema
    params_schema = _tool_param_schema_from_func(func)

    # Build the execution wrapper
    wrapper_builder = _SPECIAL_WRAPPERS.get(mod_name)
    if wrapper_builder is not None:
        execute_fn = wrapper_builder(func)
    else:
        execute_fn = _build_standard_wrapper(func)

    spec_obj = ToolSpec(
        name=spec_name,
        description=description,
        parameters=params_schema,
        category=_category_from_module(mod_name),
        timeout=60.0,
    )

    return _WrappedTool(spec_obj, execute_fn)
