# cloud/api/assistant/tools_google_calendar.py
from __future__ import annotations

from typing import Dict, Any
from datetime import datetime, timedelta, timezone, time
import re

from googleapiclient.discovery import build
from dateutil import parser as date_parser

from cloud.api.assistant.google_auth import get_google_creds


def _get_calendar_service():
    """Build a Google Calendar API service using stored / refreshed user creds."""
    creds = get_google_creds()
    return build("calendar", "v3", credentials=creds)


# ---------------------------------------------------
# TIME PARSING HELPERS
# ---------------------------------------------------

_MONTH_PATTERN = re.compile(
    r"\b("
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"january|february|march|april|june|july|august|september|october|november|december"
    r")\b",
    re.IGNORECASE,
)


def _has_explicit_date(text: str) -> bool:
    """Return True if the text obviously contains a calendar date."""
    t = text.lower()
    if re.search(r"\d{4}-\d{2}-\d{2}", t):          # 2025-12-03
        return True
    if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", t):    # 03/12/25 or 03/12/2025
        return True
    if _MONTH_PATTERN.search(t):                    # month name present
        return True
    if re.search(r"\d{1,2}(st|nd|rd|th)\b", t):     # 3rd, 21st, etc.
        return True
    return False


def _parse_time_only(text: str, base_date: datetime.date) -> datetime:
    """
    Parse only the time-of-day from text and combine with base_date.
    Never inherits current minutes when user says only '9pm' / '11 am'.
    """
    text = text.strip()
    if not text:
        # default to 09:00 if only date is specified
        t = time(hour=9, minute=0)
    else:
        dt = date_parser.parse(text, fuzzy=True, default=datetime(2000, 1, 1))
        t = dt.time()

    lower = text.lower()
    if (("am" in lower or "pm" in lower) and ":" not in lower):
        # e.g. "9pm" -> 21:00, not 21:10 or whatever current minute is
        t = t.replace(minute=0, second=0, microsecond=0)

    return datetime.combine(base_date, t)


def _parse_human_time(when_str: str) -> str | None:
    """
    FIXED VERSION:

    - If phrase contains an explicit calendar date (Dec 3, 2025, 03/12/2025, etc):
        → let dateutil parse the full phrase as-is.
    - Else if it contains relative words (tomorrow/today/tonight):
        → set the date manually and only parse the time part.
    - Else:
        → treat as a time-only phrase for today.

    All outputs are ISO 8601 in UTC.
    """
    when_str = (when_str or "").strip()
    if not when_str:
        return None

    lower = when_str.lower()
    now = datetime.now()
    local_tz = now.astimezone().tzinfo or timezone.utc

    # -------------------------
    # 1) Explicit calendar date
    # -------------------------
    if _has_explicit_date(when_str):
        try:
            dt = date_parser.parse(when_str, fuzzy=True)
        except Exception:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=local_tz)
        return dt.astimezone(timezone.utc).isoformat()

    # -------------------------
    # 2) Relative dates
    # -------------------------
    if "tomorrow" in lower or "today" in lower or "tonight" in lower:
        base_date = now.date()

        if "tomorrow" in lower:
            base_date = base_date + timedelta(days=1)

        # Strip relative word from the time phrase
        time_text = re.sub(
            r"\b(tomorrow|today|tonight)\b", "", lower, flags=re.IGNORECASE
        ).strip()

        dt_local = _parse_time_only(time_text, base_date)
        dt_local = dt_local.replace(tzinfo=local_tz)
        return dt_local.astimezone(timezone.utc).isoformat()

    # -------------------------
    # 3) Time-only → today
    # -------------------------
    dt_local = _parse_time_only(lower, now.date())
    dt_local = dt_local.replace(tzinfo=local_tz)
    return dt_local.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------
# MAIN TOOL
# ---------------------------------------------------

