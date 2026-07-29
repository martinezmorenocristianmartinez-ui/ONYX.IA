"""
_planner.py — Multi-step planning engine for ONYX.
Decomposes complex tasks into sequential steps with checkpointing.
Plans persist to disk and can resume after interruptions.
"""
import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
PLANS_PATH = MEMORY_DIR / "planner_state.json"

_MAX_STEPS_PER_PLAN = 100
_MAX_ACTIVE_PLANS = 20


def _now_iso():
    return datetime.now().isoformat()


class PlanStep:
    def __init__(self, description: str, tool_name: str = "",
                 parameters: dict = None, depends_on: list = None):
        self.id = str(uuid.uuid4())[:8]
        self.description = description
        self.tool_name = tool_name
        self.parameters = parameters or {}
        self.depends_on = depends_on or []
        self.status = "pending"
        self.result = ""
        self.score = 0
        self.error = ""
        self.executed_at = ""
        self.duration_ms = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "status": self.status,
            "result": self.result[:10000],
            "score": self.score,
            "error": self.error[:5000],
            "executed_at": self.executed_at,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanStep":
        step = cls(d.get("description", ""), d.get("tool_name", ""),
                    d.get("parameters", {}), d.get("depends_on", []))
        step.id = d.get("id", step.id)
        step.status = d.get("status", "pending")
        step.result = d.get("result", "")
        step.score = d.get("score", 0)
        step.error = d.get("error", "")
        step.executed_at = d.get("executed_at", "")
        step.duration_ms = d.get("duration_ms", 0)
        return step


class Plan:
    def __init__(self, goal: str):
        self.id = str(uuid.uuid4())[:8]
        self.goal = goal
        self.steps: list[PlanStep] = []
        self.status = "created"
        self.current_step_index = 0
        self.created_at = _now_iso()
        self.updated_at = _now_iso()
        self.completed_at = ""
        self.error = ""

    def add_step(self, description: str, tool_name: str = "",
                 parameters: dict = None, depends_on: list = None) -> PlanStep:
        if len(self.steps) >= _MAX_STEPS_PER_PLAN:
            raise ValueError(f"Max {_MAX_STEPS_PER_PLAN} steps per plan")
        step = PlanStep(description, tool_name, parameters, depends_on)
        self.steps.append(step)
        self.updated_at = _now_iso()
        return step

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "current_step_index": self.current_step_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        plan = cls(d.get("goal", ""))
        plan.id = d.get("id", plan.id)
        plan.status = d.get("status", "created")
        plan.current_step_index = d.get("current_step_index", 0)
        plan.created_at = d.get("created_at", plan.created_at)
        plan.updated_at = d.get("updated_at", plan.updated_at)
        plan.completed_at = d.get("completed_at", "")
        plan.error = d.get("error", "")
        plan.steps = [PlanStep.from_dict(s) for s in d.get("steps", [])]
        return plan

    def get_current_step(self) -> PlanStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def next_step(self) -> PlanStep | None:
        self.current_step_index += 1
        return self.get_current_step()

    def is_complete(self) -> bool:
        return all(s.status == "completed" for s in self.steps)

    def progress(self) -> str:
        total = len(self.steps)
        done = sum(1 for s in self.steps if s.status == "completed")
        failed = sum(1 for s in self.steps if s.status == "failed")
        return f"Paso {done}/{total} completados ({failed} fallos)"

    def summary(self) -> str:
        lines = [f"Plan: {self.goal}"]
        lines.append(f"Estado: {self.status} | {self.progress()}")
        for i, step in enumerate(self.steps):
            icon = {"completed": "✓", "failed": "✗", "running": "►", "pending": "○"}.get(step.status, "?")
            lines.append(f"  {i + 1}. {icon} {step.description}")
            if step.status == "completed":
                lines[-1] += f" ({step.score}/10)"
            elif step.error:
                lines[-1] += f" error: {step.error[:80]}"
        return "\n".join(lines)


