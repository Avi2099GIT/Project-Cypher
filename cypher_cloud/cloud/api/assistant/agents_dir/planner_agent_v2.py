from __future__ import annotations

from typing import List, Dict, Any, Set
from cloud.api.assistant.agents_dir.plan_model import (
    ExecutionPlan,
    PlanStep,
    PlanRisk,
)


class PlannerV2:
    """
    Phase-4 planner with:
      - multi-candidate plan generation
      - context-aware scoring
      - failure-aware tool biasing
      - explainability engine

    STRICT RULE:
    ✅ Planner never invents intent.
    ✅ Planner only routes what EntityAgent decides.
    ✅ No silent overrides.
    """

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_candidates(
        self,
        intents: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[ExecutionPlan]:

        raw_msg = (context.get("message") or "").lower()
        plans: List[ExecutionPlan] = []

        for intent in intents:
            t = (intent.get("type") or "").lower()

            # --------------------
            # CALENDAR
            # --------------------
            if t == "calendar":
                primary = self._calendar_primary(intent)
                fallback = self._calendar_fallback(intent)
                primary.fallbacks.append(fallback)
                plans.append(primary)

            # --------------------
            # TASKS
            # --------------------
            elif t == "task":
                primary = self._task_primary(intent)
                fallback = self._task_fallback(intent)
                primary.fallbacks.append(fallback)
                plans.append(primary)

            # --------------------
            # OS / Web / Time / Weather / Notes / System
            # --------------------
            elif t in ("os", "os_control", "web", "web_search", "time", "weather", "system_info", "notes"):
                plans.append(self._simple_tool(intent))

            # --------------------
            # CHAT ONLY
            # --------------------
            elif t == "chat":
                plans.append(
                    ExecutionPlan(
                        steps=[],
                        reason="Pure conversational request; no tools required.",
                        risk=PlanRisk.LOW,
                        confidence=0.95,
                        estimated_cost=0.05,
                    )
                )

            # --------------------
            # UNKNOWN → CHAT FALLBACK
            # --------------------
            else:
                plans.append(
                    ExecutionPlan(
                        steps=[],
                        reason=f"Unknown intent type '{t}'. Falling back to chat.",
                        risk=PlanRisk.MEDIUM,
                        confidence=0.4,
                        estimated_cost=0.1,
                    )
                )

        return plans

    # ---------------------------------------------------------
    # PICK BEST PLAN (EXPLAINABLE)
    # ---------------------------------------------------------

    def pick_best(
        self,
        plans: List[ExecutionPlan],
        context: Dict[str, Any],
    ) -> ExecutionPlan:

        ranked = self.evaluate_plans(plans, context)
        best = ranked[0]
        others = ranked[1:]

        # ---------- rejected alternatives ----------
        best.rejected = [
            {
                "reason": p.reason,
                "confidence": p.confidence,
                "risk": getattr(p.risk, "value", str(p.risk)),
                "tools": [s.tool for s in p.steps],
                "score": getattr(p, "score_breakdown", {}),
            }
            for p in others
        ]

        # ---------- explanation ----------
        best.explanation = {
            "reason": best.reason,
            "confidence": best.confidence,
            "risk": getattr(best.risk, "value", str(best.risk)),
            "tools": [s.tool for s in best.steps],
            "why": "Chosen by lowest risk + failure-awareness + highest confidence",
        }

        # ---------- debug visibility ----------
        context.setdefault("plan_debug", {})
        context["plan_debug"]["ranked_plans"] = [
            {
                "reason": p.reason,
                "risk": getattr(p.risk, "value", str(p.risk)),
                "confidence": p.confidence,
                "estimated_cost": p.estimated_cost,
                "steps": [s.tool for s in p.steps],
                "score": getattr(p, "score_breakdown", {}),
            }
            for p in ranked
        ]

        return best

    # ---------------------------------------------------------
    # FAILURE-AWARE SCORING ENGINE
    # ---------------------------------------------------------

    def evaluate_plans(
        self,
        plans: List[ExecutionPlan],
        context: Dict[str, Any],
    ) -> List[ExecutionPlan]:

        if not plans:
            return []

        decision = context.get("decision") or {}
        mode = (decision.get("mode") or "").lower()
        force_tools = mode in ("force_tools", "tools")

        reasoning = context.get("reasoning") or {}
        try:
            global_conf = float(reasoning.get("confidence") or 0.5)
        except Exception:
            global_conf = 0.5

        # -------------------------
        # Gather failed tools
        # -------------------------
        failed_tools: Set[str] = set()

        memory = context.get("memory") or {}
        episodes = memory.get("recent_episodes") or []

        for ep in episodes:
            meta = ep.get("meta") or {}
            verification = meta.get("verification") or {}
            for name in verification.get("failed_tools") or []:
                if isinstance(name, str):
                    failed_tools.add(name)

        # -------------------------
        # SCORING FUNCTION
        # -------------------------

        def score(p: ExecutionPlan):

            risk_weight = {
                PlanRisk.LOW: 0,
                PlanRisk.MEDIUM: 5,
                PlanRisk.HIGH: 15,
            }.get(p.risk, 5)

            tool_names = {step.tool for step in p.steps}
            failed_overlap = tool_names.intersection(failed_tools)
            failure_penalty = len(failed_overlap) * 25

            no_tools_penalty = 0
            if force_tools and not p.steps:
                no_tools_penalty = 100

            effective_conf = (p.confidence or 0.0) * global_conf
            step_count = len(p.steps)

            # ---------- explainability ----------
            p.score_breakdown = {
                "risk_penalty": risk_weight,
                "failure_penalty": failure_penalty,
                "no_tool_penalty": no_tools_penalty,
                "effective_confidence": effective_conf,
                "steps": step_count,
                "estimated_cost": p.estimated_cost,
            }

            return (
                no_tools_penalty + failure_penalty + risk_weight,
                -effective_conf,
                p.estimated_cost,
                step_count,
            )

        ranked = sorted(plans, key=score)
        return ranked

    # ---------------------------------------------------------
    # CALENDAR STRATEGIES
    # ---------------------------------------------------------

    def _calendar_primary(self, intent):

        params = intent.get("params", {})
        action = (params.get("action") or "").lower().strip()

        if not action:
            raise ValueError("Calendar intent missing 'action'.")

        if action == "create":
            return self._calendar_create_plan(params)
        if action == "list":
            return self._calendar_list_plan(params)
        if action == "delete":
            return self._calendar_delete_plan(params)
        if action == "update":
            return self._calendar_update_plan(params)

        raise ValueError(f"Unknown calendar action: {action}")

    def _calendar_fallback(self, intent: Dict[str, Any]) -> ExecutionPlan:
        return ExecutionPlan(
            steps=[],
            reason="Calendar request failed. Fallback to explanation.",
            risk=PlanRisk.LOW,
            confidence=0.4,
            estimated_cost=0.1,
        )

    def _calendar_create_plan(self, params):
        return ExecutionPlan(
            steps=[PlanStep(tool="calendar_google", args=params, expected="Event created")],
            reason="Create calendar event",
            confidence=0.95,
            risk=PlanRisk.LOW,
            estimated_cost=1.0,
            fallbacks=[],
        )

    def _calendar_list_plan(self, params):
        return ExecutionPlan(
            steps=[PlanStep(tool="calendar_google", args=params, expected="Events listed")],
            reason="List calendar events",
            confidence=0.9,
            risk=PlanRisk.LOW,
            estimated_cost=0.8,
            fallbacks=[],
        )

    def _calendar_delete_plan(self, params):
        return ExecutionPlan(
            steps=[PlanStep(tool="calendar_google", args=params, expected="Events deleted")],
            reason="Delete calendar events",
            confidence=0.9,
            risk=PlanRisk.MEDIUM,
            estimated_cost=1.2,
            fallbacks=[],
        )

    def _calendar_update_plan(self, params):
        return ExecutionPlan(
            steps=[PlanStep(tool="calendar_google", args=params, expected="Event updated")],
            reason="Update calendar event",
            confidence=0.7,
            risk=PlanRisk.MEDIUM,
            estimated_cost=1.3,
            fallbacks=[],
        )

    # ---------------------------------------------------------
    # TASK STRATEGIES
    # ---------------------------------------------------------

    def _task_primary(self, intent: Dict[str, Any]) -> ExecutionPlan:
        args = intent.get("params") or intent.get("args") or {}
        return ExecutionPlan(
            steps=[PlanStep(tool="google_tasks", args=args, expected="Task created / updated")],
            reason="Google Tasks execution",
            confidence=0.85,
            risk=PlanRisk.MEDIUM,
            estimated_cost=1.1,
        )

    def _task_fallback(self, intent: Dict[str, Any]) -> ExecutionPlan:
        return ExecutionPlan(
            steps=[],
            reason="Fallback instructions for tasks",
            risk=PlanRisk.LOW,
            confidence=0.4,
            estimated_cost=0.1,
        )

    # ---------------------------------------------------------
    # GENERIC TOOL ROUTING
    # ---------------------------------------------------------

    def _simple_tool(self, intent: Dict[str, Any]) -> ExecutionPlan:

        itype = (intent.get("type") or "").lower()
        args = intent.get("params") or intent.get("args") or {}

        # Exact tool_registry alignment
        if itype in ("os", "os_control"):
            tool_name = "os_control"
        elif itype in ("web", "search", "web_search"):
            tool_name = "web_search"
        elif itype == "time":
            tool_name = "time"
        elif itype == "weather":
            tool_name = "weather"
        elif itype == "system_info":
            tool_name = "system_info"
        elif itype == "notes":
            tool_name = "notes"
        else:
            tool_name = intent.get("tool") or itype or "unknown_tool"

        return ExecutionPlan(
            steps=[PlanStep(tool=tool_name, args=args, expected="Tool executed")],
            reason=f"Execute {tool_name}",
            risk=PlanRisk.LOW,
            confidence=0.9,
            estimated_cost=0.3,
        )
