# cloud/api/assistant/agents_dir/intent_agent.py
from __future__ import annotations

from typing import Any, Dict, List
import json
import logging

from cloud.api.assistant.agents import _call_openai_chat, OPENAI_MODEL_PLANNER

logger = logging.getLogger(__name__)


class IntentAgent:
    """
    Step 1: Turn the raw user message into a list of high-level intents.

    Each intent is a dict like:
    {
        "type": "weather" | "time" | "web_search" | "os_control" | "notes" | "tasks" | "calendar" | "chat",
        "params": { ... },
        "priority": 1
    }
    """

    def __init__(self, model: str = OPENAI_MODEL_PLANNER) -> None:
        self.model = model

    async def parse(self, message: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 1) Try LLM-based parsing
        intents = await self._parse_with_llm(message, history)
        if intents:
            return intents

        # 2) Fallback: rule-based intents
        return self._parse_with_rules(message)

    async def _parse_with_llm(self, message: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            history_snippets: List[str] = []
            for h in history[-5:]:
                role = h.get("role", "user")
                content = h.get("content", "")
                history_snippets.append(f"{role}: {content}")

            system_prompt = (
            "You are the Intent Agent for Cypher, an AI operating system.\n"
            "Your job is to decompose a user message into one or more intents.\n\n"

            "IMPORTANT RULES:\n"
            "1. Split compound requests into MULTIPLE intents.\n"
            "2. Preserve execution order using priority (1 = first).\n"
            "3. DO NOT merge different actions into one intent.\n"
            "4. Each intent MUST represent exactly ONE action.\n\n"

            "Supported intent types:\n"
            "  - 'time'\n"
            "  - 'weather'\n"
            "  - 'web_search'\n"
            "  - 'os_control'\n"
            "  - 'notes'\n"
            "  - 'tasks'\n"
            "  - 'calendar'\n"
            "  - 'chat'\n\n"

            "Return ONLY a JSON object with this schema:\n"
            "{ \"intents\": [\n"
            "  {\n"
            "    \"type\": \"time\" | \"weather\" | \"web_search\" | \"os_control\" |\n"
            "             \"notes\" | \"tasks\" | \"calendar\" | \"chat\",\n"
            "    \"params\": { },\n"
            "    \"priority\": 1\n"
            "  }\n"
            "]}\n\n"

            "Example:\n"
            "User: 'Open Chrome and search for artificial intelligence'\n"
            "Return:\n"
            "{ \"intents\": [\n"
            "    {\"type\":\"os_control\",\"params\":{},\"priority\":1},\n"
            "    {\"type\":\"web_search\",\"params\":{\"query\":\"artificial intelligence\"},\"priority\":2}\n"
            "]}\n"
            )


            user_prompt = (
                "Recent conversation:\n" + "\n".join(history_snippets) + "\n\n"
                f"User message:\n{message}\n\n"
                "Think internally, but output ONLY the final JSON object, nothing else."
            )

            raw = await _call_openai_chat(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.model,
            )

            try:
                data = json.loads(raw)
            except Exception:
                logger.warning("IntentAgent: JSON parse failed, raw=%r", raw)
                return []

            intents = data.get("intents") or []
            if not isinstance(intents, list):
                return []

            cleaned: List[Dict[str, Any]] = []
            for it in intents:
                if not isinstance(it, dict):
                    continue
                t = it.get("type")
                if t not in (
                    "time",
                    "weather",
                    "web_search",
                    "os_control",
                    "notes",
                    "tasks",
                    "calendar",
                    "chat",
                ):
                    continue
                params = it.get("params") or {}
                if not isinstance(params, dict):
                    params = {}
                prio = it.get("priority", 1)
                cleaned.append(
                    {
                        "type": t,
                        "params": params,
                        "priority": int(prio) if isinstance(prio, int) else 1,
                    }
                )

            return cleaned
        except Exception as e:
            logger.exception("IntentAgent LLM error: %s", e)
            return []

    def _parse_with_rules(self, message: str) -> List[Dict[str, Any]]:
        """
        Very simple rules as a safety net if LLM fails or is unavailable.
        """
        m = message.lower()
        intents: List[Dict[str, Any]] = []

        if any(w in m for w in ["weather", "temperature", "forecast"]):
            intents.append({"type": "weather", "params": {}, "priority": 1})

        if any(w in m for w in ["time", "clock", "what time"]):
            intents.append({"type": "time", "params": {}, "priority": 1})

        if any(w in m for w in ["search", "google", "look up"]):
            intents.append({"type": "web_search", "params": {}, "priority": 1})

        if any(w in m for w in ["note", "remember that", "remember to"]):
            intents.append({"type": "notes", "params": {}, "priority": 1})

        if any(w in m for w in ["task", "todo", "to-do", "reminder"]):
            intents.append({"type": "tasks", "params": {}, "priority": 1})

        if any(w in m for w in ["calendar", "schedule", "meeting", "event"]):
            intents.append({"type": "calendar", "params": {}, "priority": 1})

        if any(w in m for w in ["open", "launch", "start", "lock my computer", "lock screen", "processes"]):
            intents.append({"type": "os_control", "params": {}, "priority": 1})

        if not intents:
            intents.append({"type": "chat", "params": {}, "priority": 1})

        return intents