class Planner:
    _lock = threading.Lock()

    def __init__(self):
        self._active_plans: dict[str, Plan] = {}
        self._load_active()

    def _load_active(self):
        if not PLANS_PATH.exists():
            return
        try:
            data = json.loads(PLANS_PATH.read_text(encoding="utf-8"))
            for pdata in data.get("active_plans", []):
                plan = Plan.from_dict(pdata)
                if plan.status in ("created", "running"):
                    self._active_plans[plan.id] = plan
        except Exception:
            pass

    def _save_active(self):
        PLANS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active_plans": [p.to_dict() for p in self._active_plans.values()],
            "saved_at": _now_iso(),
        }
        PLANS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def create_plan(self, goal: str, steps: list[dict] = None) -> Plan:
        with self._lock:
            if len(self._active_plans) >= _MAX_ACTIVE_PLANS:
                oldest = min(self._active_plans.keys(),
                             key=lambda k: self._active_plans[k].updated_at)
                del self._active_plans[oldest]
            plan = Plan(goal)
            if steps:
                for s in steps:
                    plan.add_step(
                        description=s.get("description", ""),
                        tool_name=s.get("tool_name", ""),
                        parameters=s.get("parameters", {}),
                        depends_on=s.get("depends_on", []),
                    )
            self._active_plans[plan.id] = plan
            self._save_active()
            return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._active_plans.get(plan_id)

    def get_active_plans(self) -> dict[str, Plan]:
        return dict(self._active_plans)

    def mark_step_running(self, plan_id: str) -> PlanStep | None:
        with self._lock:
            plan = self._active_plans.get(plan_id)
            if not plan:
                return None
            step = plan.get_current_step()
            if step and step.status == "pending":
                step.status = "running"
                plan.status = "running"
                plan.updated_at = _now_iso()
                self._save_active()
            return step

    def mark_step_completed(self, plan_id: str, result: str = "",
                            score: int = 5, duration_ms: float = 0) -> PlanStep | None:
        with self._lock:
            plan = self._active_plans.get(plan_id)
            if not plan:
                return None
            step = plan.get_current_step()
            if step:
                step.status = "completed"
                step.result = result[:2000]
                step.score = score
                step.duration_ms = duration_ms
                step.executed_at = _now_iso()
                plan.updated_at = _now_iso()
                if plan.is_complete():
                    plan.status = "completed"
                    plan.completed_at = _now_iso()
                    self._archive_plan(plan_id)
                else:
                    plan.next_step()
                self._save_active()
            return step

    def mark_step_failed(self, plan_id: str, error: str = "") -> PlanStep | None:
        with self._lock:
            plan = self._active_plans.get(plan_id)
            if not plan:
                return None
            step = plan.get_current_step()
            if step:
                step.status = "failed"
                step.error = error[:500]
                step.executed_at = _now_iso()
                plan.updated_at = _now_iso()
                plan.error = error[:500]
                self._save_active()
            return step

    def cancel_plan(self, plan_id: str) -> bool:
        with self._lock:
            plan = self._active_plans.get(plan_id)
            if not plan:
                return False
            plan.status = "cancelled"
            plan.updated_at = _now_iso()
            self._archive_plan(plan_id)
            self._save_active()
            return True

    def _archive_plan(self, plan_id: str):
        self._active_plans.pop(plan_id, None)

    def resume_plan(self, plan_id: str) -> Plan | None:
        plan = self._active_plans.get(plan_id)
        if not plan:
            return None
        # Find first pending or running step
        for i, step in enumerate(plan.steps):
            if step.status in ("pending", "running"):
                plan.current_step_index = i
                if step.status == "running":
                    step.status = "pending"
                plan.status = "running"
                plan.updated_at = _now_iso()
                self._save_active()
                return plan
        return plan

    def decompose_task(self, goal: str, call_llm_func) -> Plan | None:
        """Use LLM to decompose a goal into steps automatically."""
        prompt = (
            f"Descompón la siguiente tarea en pasos secuenciales que ONYX pueda ejecutar.\n"
            f"Tarea: '{goal}'\n\n"
            "Para cada paso, indica:\n"
            "- description: qué hacer (texto claro)\n"
            "- tool_name: qué herramienta de ONYX usar (o vacío si es explicativo)\n"
            "- parameters: dict de parámetros para la herramienta (o vacío)\n\n"
            "Devuelve SOLO un JSON array de pasos, nada más. Ejemplo:\n"
            '[{"description": "Buscar clima en Buenos Aires", "tool_name": "weather_report", '
            '"parameters": {"city": "Buenos Aires"}}]'
        )
        try:
            response = call_llm_func(prompt)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            steps_data = json.loads(response)
            if isinstance(steps_data, list) and len(steps_data) > 0:
                return self.create_plan(goal, steps_data)
        except Exception:
            pass
        return None


_planner = None


def get_planner() -> Planner:
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner
