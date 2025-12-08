from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from cloud.api.assistant.orchestrator.tracer import tracer

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
        ctx: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Decide how to proceed, and annotate the trace with the arbiter decision.
        """

        # -----------------------------
        # 1) Safety has absolute priority
        # -----------------------------
        if not safe_intents and blocked_intents:
            reasons = [b.get("reason") or "unsafe" for b in blocked_intents]
            explanation = "Request blocked by safety policy: " + "; ".join(reasons)

            decision: Dict[str, Any] = {
                "mode": "safety_block",
                "use_tools": False,
                "explanation": explanation,
                "blocked": True,
            }

        else:
            mode = (reasoning.get("mode") or "auto_tools").lower()
            needs_clarification = bool(reasoning.get("needs_clarification", False))

            # -----------------------------
            # 2) Clarification mode
            # -----------------------------
            if needs_clarification and mode in ("clarify_only", "auto_tools"):
                decision = {
                    "mode": "clarify_only",
                    "use_tools": False,
                    "explanation": "Reasoning requested clarification before acting.",
                    "blocked": False,
                }

            # -----------------------------
            # 3) Chat only mode
            # -----------------------------
            elif mode == "chat_only":
                decision = {
                    "mode": "chat_only",
                    "use_tools": False,
                    "explanation": "Reasoning decided tools are unnecessary.",
                    "blocked": False,
                }

            # -----------------------------
            # 4) Tools forced
            # -----------------------------
            elif mode == "force_tools":
                decision = {
                    "mode": "tools",
                    "use_tools": True,
                    "explanation": "Reasoning decided tools are required.",
                    "blocked": False,
                }

            # -----------------------------
            # 5) Default automatic mode
            # -----------------------------
            else:
                decision = {
                    "mode": "auto",
                    "use_tools": True,
                    "explanation": "Default automatic mode (tools allowed).",
                    "blocked": False,
                }

        # =======================================================
        # ✅ TRACE ANNOTATION — Arbiter Decision (EPIC #1)
        # =======================================================
        trace_id: Optional[str] = None

        # ctx can be an ExecutionContext OR a plain dict
        if ctx is not None:
            # ExecutionContext: try attribute first
            trace_id = getattr(ctx, "trace_id", None)
            # Fallback if ctx is a dict
            if trace_id is None and isinstance(ctx, dict):
                trace_id = ctx.get("trace_id")

        if trace_id:
            try:
                tracer.annotate(
                    trace_id=trace_id,
                    key="arbiter",
                    value={
                        "mode": decision["mode"],
                        "use_tools": decision["use_tools"],
                        "blocked": decision["blocked"],
                        "explanation": decision["explanation"],
                    },
                )
                logger.debug("Trace Annotation [arbiter][%s]: %s", trace_id, decision)
            except Exception:
                # Annotation must never break the core flow
                logger.exception(
                    "Failed to annotate arbiter decision for trace %s", trace_id
                )

        return decision
