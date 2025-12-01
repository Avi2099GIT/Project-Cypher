# cloud/api/assistant/agents_dir/intent_agent.py

from __future__ import annotations
from typing import Dict, Any, List
import re


class IntentAgent:
    """
    Step 1: Convert user message → list of intents.
    No LLM. Deterministic only.
    """

    async def parse(self, message: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        m = message.lower()
        intents: List[Dict[str, Any]] = []

        # -------- TIME ----------
        if any(k in m for k in ["time", "clock", "current time"]):
            intents.append({"type": "time", "params": {}, "priority": 1})

        # -------- WEATHER -------
        if any(k in m for k in ["weather", "temperature", "forecast"]):
            intents.append({"type": "weather", "params": {}, "priority": 1})

        # -------- GOOGLE SEARCH ---
        if any(k in m for k in ["search", "google", "look up"]):
            intents.append({"type": "web_search", "params": {}, "priority": 1})

        # -------- NOTES ----------
        if any(k in m for k in ["note", "remember"]):
            intents.append({"type": "notes", "params": {}, "priority": 2})

        # -------- TASKS ----------
        if any(k in m for k in ["task", "todo", "to-do", "remind me","tasks"]):
            intents.append({"type": "tasks", "params": {}, "priority": 2})

        # -------- CALENDAR -------
        if any(
            k in m for k in [
                "calendar", "meeting", "schedule", "appointment", "event"
            ]
        ):
            intents.append({"type": "calendar", "params": {}, "priority": 1})

        # -------- OS CONTROL -----
        if any(
            k in m for k in [
                "open", "launch", "start", "close", "kill", "lock", "process"
            ]
        ):
            intents.append({"type": "os_control", "params": {}, "priority": 1})

        if not intents:
            intents.append({"type": "chat", "params": {}, "priority": 10})

        return intents
