# cloud/api/assistant/agents_dir/planner_agent.py
from __future__ import annotations
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class PlannerAgentH:
    """
    PlannerAgentH

    Routes intents to:
      • calendar_google (PRIMARY)
      • tasks (google tasks later)
      • notes
      • OS
      • web
      • time/weather
    """

    def plan(self, intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not intents:
            return []

        steps: List[Dict[str, Any]] = []

        ordered = sorted(intents, key=lambda i: i.get("priority", 5))

        for intent in ordered:
            try:
                step = self._intent_to_step(intent)
                if step:
                    steps.append(step)
            except Exception as e:
                logger.exception("PlannerAgentH: Failed to plan intent %s", intent)

        return steps

    # ----------------------------------------------------

    def _intent_to_step(self, intent: Dict[str, Any]) -> Dict[str, Any] | None:
        itype = (intent.get("type") or "").lower()
        params = intent.get("params") or {}

        # ---- TIME ---------------------------------------
        if itype == "time":
            return {"tool": "time", "args": params}

        # ---- WEATHER -----------------------------------
        if itype == "weather":
            return {"tool": "weather", "args": params}

        # ---- WEB SEARCH --------------------------------
        if itype in ("search", "web_search", "browse"):
            return {"tool": "web_search", "args": params}

        # ---- OS CONTROL --------------------------------
        if itype == "os_control":
            return {"tool": "os_control", "args": params}

        # ---- NOTES -------------------------------------
        if itype == "notes":
            return {"tool": "notes", "args": params}

        # ---- TASKS -------------------------------------
        if itype == "tasks":
            return {
                "tool": "google_tasks",
                "args": params,
            }

        # ---- GOOGLE CALENDAR (PRIMARY) -----------------
        if itype == "calendar":
            return {
                "tool": "calendar_google",
                "args": params,
            }
        
         # ---- GOOGLE TASKS
        if itype == "google_tasks":
            return {
                "tool": "google_tasks",
                "args": params,
            }


        # ---- CHAT --------------------------------------
        if itype == "chat":
            return None

        logger.warning("PlannerAgentH: Unrecognized intent type '%s'", itype)
        return None
