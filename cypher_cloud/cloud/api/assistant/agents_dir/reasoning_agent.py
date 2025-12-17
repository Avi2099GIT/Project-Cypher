from __future__ import annotations

from typing import Any, Dict, List
import json
import logging

from cloud.api.assistant.agents import _call_openai_chat, OPENAI_MODEL_CHAT

logger = logging.getLogger(__name__)


class ReasoningAgent:
    """
    LLM-based reasoning layer for Cypher.

    Given:
      - message
      - parsed intents
      - enriched entities
      - recent history

    It returns a compact JSON decision blob:

    {
      "mode": "auto_tools" | "chat_only" | "clarify_only" | "force_tools",
      "confidence": 0.0-1.0,
      "needs_clarification": bool,
      "clarification_question": str | null,
      "notes": str
    }
    """

    def __init__(self, model: str = OPENAI_MODEL_CHAT) -> None:
        self.model = model

    # ---------------------------------------------------------
    # MEMORY FILTERING (UNCHANGED)
    # ---------------------------------------------------------

    def _filter_memory_episodes(self, memory) -> list:
        episodes = (memory or {}).get("recent_episodes", [])

        filtered = []
        for ep in episodes:
            meta = ep.get("meta") or {}
            content = (ep.get("content") or "").lower()

            if meta.get("suppress_for_reasoning"):
                continue

            if "your computer is now locked" in content:
                continue
            if "computer is currently locked" in content:
                continue

            filtered.append(ep)

        return filtered

    # ---------------------------------------------------------
    # EXECUTION INTENT DETECTION (NEW, CRITICAL)
    # ---------------------------------------------------------

    def _looks_like_execution(self, message: str) -> bool:
        """
        Detects imperative execution intent where tools are REQUIRED,
        even if the LLM is unavailable.
        """
        msg = message.lower().strip()

        imperative_prefixes = (
            "run ",
            "execute ",
            "exec ",
            "open ",
            "list ",
            "show ",
            "delete ",
            "remove ",
            "create ",
            "kill ",
            "start ",
            "stop ",
        )

        if msg.startswith(imperative_prefixes):
            return True

        if "run command" in msg or "execute command" in msg:
            return True

        return False

    # ---------------------------------------------------------
    # MAIN ENTRY
    # ---------------------------------------------------------

    async def run(
        self,
        message: str,
        intents: List[Dict[str, Any]],
        enriched: Any,
        history: List[Dict[str, Any]],
        memory,
    ) -> Dict[str, Any]:

        history_snippets = [
            f"{h.get('role', 'user')}: {h.get('content', '')}"
            for h in history[-5:]
        ]

        system_prompt = (
            "You are ReasoningAgent inside Cypher, an AI operating system.\n"
            "Your job is to decide HOW Cypher should respond, not to respond directly.\n\n"
            "You MUST respond with STRICT JSON only, no prose, no comments.\n\n"
            "JSON schema:\n"
            "{\n"
            '  \"mode\": \"auto_tools\" | \"chat_only\" | \"clarify_only\" | \"force_tools\",\n'
            "  \"confidence\": number between 0 and 1,\n"
            "  \"needs_clarification\": boolean,\n"
            "  \"clarification_question\": string or null,\n"
            "  \"notes\": string\n"
            "}\n\n"
            "Definitions:\n"
            "- auto_tools: let the planner decide and run tools if helpful.\n"
            "- chat_only: just answer conversationally; tools are unnecessary.\n"
            "- clarify_only: DO NOT answer or run tools; Cypher must ask a clarifying question.\n"
            "- force_tools: tools are essential (e.g., calendar, tasks, system state, web, weather).\n"
            "You MUST NOT assume computer lock state from past memory.\n"
            "If the user asks for real-time information (weather, stocks, news) or personal data (calendar, tasks), you MUST choose 'force_tools' or 'auto_tools'. Do NOT use 'chat_only'.\n"
        )

        filtered_episodes = self._filter_memory_episodes(memory)

        user_prompt = json.dumps(
            {
                "message": message,
                "intents": intents,
                "enriched": enriched,
                "recent_history": history_snippets,
                "memory": filtered_episodes,
            },
            ensure_ascii=False,
            indent=2,
        )

        raw = await _call_openai_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=self.model,
        )

        # -------------------------
        # LLM FAILURE → HEURISTICS
        # -------------------------

        if not raw or raw.startswith("LLM ERROR"):
            logger.warning("ReasoningAgent LLM failed, raw=%r", raw)
            return self._fallback_decision(message, intents)

        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("ReasoningAgent JSON parse failed, raw=%r", raw)
            return self._fallback_decision(message, intents)

        mode = data.get("mode") or "auto_tools"
        if mode not in ("auto_tools", "chat_only", "clarify_only", "force_tools"):
            mode = "auto_tools"

        try:
            confidence = float(data.get("confidence", 0.7))
        except Exception:
            confidence = 0.7

        needs_clarification = bool(data.get("needs_clarification", False))
        clarification_question = data.get("clarification_question")
        if clarification_question is not None:
            clarification_question = str(clarification_question).strip() or None

        notes = str(data.get("notes") or "").strip()

        return {
            "mode": mode,
            "confidence": max(0.0, min(confidence, 1.0)),
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "notes": notes,
        }

    # ---------------------------------------------------------
    # FALLBACK (UPDATED, SAFE)
    # ---------------------------------------------------------

    def _fallback_decision(
        self,
        message: str,
        intents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Deterministic heuristic fallback if the LLM fails.
        This MUST allow OS / MCP execution.
        """
        lower = message.lower()
        if "time" in lower:
            return {
                "mode": "force_tools",
                "confidence": 0.95,
                "needs_clarification": False,
                "clarification_question": None,
                "notes": "time_requires_tool_override",
            }

        # 🔴 CRITICAL FIX: execution intent bypasses LLM
        if self._looks_like_execution(message):
            return {
                "mode": "force_tools",
                "confidence": 0.95,
                "needs_clarification": False,
                "clarification_question": None,
                "notes": "imperative_execution_detected_fallback",
            }

        if any(k in lower for k in ["what time", "weather", "temperature", "forecast"]):
            mode = "force_tools"
        elif any(k in lower for k in ["schedule", "calendar", "event", "meeting", "reminder"]):
            mode = "force_tools"
        else:
            if len(intents) == 1 and intents[0].get("type") == "chat":
                mode = "chat_only"
            else:
                mode = "auto_tools"

        return {
            "mode": mode,
            "confidence": 0.6,
            "needs_clarification": False,
            "clarification_question": None,
            "notes": "heuristic_fallback",
        }
