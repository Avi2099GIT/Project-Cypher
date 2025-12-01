from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from dotenv import load_dotenv

from .tools_registry import tool_registry
from .tools_base import ToolContext

load_dotenv()

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

OPENAI_MODEL_CHAT = os.getenv("CYPHER_CHAT_MODEL", "gpt-4o-mini")
OPENAI_MODEL_PLANNER = os.getenv("CYPHER_PLANNER_MODEL", "gpt-4o-mini")

PlannerDecisionMode = Literal["chat", "tools", "mixed", "mcp"]


class PlannerDecision(Dict[str, Any]):
    """Dict-like decision object with convenience accessors."""

    @property
    def mode(self) -> PlannerDecisionMode:
        return self.get("mode", "chat")  # type: ignore[return-value]

    @property
    def tools(self) -> List[Dict[str, Any]]:
        return self.get("tools", [])


# -------------------------------------------------------------------
# OpenAI helper
# -------------------------------------------------------------------

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover
    openai = None  # type: ignore
    logger.warning("OpenAI library not available; LLM calls will fail.")


async def _call_openai_chat(*, prompt: str, system_prompt: str, model: str) -> str:
    """
    Thin wrapper around OpenAI Chat Completions.
    Returns a string; caller is responsible for interpreting/parsing.
    """
    if openai is None:
        logger.warning("OpenAI library not installed.")
        return "LLM ERROR: openai library not installed"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY missing.")
        return "LLM ERROR: missing API key"

    try:
        client = openai.OpenAI(api_key=api_key)

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:  # pragma: no cover
        logger.exception("LLM planner/chat call failed: %s", e)
        return f"LLM ERROR: {e}"


# -------------------------------------------------------------------
# ChatAgent — main conversation brain
# -------------------------------------------------------------------

class ChatAgent:
    """
    LLM-powered chat agent.
    Takes user message + history + optional tool results and returns a reply.
    """

    def __init__(self, model: str = OPENAI_MODEL_CHAT) -> None:
        self.model = model

    async def run(
        self,
        message: str,
        history: List[Dict[str, Any]],
        device: Optional[Dict[str, Any]] = None,
        tools_used: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        # Compact history
        history_snippets = [
            f"{h.get('role', 'user')}: {h.get('content', '')}"
            for h in history[-5:]
        ]

        tool_block = ""
        if tools_used:
            lines: List[str] = []
            for t in tools_used:
                name = t.get("tool", "unknown-tool")
                result_preview = str(t.get("result"))[:200]
                lines.append(f"- {name}: {result_preview}")
            tool_block = "\n\nRecent tool results:\n" + "\n".join(lines)

        device_block = ""
        if device:
            device_id = device.get("device_id") or device.get("id") or "unknown-device"
            device_block = f"\n\nDevice: {device_id}"

        # IMPORTANT: no emojis / markdown, to avoid PowerShell mojibake
        system_prompt = (
        "You are Cypher, an AI operating system assistant (Jarvis-like). "
        "You reply briefly, clearly, and helpfully. "
        "You may see condensed history and tool results. "
        "Avoid using emojis or non-ASCII symbols in your replies. "
        "Prefer plain text and simple Markdown only."
        "Use them to stay context-aware, but do not mention raw JSON or internal structures. "
        "If a tool result includes a field named 'htmlLink' (for example from Google Calendar), "
        "ALWAYS present that exact URL as the link and NEVER construct or guess Google Calendar URLs yourself."
        "print the EXACT full URL as plain text.\n"
        "Do NOT wrap links in Markdown.\n"
        "DO NOT shorten URLs.\n"
        "DO NOT generate Google links yourself.\n"
        "If a URL is present in tool results, you MUST display THAT URL."
        )


        user_prompt = (
            "Conversation history (last few turns):\n"
            + "\n".join(history_snippets)
            + "\n\nUser message:\n"
            + message
            + tool_block
            + device_block
        )

        reply = await _call_openai_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=self.model,
        )
        return reply.strip() or "I’m here and listening."


# -------------------------------------------------------------------
# PlannerAgent — (still available, but H-pipeline mostly uses IntentAgent)
# -------------------------------------------------------------------

