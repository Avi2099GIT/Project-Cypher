# cloud/api/assistant/agents_dir/brain.py
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
      5) ExecutorAgent    → run tools (time, weather, OS, etc.)
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
        """
        Main entry point used by the FastAPI router.

        ctx should contain:
          - device: dict
          - history: list[dict]
        """
        device = ctx.get("device") or {"device_id": "local-dev"}
        history: List[Dict[str, Any]] = ctx.get("history") or []

        # 1) Intents
        intents = await self.intent_agent.parse(message, history)

        # If only 'chat' → skip tools completely
        if len(intents) == 1 and intents[0].get("type") == "chat":
            reply = await chat_agent.run(
                message=message,
                history=history,
                device=device,
                tools_used=None,
            )
            return reply, []

        # 2) Entity resolution
        enriched = self.entity_agent.enrich(intents, message, ctx)

        # 3) Safety filter
        safe_intents, blocked = self.safety_agent.filter(enriched)

        if not safe_intents:
            # All blocked → explain
            details = ", ".join(i.get("reason", "blocked") for i in blocked) or "unsafe action"
            reply = (
                "I’ve blocked this request for safety reasons "
                f"({details}). I can help with other tasks instead."
            )
            return reply, []

        # 4) Plan tool calls
        steps = self.planner.plan(safe_intents)

        if not steps:
            # Nothing to execute, fallback to chat
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

        # 7) Final answer via ChatAgent using tool results as context
        tool_summary_lines: List[str] = []
        for t in tools_meta:
            name = t.get("tool")
            if "error" in t:
                tool_summary_lines.append(f"{name}: ERROR → {t['error']}")
            else:
                preview = str(t.get("result"))[:400]
                tool_summary_lines.append(f"{name}: {preview}")

        tools_block = "\n\n[Tool results]\n" + "\n".join(tool_summary_lines) if tool_summary_lines else ""

        augmented_message = message + tools_block

        reply = await chat_agent.run(
            message=augmented_message,
            history=history,
            device=device,
            tools_used=tools_meta,
        )

        # If something failed, gently mention it
        if not verification["ok"]:
            failed_names = ", ".join(verification["failed_tools"])
            reply = (
                reply.strip()
                + f"\n\n(Note: some tools failed internally: {failed_names}. "
                "I still returned what I could.)"
            )

        return reply, tools_meta
