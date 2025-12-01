from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re


class EntityAgent:
    """
    Step 2: Attach concrete parameters (city names, note content, OS actions, etc.)
    based on the message + already detected intents.
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

            # -------- TIME / WEATHER --------
            if itype in ("time", "weather"):
                params.setdefault("raw_message", message)

            # -------- WEB SEARCH ------------
            elif itype == "web_search":
                q = self._extract_search_query(lower)
                params.setdefault("query", q or message.strip())

            # -------- NOTES -----------------
            elif itype == "notes":
                if any(
                    phrase in lower
                    for phrase in [
                        "show my notes",
                        "list my notes",
                        "what notes do i have",
                        "what are my notes",
                    ]
                ):
                    params.setdefault("action", "list")
                elif "clear" in lower or "delete all notes" in lower:
                    params.setdefault("action", "clear")
                else:
                    params.setdefault("action", "add")
                    params.setdefault(
                        "content",
                        self._extract_after_keywords(
                            message,
                            ["note", "remember that", "remember to", "remember"],
                        ),
                    )

            # -------- TASKS -----------------
            elif itype == "tasks":
                # LIST
                if any(p in lower for p in ["list my tasks", "show my tasks","clear my task","delete my task","add a task","update my task"]):
                    params["action"] = "list"

                # CLEAR
                elif "clear" in lower or "delete all" in lower:
                    params["action"] = "clear"

                # COMPLETE
                elif "complete" in lower or "done" in lower:
                    m = re.search(r"\b(\d+)\b", lower)
                    if m:
                        params["action"] = "complete"
                        params["id"] = m.group(1)
                    else:
                        params["action"] = "list"

                # ADD (default)
                else:
                    params["action"] = "add"
                    params["text"] = self._extract_after_keywords(
                        message,
                        ["task", "todo", "add task", "remind me to"]
                    )

                # IMPORTANT SWITCH
                intent["type"] = "google_tasks"


            # -------- CALENDAR (Google) -----
            elif itype == "calendar":
                list_triggers = [
                    "show my calendar",
                    "show calendar",
                    "list my events",
                    "list calendar events",
                    "what's on my calendar",
                    "whats on my calendar",
                    "upcoming events",
                    "upcoming calendar events",
                    "show my upcoming events",
                    "show my upcoming calendar events",
                    "clear my task",
                    "delete my task",
                    "update my task",
                    "update event",
                    "reschedule event"
                ]
                if any(p in lower for p in list_triggers):
                    params.setdefault("action", "list")

                elif "clear calendar" in lower or "delete all events" in lower:
                    # This will use the local in-memory calendar; Google clear-all
                    # is dangerous so we keep it local-only for now.
                    params.setdefault("action", "clear")

                elif "delete" in lower or "cancel" in lower:
                    params.setdefault("action", "delete")
                    m = re.search(r"(event\s+)?([a-z0-9_\-]{8,})", lower)
                    if m:
                        params.setdefault("event_id", m.group(2))

                # ---- RESCHEDULE ----
                elif "reschedule" in lower or "move" in lower:
                    params["action"] = "update"
                    params["raw_message"] = message

                else:
                    # Default → create/schedule
                    params.setdefault("action", "create")
                    title, time_hint = self._extract_calendar_fields(message)
                    if title:
                        params.setdefault("title", title)
                    if time_hint:
                        params.setdefault("when", time_hint)
                    else:
                        params.setdefault("when", message)
                    params.setdefault("raw_message", message)
                
                


            # -------- OS CONTROL -----------
            elif itype == "os_control":
                if any(
                    phrase in lower
                    for phrase in ["lock my computer", "lock the pc", "lock screen"]
                ):
                    params.setdefault("action", "lock")
                elif "process" in lower:
                    params.setdefault("action", "list_processes")
                elif "open" in lower or "launch" in lower or "start" in lower:
                    url_match = re.search(r"(https?://\S+)", message)
                    if url_match:
                        params.setdefault("action", "open_url")
                        params.setdefault("url", url_match.group(1))
                    else:
                        for app in ["notepad", "calculator", "calc", "chrome", "edge", "explorer"]:
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

    # ----------------- Helpers -----------------

    def _extract_search_query(self, lower: str) -> str | None:
        for prefix in ["search web for", "search for", "search"]:
            if prefix in lower:
                q = lower.split(prefix, 1)[1].strip()
                return q or None
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
        e.g. 'Schedule meeting tomorrow at 6 PM'
        -> title='meeting', time_hint='tomorrow at 6 PM'
        """
        lower = message.lower()
        title = None
        time_hint = None

        m = re.search(
            r"(today|tomorrow|tonight|on\s+\w+)?\s*(at\s+[0-9: ]+(am|pm)?)",
            lower,
        )
        if m:
            time_hint = m.group(0).strip()

        for kw in ["event", "meeting", "call"]:
            if kw in lower:
                idx = lower.index(kw) + len(kw)
                title = message[idx:].strip(" :-.,")
                if time_hint and time_hint in title.lower():
                    title = title.lower().replace(time_hint, "").strip(" :-.,")
                break

        return (title or None, time_hint or None)
