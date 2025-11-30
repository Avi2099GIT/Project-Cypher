# cloud/api/assistant/agents_dir/entity_agent.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re


class EntityAgent:
    """
    Step 2: Take high-level intents and attach concrete parameters
    (city names, note content, OS actions, etc.) based on the message.
    """

    def enrich(
        self,
        intents: List[Dict[str, Any]],
        message: str,
        ctx: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        lower = message.lower()

        for intent in intents:
            itype = intent.get("type")
            params = dict(intent.get("params") or {})

            if itype in ("time", "weather"):
                # tools already infer city from message, but we keep hook
                params.setdefault("raw_message", message)

            elif itype == "web_search":
                # extract search query after 'search' or 'for'
                q = self._extract_search_query(lower)

                # If user says "open chrome and search for X"
                if not q:
                    m = re.search(r"search for (.+)", lower)
                    if m:
                        q = m.group(1).strip()

                params.setdefault("query", q or message.strip())

            elif itype == "notes":
                # decide add vs list
                if any(w in lower for w in ["show my notes", "list my notes", "what notes"]):
                    params.setdefault("action", "list")
                elif "clear" in lower:
                    params.setdefault("action", "clear")
                else:
                    params.setdefault("action", "add")
                    params.setdefault("content", self._extract_after_keywords(message, ["note", "remember", "remember to"]))

            elif itype == "tasks":
                if any(w in lower for w in ["list my tasks", "show my tasks", "what tasks"]):
                    params.setdefault("action", "list")
                elif "clear" in lower:
                    params.setdefault("action", "clear")
                elif "complete" in lower or "done" in lower:
                    # naive: look for a number
                    m = re.search(r"\b(\d+)\b", lower)
                    if m:
                        params.setdefault("action", "complete")
                        params.setdefault("id", int(m.group(1)))
                    else:
                        params.setdefault("action", "list")
                else:
                    params.setdefault("action", "add")
                    params.setdefault("text", self._extract_after_keywords(message, ["task", "todo", "to-do", "add task", "remind me to"]))

            elif itype == "calendar":
                if any(w in lower for w in ["show my calendar", "list my events", "what's on my calendar"]):
                    params.setdefault("action", "list")
                elif "clear" in lower:
                    params.setdefault("action", "clear")
                else:
                    params.setdefault("action", "add")
                    # very simple: title = everything after 'event' or 'meeting'
                    title, time_hint = self._extract_calendar_fields(message)
                    if title:
                        params.setdefault("title", title)
                    if time_hint:
                        params.setdefault("time_hint", time_hint)
                    params.setdefault("raw_message", message)

            elif itype == "os_control":
                # let tools infer, but we can help:
                if any(w in lower for w in ["lock my computer", "lock the pc", "lock screen"]):
                    params.setdefault("action", "lock")
                elif "process" in lower:
                    params.setdefault("action", "list_processes")
                elif "open" in lower or "launch" in lower or "start" in lower:
                    # detect URL
                    url_match = re.search(r"(https?://\S+)", message)
                    if url_match:
                        params.setdefault("action", "open_url")
                        params.setdefault("url", url_match.group(1))
                    else:
                        # very simple app detection
                        for app in ["notepad", "calculator", "calc"]:
                            if app in lower:
                                params.setdefault("action", "open_app")
                                params.setdefault("app", app)
                                break

            enriched.append(
                {
                    "type": itype,
                    "params": params,
                    "priority": intent.get("priority", 1),
                }
            )

        return enriched

    def _extract_search_query(self, lower: str) -> str | None:
        # examples:
        # "search web for what is quantum computing"
        # "search for dark matter"
        for prefix in ["search web for", "search for", "search"]:
            if prefix in lower:
                return lower.split(prefix, 1)[1].strip() or None
        return None

    def _extract_after_keywords(self, message: str, keywords: List[str]) -> str:
        lower = message.lower()
        best_idx = None
        for kw in keywords:
            if kw in lower:
                idx = lower.index(kw) + len(kw)
                if best_idx is None or idx < best_idx:
                    best_idx = idx
        if best_idx is None:
            return message.strip()
        return message[best_idx:].strip(" :-.,").strip()

    def _extract_calendar_fields(self, message: str) -> Tuple[str | None, str | None]:
        """
        Extremely naive calendar extraction.
        e.g. 'Add calendar event Meeting at 5 PM'
        -> title='Meeting', time_hint='5 PM'
        """
        lower = message.lower()
        title = None
        time_hint = None

        # find 'at <time>' pattern
        m = re.search(r"\bat\s+([0-9: ]+(am|pm)?)", lower)
        if m:
            time_hint = m.group(1).strip()

        # try to guess title after 'event' or 'meeting'
        for kw in ["event", "meeting", "call"]:
            if kw in lower:
                idx = lower.index(kw) + len(kw)
                title = message[idx:].strip(" :-.,")
                if time_hint and "at" in title.lower():
                    title = title.split("at", 1)[0].strip()
                break

        return title or None, time_hint or None
