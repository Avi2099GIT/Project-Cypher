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
                if any(
                    p in lower
                    for p in [
                        "list my tasks",
                        "show my tasks",
                        "clear my task",
                        "delete my task",
                        "add a task",
                        "update my task",
                    ]
                ):
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
                        message, ["task", "todo", "add task", "remind me to"]
                    )

                # IMPORTANT SWITCH
                itype = "google_tasks"

            # -------- CALENDAR (Google) -----
            elif itype == "calendar":
                # Phrases that should almost always mean "show/list"
                list_triggers = [
                    "show my calendar",
                    "show me my calendar",
                    "show calendar",
                    "show me calendar",
                    "list my events",
                    "list calendar events",
                    "what's on my calendar",
                    "whats on my calendar",
                    "upcoming events",
                    "upcoming calendar events",
                    "show my upcoming events",
                    "show my upcoming calendar events",
                    "calendar for this week",
                    "my calendar for this week",
                    "calendar for today",
                    "calendar for tomorrow",
                    "show me my calendar for this week",
                ]

                is_list = any(p in lower for p in list_triggers)

                # Generic heuristic: "show" + "calendar" or "calendar" + relative range
                has_create_verb = any(
                    v in lower for v in ["schedule", "create", "add", "book", "set up"]
                )
                if (
                    ("show" in lower and "calendar" in lower)
                    or ("calendar" in lower and any(p in lower for p in ["this week", "today", "tomorrow"]))
                ) and not has_create_verb:
                    is_list = True

                if is_list:
                    params.setdefault("action", "list")

                if is_list:
                    params.setdefault("action", "list")

                elif any(kw in lower for kw in ["clear", "delete", "remove", "cancel"]):
                    params.setdefault("action", "delete")
                    # If specific event ID not found, it implies bulk delete by range (handled by tool)
                    m = re.search(r"(event\s+)?([a-z0-9_\-]{8,})", lower)
                    if m:
                        params.setdefault("event_id", m.group(2))
                    
                    # Ensure range fields are extracted for bulk clear
                    title_dummy, time_hint = self._extract_calendar_fields(message)
                    if time_hint:
                        params.setdefault("when", time_hint)
                    params.setdefault("raw_message", message)

                # ---- RESCHEDULE ----

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
        Smart calendar extraction using dateutil.
        Splits message into title (text) and when (date/time).
        """
        try:
            from dateutil import parser as date_parser
            
            # fuzzy_with_tokens returns (datetime_obj, tokens_tuple)
            # tokens_tuple contains the parts of the string that were NOT parsed as date
            _, tokens = date_parser.parse(message, fuzzy_with_tokens=True)
            
            # Reconstruct title from non-date tokens
            # tokens is a tuple of strings that were skipped
            title_candidates = []
            for t in tokens:
                t = t.strip(" ,.-:")
                if not t:
                    continue
                # Skip meaningless connecting words common in requests
                if t.lower() in ("schedule", "a", "meeting", "event", "on", "at", "for", "with", "create", "book"):
                    continue
                title_candidates.append(t)
            
            title = " ".join(title_candidates).strip()
            
            # The 'when' is effectively the whole message, trusting the tool 
            # to re-parse it with the context of the title removed or just passing raw.
            # However, a better pattern is: pass the whole raw message as 'when' 
            # if we are confident, OR just return None for title/time and let the tool handle raw_message.
            
            # Since the Tool prefers 'when' arg if present:
            # We can reconstruct the "date part" by removing tokens from message? Hard.
            # Simpler: just pass the raw message as 'when' (time hint) 
            # BUT we need to extract a TITLE.
            
            if not title:
                title = "Meeting"
                
            # If dateutil found a date, we can just pass the original string as the time hint
            # because the tool will parse it again. The value add here is separating the Title.
            # But wait, if we pass 'message' as 'when', the tool might think the Title is part of the date? 
            # (Unlikely for "meeting", but possible for "March").
            
            # Actually, `dateutil` doesn't give us the SUBSTRING that matched. 
            # It gives us the parsed object.
            
            # Let's revert to a slightly smarter regex approach combined with valid fallback.
            # Ideally we want to identify the date string position.
            pass
        except ImportError:
            pass
        except Exception:
            pass

        # --- Improved Regex Approach ---
        # Capture "on <date expression>" or "at <time expression>" or relative words
        # and assume everything else is title.
        
        lower = message.lower()
        
        # Regex to capture time hints:
        # 1. "on 18th Dec..."
        # 2. "today", "tomorrow", "next friday"
        # 3. "at 9pm", "from 9 to 10"
        
        # We try to find the START of the time expression.
        # Common prepositions: on, at, from, by, due, in
        # Keywords: today, tomorrow, yesterday, next, this
        
        time_triggers = [
            r"\bon\s+(?:\w+\s*)+",       # on 18th dec 2025
            r"\bat\s+[\d:]+\s*(?:am|pm)?", # at 9pm
            r"\btoday\b",
            r"\btomorrow\b",
            r"\btonight\b",
            r"\bnext\s+\w+",             # next week/friday
            r"\bthis\s+\w+",             # this weekend
            r"\bin\s+\d+\s+(?:min|hour|day)s?",
        ]
        
        # We want to match the *first* occurrence of any of these, and assume
        # everything from there on is the "when" part (a simplification, but works for "Title on Date").
        # Many users say "Schedule Title on Date".
        
        earliest_idx = len(message)
        found_match = False
        
        for pattern in time_triggers:
            try:
                # We want the start index of the match
                for m in re.finditer(pattern, lower):
                     if m.start() < earliest_idx:
                         earliest_idx = m.start()
                         found_match = True
                     # We only care about the first relevant time marker
                     break 
            except Exception:
                continue

        if found_match:
            title_part = message[:earliest_idx].strip(" ,.-")
            when_part = message[earliest_idx:].strip()
            
            # Clean title
            for prefix in ["schedule a", "schedule", "create a", "create", "book a", "book", "add", "meeting", "event"]:
                if title_part.lower().startswith(prefix):
                    title_part = title_part[len(prefix):].strip()
                    
            return (title_part or None, when_part)

        return (None, None)