async def calendar_google_tool(args: Dict[str, Any], ctx: dict) -> Dict[str, Any]:
    """
    Google Calendar integration.

    Actions:
      - list / show / upcoming   → next 30 days
      - create / add / schedule  → create a new 30-minute event
      - delete / remove / cancel → delete an event
      - update / reschedule      → move an event to a new time
    """
    service = _get_calendar_service()

    raw_msg = str(ctx.get("message") or "")
    action = (args.get("action") or "").lower().strip()

    if not action:
        # Fallback: infer from message if not explicitly set
        if "show" in raw_msg.lower() or "upcoming" in raw_msg.lower():
            action = "list"
        else:
            action = "create"

    # ------------------- LIST EVENTS (next 30 days) -------------------
    if action in ("list", "show", "upcoming"):
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=30)).isoformat()

        results = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = results.get("items", [])

        parsed = []
        for ev in events:
            parsed.append(
                {
                    "id": ev.get("id"),
                    "title": ev.get("summary") or "Untitled Event",
                    "start": ev.get("start", {}).get("dateTime")
                    or ev.get("start", {}).get("date"),
                    "end": ev.get("end", {}).get("dateTime")
                    or ev.get("end", {}).get("date"),
                    "htmlLink": ev.get("htmlLink"),
                }
            )

        return {
            "status": "ok",
            "mode": "list",
            "count": len(parsed),
            "events": parsed,
        }

    # ------------------- CREATE EVENT -------------------
    if action in ("create", "add", "schedule"):
        title = (args.get("title") or "").strip() or "Cypher Event"

        # IMPORTANT: always parse the FULL user message for time
        when_iso = args.get("when_iso")
        if not when_iso:
            when_iso = _parse_human_time(raw_msg)

        if not when_iso:
            return {
                "status": "error",
                "mode": "create",
                "message": (
                    "I couldn't understand the event time. "
                    "Try something like 'tomorrow at 6 PM' or "
                    "'on 3rd December 2025 at 9 PM'."
                ),
            }

        dt = datetime.fromisoformat(when_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        end_dt = dt + timedelta(minutes=30)

        event_body = {
            "summary": title,
            "start": {"dateTime": dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }

        created = service.events().insert(
            calendarId="primary", body=event_body
        ).execute()

        return {
            "status": "ok",
            "mode": "create",
            "id": created.get("id"),
            "title": created.get("summary"),
            "start": created.get("start", {}).get("dateTime")
            or created.get("start", {}).get("date"),
            "end": created.get("end", {}).get("dateTime")
            or created.get("end", {}).get("date"),
            "htmlLink": created.get("htmlLink"),
        }

    # ------------------- SMART DELETE EVENT -------------------
    if action in ("delete", "remove", "cancel"):
        query = (args.get("query") or "").lower()

        now = datetime.now(timezone.utc).isoformat()

        events = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=50,
            singleEvents=True,
            orderBy="startTime",
        ).execute().get("items", [])

        if not events:
            return {"status": "error", "message": "No upcoming events found."}

        matched = []
        for ev in events:
            title = (ev.get("summary") or "").lower()
            start = ev.get("start", {}).get("dateTime", "") or ""
            if query and (query in title or query in start.lower()):
                matched.append(ev)

        target = matched[0] if matched else events[0]

        service.events().delete(
            calendarId="primary", eventId=target["id"]
        ).execute()

        return {
            "status": "ok",
            "mode": "delete",
            "deleted": {
                "title": target.get("summary"),
                "start": target.get("start"),
            },
        }

    # ------------------- RESCHEDULE EVENT -------------------
    if action in ("update", "reschedule", "move"):
        # 1) Figure out the NEW time phrase
        raw = raw_msg

        # Explicit override from args if we ever add it later
        new_time_phrase = (args.get("new_time") or "").strip()

        if not new_time_phrase:
            # Split on "to" and take the right-hand side as the NEW time
            parts = re.split(r"\bto\b", raw, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                new_time_phrase = parts[1].strip()
            else:
                # Fallback: use whole message (worst-case, same behavior as before)
                new_time_phrase = raw

        new_time_iso = _parse_human_time(new_time_phrase)
        if not new_time_iso:
            return {
                "status": "error",
                "message": "I couldn't understand the new time for reschedule.",
            }

        new_dt = datetime.fromisoformat(new_time_iso)
        if new_dt.tzinfo is None:
            new_dt = new_dt.replace(tzinfo=timezone.utc)
        new_end_dt = new_dt + timedelta(minutes=30)

        # 2) For now: pick the earliest upcoming event and move it
        now = datetime.now(timezone.utc).isoformat()
        events = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=30,
            singleEvents=True,
            orderBy="startTime",
        ).execute().get("items", [])

        if not events:
            return {
                "status": "error",
                "message": "No upcoming event found to reschedule.",
            }

        target = events[0]

        # Ensure we have datetime start/end
        start_obj = target.get("start", {})
        end_obj = target.get("end", {})
        start_obj["dateTime"] = new_dt.isoformat()
        start_obj.pop("date", None)
        end_obj["dateTime"] = new_end_dt.isoformat()
        end_obj.pop("date", None)
        target["start"] = start_obj
        target["end"] = end_obj

        updated = service.events().update(
            calendarId="primary", eventId=target["id"], body=target
        ).execute()

        return {
            "status": "ok",
            "mode": "update",
            "rescheduled": {
                "title": updated.get("summary"),
                "new_time": updated.get("start", {}).get("dateTime")
                or updated.get("start", {}).get("date"),
                "htmlLink": updated.get("htmlLink"),
            },
        }

    # ------------------- UNKNOWN ACTION -------------------
    return {
        "status": "error",
        "message": f"Unknown calendar action: {action}",
    }
