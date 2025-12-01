from __future__ import annotations

from typing import Any, Dict, List
import logging

from cloud.api.assistant.agents import chat_agent
from .intent_agent import IntentAgent
from .entity_agent import EntityAgent
from .safety_agent import SafetyAgent
from .planner_agent import PlannerAgentH
from .executor_agent import ExecutorAgent
from .verifier_agent import VerifierAgent

logger = logging.getLogger(__name__)


class CypherBrain:
    """
    High-level multi-agent brain for Cypher.

    Pipeline:
      1) IntentAgent      → break message into intents
      2) EntityAgent      → resolve entities & parameters
      3) SafetyAgent      → filter / block dangerous intents
      4) PlannerAgentH    → map intents → tool steps
      5) ExecutorAgent    → run tools (time, weather, OS, calendar, etc.)
      6) VerifierAgent    → inspect results
      7) ChatAgent        → generate final reply
    """

    def __init__(self) -> None:
        self.intent_agent = IntentAgent()
        self.entity_agent = EntityAgent()
        self.safety_agent = SafetyAgent()
        self.planner = PlannerAgentH()
        self.executor = ExecutorAgent()
        self.verifier = VerifierAgent()

    async def process(
        self,
        message: str,
        ctx: Dict[str, Any],
    ) -> tuple[str, List[Dict[str, Any]]]:
        device = ctx.get("device") or {"device_id": "local-dev"}
        history: List[Dict[str, Any]] = ctx.get("history") or []

        # 1) Intents
        intents = await self.intent_agent.parse(message, history)

        # Pure chat
        if len(intents) == 1 and intents[0].get("type") == "chat":
            reply = await chat_agent.run(
                message=message,
                history=history,
                device=device,
                tools_used=None,
            )
            return reply, []

        # 2) Entities
        enriched = self.entity_agent.enrich(intents, message, ctx)

        # 3) Safety
        safe_intents, blocked = self.safety_agent.filter(enriched)
        if not safe_intents:
            details = ", ".join(i.get("reason", "blocked") for i in blocked) or "unsafe action"
            reply = (
                "I’ve blocked this request for safety reasons "
                f"({details}). I can help with other tasks instead."
            )
            return reply, []

        # 4) Plan tool calls
        steps = self.planner.plan(safe_intents)
        if not steps:
            reply = await chat_agent.run(
                message=message,
                history=history,
                device=device,
                tools_used=None,
            )
            return reply, []

        # 5) Execute tools
        exec_ctx = dict(ctx)
        exec_ctx["message"] = message
        tools_meta = await self.executor.run(steps, exec_ctx)

        # 6) Verification
        verification = self.verifier.analyse(tools_meta)

        # 7) Build a compact tool summary for ChatAgent
        tool_summary_lines: List[str] = []
        for t in tools_meta:
            name = t.get("tool")
            result = t.get("result")
            if "error" in t:
                tool_summary_lines.append(f"{name}: ERROR → {t['error']}")
                continue

            # Special case: calendar list
            if name == "calendar_google" and isinstance(result, dict):
                if result.get("mode") == "list" and result.get("status") == "ok":
                    events = result.get("events") or []
                    if not events:
                        tool_summary_lines.append("calendar_google: no upcoming events.")
                    else:
                        lines = []
                        for ev in events[:5]:
                            title = ev.get("title") or "Untitled"
                            start = ev.get("start") or "unknown time"
                            lines.append(f"{start} — {title}")
                        tool_summary_lines.append(
                            "calendar_google: upcoming events:\n" + "\n".join(lines)
                        )
                    continue

            # Generic preview
            preview = str(result)[:400]
            tool_summary_lines.append(f"{name}: {preview}")

        tools_block = (
            "\n\n[Tool results]\n" + "\n".join(tool_summary_lines)
            if tool_summary_lines
            else ""
        )

        augmented_message = message + tools_block

        reply = await chat_agent.run(
            message=augmented_message,
            history=history,
            device=device,
            tools_used=tools_meta,
        )

        if not verification["ok"]:
            failed_names = ", ".join(verification["failed_tools"])
            reply = (
                reply.strip()
                + f"\n\n(Note: some tools failed internally: {failed_names}. "
                  "I still returned what I could.)"
            )

        return reply, tools_meta
