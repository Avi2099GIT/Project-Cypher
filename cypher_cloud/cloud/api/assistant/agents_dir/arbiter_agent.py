from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ArbiterAgent:
    """
    Arbitration engine for Cypher.

    Combines:
      - safety outcome
      - reasoning outcome
    to produce a final high-level decision.

    Output schema:

    {
      "mode": "safety_block" | "clarify_only" | "chat_only" | "tools" | "auto",
      "use_tools": bool,
      "explanation": str,
      "blocked": bool
    }
    """

    async def run(
        self,
        message: str,
        safe_intents: List[Dict[str, Any]],
        blocked_intents: List[Dict[str, Any]],
        reasoning: Dict[str, Any],
    ) -> Dict[str, Any]:
        # 1) Safety has absolute priority
        if not safe_intents and blocked_intents:
            reasons = [b.get("reason") or "unsafe" for b in blocked_intents]
            explanation = "Request blocked by safety policy: " + "; ".join(reasons)
            return {
                "mode": "safety_block",
                "use_tools": False,
                "explanation": explanation,
                "blocked": True,
            }

        mode = reasoning.get("mode") or "auto_tools"
        needs_clarification = bool(reasoning.get("needs_clarification", False))

        # 2) Clarification mode
        if needs_clarification and mode in ("clarify_only", "auto_tools"):
            return {
                "mode": "clarify_only",
                "use_tools": False,
                "explanation": "Reasoning requested clarification before acting.",
                "blocked": False,
            }

        # 3) Chat only mode
        if mode == "chat_only":
            return {
                "mode": "chat_only",
                "use_tools": False,
                "explanation": "Reasoning decided tools are unnecessary.",
                "blocked": False,
            }

        # 4) Tools forced
        if mode == "force_tools":
            return {
                "mode": "tools",
                "use_tools": True,
                "explanation": "Reasoning decided tools are required.",
                "blocked": False,
            }

        # 5) Default: automatic (planner can decide, tools allowed)
        return {
            "mode": "auto",
            "use_tools": True,
            "explanation": "Default automatic mode (tools allowed).",
            "blocked": False,
        }