class PlannerAgent:
    """
    LLM-powered planner that decides:
      - mode: 'chat' | 'tools' | 'mixed' | 'mcp'
      - tools: list of { name: str, args: dict }
    """

    def __init__(self, model: str = OPENAI_MODEL_PLANNER) -> None:
        self.model = model

    def _heuristic_plan(self, message: str) -> PlannerDecision:
        msg = message.lower()

        if any(k in msg for k in ["time", "clock", "current time"]):
            return PlannerDecision(
                {"mode": "tools", "tools": [{"name": "time", "args": {}}]}
            )

        if any(k in msg for k in ["system", "os", "machine", "python version"]):
            return PlannerDecision(
                {"mode": "tools", "tools": [{"name": "system_info", "args": {}}]}
            )

        return PlannerDecision({"mode": "chat", "tools": []})

    async def plan(
        self,
        message: str,
        history: List[Dict[str, Any]],
        device: Optional[Dict[str, Any]] = None,
        forced_mode: Optional[PlannerDecisionMode] = None,
    ) -> PlannerDecision:
        if forced_mode:
            return PlannerDecision({"mode": forced_mode, "tools": []})

        heuristic_decision = self._heuristic_plan(message)
        if heuristic_decision.mode != "chat":
            return heuristic_decision

        tools_info = [
            {"name": t.name, "description": t.description}
            for t in tool_registry.list()
        ]
        tools_json = json.dumps(tools_info, ensure_ascii=False, indent=2)

        history_snippets = [
            f"{h.get('role', 'user')}: {h.get('content', '')}"
            for h in history[-5:]
        ]

        system_prompt = (
            "You are the Planner for Cypher, an AI OS assistant.\n"
            "Respond ONLY with valid JSON.\n"
            "Schema:\n"
            "{\n"
            '  \"mode\": \"chat\" | \"tools\" | \"mixed\" | \"mcp\",\n'
            "  \"tools\": [ { \"name\": string, \"args\": object } ]\n"
            "}\n"
        )

        user_prompt = (
            "Available tools:\n"
            f"{tools_json}\n\n"
            "Recent conversation:\n"
            + "\n".join(history_snippets)
            + "\n\nUser message:\n"
            f"{message}\n\n"
            "Think internally, but output ONLY the final JSON decision."
        )

        raw = await _call_openai_chat(
            prompt=user_prompt, system_prompt=system_prompt, model=self.model
        )

        if not raw or raw.startswith("LLM ERROR"):
            logger.warning("Planner LLM failed, raw=%r", raw)
            return self._heuristic_plan(message)

        try:
            decision_data = json.loads(raw)
        except Exception:
            logger.warning("Planner JSON parse failed, raw=%r", raw)
            return self._heuristic_plan(message)

        mode = decision_data.get("mode", "chat")
        if mode not in ("chat", "tools", "mixed", "mcp"):
            mode = "chat"

        tools_list = decision_data.get("tools") or []
        if not isinstance(tools_list, list):
            tools_list = []

        valid_tool_names = {t.name for t in tool_registry.list()}
        filtered_tools: List[Dict[str, Any]] = []
        for t in tools_list:
            if not isinstance(t, dict):
                continue
            name = t.get("name")
            if name in valid_tool_names:
                filtered_tools.append({"name": name, "args": t.get("args") or {}})

        if mode in ("tools", "mixed") and not filtered_tools:
            return PlannerDecision({"mode": "chat", "tools": []})

        return PlannerDecision({"mode": mode, "tools": filtered_tools})


# -------------------------------------------------------------------
# ToolExecutorAgent — executes tools based on PlannerDecision
# -------------------------------------------------------------------

class ToolExecutorAgent:
    async def run(
        self,
        decision: PlannerDecision,
        message: str,
        history: List[Dict[str, Any]],
        device: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        tools_meta: List[Dict[str, Any]] = []

        if not decision.tools:
            return "I don't need to call any tools for this.", tools_meta

        ctx = ToolContext(device=device or {}, history=history, message=message)

        lines: List[str] = []
        for tool_spec in decision.tools:
            name = tool_spec.get("name")
            args = tool_spec.get("args") or {}

            try:
                result = await tool_registry.call(name=name, args=args, ctx=ctx)
                tools_meta.append({"tool": name, "args": args, "result": result})
                lines.append(f"{name}: {result}")
            except Exception as e:  # pragma: no cover
                logger.exception("Error executing tool %s: %s", name, e)
                tools_meta.append({"tool": name, "args": args, "error": str(e)})
                lines.append(f"{name}: ERROR: {e}")

        reply_text = "\n".join(lines)
        return reply_text, tools_meta


# -------------------------------------------------------------------
# Global singletons
# -------------------------------------------------------------------

chat_agent = ChatAgent()
planner_agent = PlannerAgent()
tool_executor = ToolExecutorAgent()
