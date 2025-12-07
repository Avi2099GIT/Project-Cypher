# cloud/api/assistant/agents_dir/intent_agent.py
from __future__ import annotations

from typing import Any, Dict, List
import logging
import re

logger = logging.getLogger(__name__)


class IntentAgent:
    """
    Very small, very explicit intent classifier.

    Responsibilities:
      - Decide *type* of intent:
          - "calendar"
          - "task"
          - "time"
          - "weather"
          - "os"
          - "web"
          - "chat"
      - Do NOT decide calendar actions (create/list/delete/update).
        That is handled by EntityAgent.
    """

    async def parse(
        self,
        message: str,
        history: List[Dict[str, Any]] | None = None,
        ctx: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Async interface for compatibility with existing graph/brain code.
        Internally just calls a synchronous classifier.
        """
        history = history or []
        ctx = ctx or {}

        intents = self._classify(message)
        logger.debug("IntentAgent.parse -> %s", intents)
        return intents

    # ------------------------------------------------------------------
    # Internal classifier
    # ------------------------------------------------------------------

    def _classify(self, message: str) -> List[Dict[str, Any]]:
        text = (message or "").strip()
        lower = text.lower()

        if not text:
            # Nothing to do – treat as generic chat
            return [
                {
                    "type": "chat",
                    "priority": 1,
                    "params": {},
                }
            ]

        # --- Calendar-like phrases (meetings, events, reminders) ---
        if self._looks_like_calendar(lower):
            return [
                {
                    "type": "calendar",
                    "priority": 1,
                    "params": {},  # EntityAgent will fill this
                }
            ]

        # --- Task / todo / non-calendar reminders ---
        # NOTE: we deliberately do NOT include "remind me" here, so that
        #       "remind me at 7pm" still routes to calendar, as you had before.
        if self._looks_like_task(lower):
            return [
                {
                    "type": "task",
                    "priority": 1,
                    "params": {},
                }
            ]

        # --- Weather queries ---
        if self._looks_like_weather(lower):
            return [
                {
                    "type": "weather",
                    "priority": 1,
                    "params": {
                        # tools can still read the full user message
                        # from ToolContext.message, but this is here if
                        # you later want to parse location explicitly.
                        "raw_message": message,
                    },
                }
            ]

        # --- Time queries ---
        if self._looks_like_time(lower):
            return [
                {
                    "type": "time",
                    "priority": 1,
                    "params": {
                        "raw_message": message,
                    },
                }
            ]

        # --- OS / system ops (lock, open apps, etc.) ---
        if self._looks_like_os(lower):
            return [
                {
                    "type": "os",
                    "priority": 1,
                    "params": {
                        "raw_message": message,
                    },
                }
            ]

        # --- Web search ---
        if self._looks_like_web(lower):
            return [
                {
                    "type": "web",
                    "priority": 1,
                    "params": {
                        "raw_message": message,
                    },
                }
            ]

        # Fallback: normal conversation
        return [
            {
                "type": "chat",
                "priority": 1,
                "params": {},
            }
        ]

    # ------------------------------------------------------------------
    # Heuristics
    # ------------------------------------------------------------------

    def _looks_like_calendar(self, lower: str) -> bool:
        """
        Decide if this message is about *calendar*.

        We keep this intentionally simple and focused.
        """
        calendar_keywords = [
            "calendar",
            "meeting",
            "meet with",
            "schedule a meeting",
            "schedule meeting",
            "schedule an event",
            "book a meeting",
            "book an appointment",
            "appointment",
            "event",
            "call with",
            "zoom call",
            "google meet",
            "team call",
            "set up a meeting",
            "schedule a call",
            "schedule a reminder",
            # You were using "remind me ..." for calendar-style reminders
            "remind me",
        ]

        if any(kw in lower for kw in calendar_keywords):
            return True

        # Also treat things like "at 7pm on 5th December" *with* a time verb
        if "schedule" in lower or "book" in lower or "set up" in lower:
            if re.search(r"\b(at|on)\b", lower) and re.search(
                r"\b\d{1,2}(:\d{2})?\s*(am|pm)?\b", lower
            ):
                return True

        return False

    def _looks_like_task(self, lower: str) -> bool:
        """
        Task / todo manager style things.

        We deliberately do NOT treat "remind me" as tasks,
        so your reminders continue to use Calendar (as before).
        """
        task_keywords = [
            "to-do",
            "todo",
            "task",
            "add to my todo",
            "add to my to-do",
            "add to my list",
            "create a task",
            "new task",
        ]

        return any(kw in lower for kw in task_keywords)

    def _looks_like_weather(self, lower: str) -> bool:
        """
        Weather / forecast queries.

        Example:
          - "what's the weather in hyderabad"
          - "is it raining in mumbai"
          - "temperature in delhi tomorrow"
        """
        if "weather" in lower or "forecast" in lower:
            return True

        weather_words = [
            "raining",
            "rainy",
            "rain today",
            "snow",
            "snowing",
            "hot outside",
            "cold outside",
            "temperature",
            "humid",
            "humidity",
        ]
        if any(kw in lower for kw in weather_words):
            return True

        # Very rough pattern: "how hot is it" / "how cold is it"
        if re.search(r"how\s+(hot|cold)\s+is\s+it", lower):
            return True

        return False

    def _looks_like_time(self, lower: str) -> bool:
        """
        Time / date queries.

        Example:
          - "what time is it"
          - "time in london"
          - "what's the date today"
        """
        # Direct time questions
        if "what time is it" in lower or "current time" in lower or "time now" in lower:
            return True

        # "time in london", "time in new york"
        if re.search(r"time\s+in\s+\w+", lower):
            return True

        # Date / day questions can also go through the time tool
        if any(
            kw in lower
            for kw in [
                "what's the date",
                "whats the date",
                "what is the date",
                "what day is it",
                "which day is it",
            ]
        ):
            return True

        return False

    def _looks_like_os(self, lower: str) -> bool:
        """
        OS / system control.

        We keep this *descriptive*; actual safety is enforced
        in the os_control tool and SafetyAgent.
        """
        # Locking / session control
        os_lock_phrases = [
            "lock my computer",
            "lock the computer",
            "lock my pc",
            "lock pc",
            "lock screen",
        ]

        if any(kw in lower for kw in os_lock_phrases):
            return True

        # Generic "open X" for common apps
        if lower.startswith("open "):
            return True

        os_keywords = [
            "open app",
            "open application",
            "launch",
            "shutdown",
            "shut down",
            "restart",
            "restart machine",
            "sleep mode",
            "put my pc to sleep",
        ]

        if any(kw in lower for kw in os_keywords):
            return True

        return False

    def _looks_like_web(self, lower: str) -> bool:
        """
        Web search queries.

        Example:
          - "search web for ..."
          - "google for ..."
          - "look up ..."
        """
        web_prefixes = [
            "search web for",
            "search for",
            "google for",
            "google",
            "look up",
            "lookup",
        ]

        if any(kw in lower for kw in web_prefixes):
            return True

        # "open https://...", "open http://..."
        if "http://" in lower or "https://" in lower:
            return True

        return False
