from __future__ import annotations

from typing import Dict, Any, Tuple, List
from datetime import datetime, timedelta, timezone, date as dt_date, time as dt_time
import re

from dateutil import parser as date_parser
from googleapiclient.discovery import build

from cloud.api.assistant.google_auth import get_google_creds


# -------------------------------------------------------------------
# SERVICE FACTORY
# -------------------------------------------------------------------

def _get_calendar_service():
    """Build a Google Calendar API service using stored / refreshed user creds."""
    creds = get_google_creds()
    return build("calendar", "v3", credentials=creds)


# -------------------------------------------------------------------
# DATE / TIME HELPERS
# -------------------------------------------------------------------

_MONTH_PATTERN = re.compile(
    r"\b("
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"january|february|march|april|may|june|july|august|september|october|november|december"
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


def _local_tz():
    now = datetime.now()
    return now.astimezone().tzinfo or timezone.utc


# -------------------------------------------------------------------
# RANGE RESOLUTION
# -------------------------------------------------------------------

def _resolve_range_from_mode(mode: str) -> Tuple[datetime, datetime]:
    """
    Convert canonical range_mode into [start, end) UTC datetimes.
    """
    now_utc = datetime.now(timezone.utc)
    start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    mode = (mode or "").lower().strip()

    if mode == "today":
        return start, start + timedelta(days=1)

    if mode == "tomorrow":
        s = start + timedelta(days=1)
        return s, s + timedelta(days=1)

    if mode == "yesterday":
        s = start - timedelta(days=1)
        return s, start

    if mode == "today_tomorrow":
        return start, start + timedelta(days=2)

    if mode == "this_week":
        # current day + next 7 days
        return start, start + timedelta(days=7)

    if mode == "this_month":
        # very rough month window
        return start, start + timedelta(days=30)

    # Fallback = next 7 days
    return now_utc, now_utc + timedelta(days=7)


def _resolve_range_from_text(text: str) -> Tuple[datetime, datetime]:
    """
    Interpret natural language ranges when range_mode is not provided.

    Supports:
      - today / tomorrow / yesterday
      - this week / this month
      - phrases with explicit date → that single day
      - fallback: [now, now+7 days]
    """
    text = (text or "").lower()
    now_utc = datetime.now(timezone.utc)
    start_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    # Relative keywords
    if "today and tomorrow" in text or "today & tomorrow" in text:
        return start_today, start_today + timedelta(days=2)
    if "today" in text and "tomorrow" in text:
        return start_today, start_today + timedelta(days=2)
    if "today" in text:
        return start_today, start_today + timedelta(days=1)
    if "tomorrow" in text:
        s = start_today + timedelta(days=1)
        return s, s + timedelta(days=1)
    if "yesterday" in text:
        s = start_today - timedelta(days=1)
        return s, start_today
    if "this week" in text:
        return start_today, start_today + timedelta(days=7)
    if "this month" in text:
        return start_today, start_today + timedelta(days=30)

    # Explicit calendar date → that day
    if _has_explicit_date(text):
        try:
            dt = date_parser.parse(text, fuzzy=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_local_tz())
            dt_utc = dt.astimezone(timezone.utc)
            day_start = dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            return day_start, day_start + timedelta(days=1)
        except Exception:
            pass

    # Final fallback → next 7 days
    return now_utc, now_utc + timedelta(days=7)


def _resolve_range(args: Dict[str, Any]) -> Tuple[datetime, datetime]:
    """
    Prefer explicit range_mode from EntityAgent; otherwise infer from raw_message/when.
    """
    range_mode = (args.get("range_mode") or "").lower().strip()
    raw = str(args.get("raw_message") or "") or str(args.get("when") or "")

    if range_mode:
        return _resolve_range_from_mode(range_mode)

    return _resolve_range_from_text(raw)


# -------------------------------------------------------------------
# EVENT TIME PARSING (for CREATE / UPDATE)
# -------------------------------------------------------------------

def _parse_event_time(args: Dict[str, Any]) -> datetime | None:
    """
    Parse a single event datetime from args['when'] or args['raw_message'].

    Supports:
      - 'today at 7pm', 'tomorrow 10:30 am'
      - 'on 5th December 2025 at 7pm'
      - '6 December 2025 19:00'
      - 'at 7pm' (defaults to today)
    """
    when_str = (args.get("when") or args.get("raw_message") or "").strip()
    if not when_str:
        return None

    local_tz = _local_tz()
    now = datetime.now(local_tz)

    # If there is an explicit date, let dateutil parse full phrase
    if _has_explicit_date(when_str):
        try:
            dt = date_parser.parse(when_str, fuzzy=True)
        except Exception:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=local_tz)
        return dt.astimezone(timezone.utc)

    # Relative: today / tomorrow
    lower = when_str.lower()
    base_date: dt_date = now.date()

    if "tomorrow" in lower:
        base_date = base_date + timedelta(days=1)
        # strip the word to leave only time part
        time_part = re.sub(r"\btomorrow\b", "", lower, flags=re.IGNORECASE).strip()
    elif "today" in lower:
        time_part = re.sub(r"\btoday\b", "", lower, flags=re.IGNORECASE).strip()
    else:
        time_part = lower

    if not time_part:
        # If only date-like info, assume 09:00
        t = dt_time(hour=9, minute=0)
        dt_local = datetime.combine(base_date, t).replace(tzinfo=local_tz)
        return dt_local.astimezone(timezone.utc)

    try:
        # parse *time only*, default date 2000-01-01
        dt_time_only = date_parser.parse(
            time_part,
            fuzzy=True,
            default=datetime(2000, 1, 1, 9, 0),
        )
        t = dt_time_only.time()

        # if '7pm' style (am/pm, no colon) → snap minutes to :00
        lower_time = time_part.lower()
        if (("am" in lower_time or "pm" in lower_time) and ":" not in lower_time):
            t = t.replace(minute=0, second=0, microsecond=0)

        dt_local = datetime.combine(base_date, t).replace(tzinfo=local_tz)
        return dt_local.astimezone(timezone.utc)
    except Exception:
        return None


# -------------------------------------------------------------------
# NORMALIZATION HELPERS
# -------------------------------------------------------------------

def _normalize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    start = ev.get("start", {}) or {}
    end = ev.get("end", {}) or {}
    return {
        "id": ev.get("id"),
        "title": ev.get("summary") or "Untitled event",
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "htmlLink": ev.get("htmlLink"),
        "eventType": ev.get("eventType", "default"),
    }


def _is_deletable_event(ev: Dict[str, Any]) -> bool:
    """
    Avoid deleting non-editable types like 'birthday' events.
    """
    event_type = ev.get("eventType") or ev.get("kind")  # kind is usually 'calendar#event'
    if str(event_type).lower() == "birthday":
        return False
    return True


# -------------------------------------------------------------------
# MAIN TOOL ENTRYPOINT
# -------------------------------------------------------------------

async def calendar_google_tool(args: Dict[str, Any], ctx: dict) -> Dict[str, Any]:
    """
    Google Calendar integration.

    Inputs (from EntityAgent/Planner):
      args = {
        "action": "create" | "list" | "delete" | "update",
        "range_mode": optional canonical range ("today", "this_week", etc.),
        "when": string (time phrase),
        "raw_message": original user message,
        ...
      }

    Returns structured dict with "status" key.
    """
    try:
        service = _get_calendar_service()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to create Google Calendar service: {e}",
        }

    action = (args.get("action") or "").lower().strip()
    raw_msg = str(args.get("raw_message") or "")

    # ------------------ LIST EVENTS ------------------
    if action == "list":
        try:
            start_dt, end_dt = _resolve_range(args)
            events_resp = service.events().list(
                calendarId="primary",
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            ).execute()
            events_raw = events_resp.get("items", []) or []

            events = [_normalize_event(ev) for ev in events_raw]

            return {
                "status": "ok",
                "mode": "list",
                "range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
                "count": len(events),
                "events": events,
            }
        except Exception as e:
            return {
                "status": "error",
                "mode": "list",
                "message": f"Error while listing events: {e}",
            }

    # ------------------ CREATE EVENT ------------------
    if action == "create":
        dt_utc = _parse_event_time(args)
        if dt_utc is None:
            return {
                "status": "error",
                "mode": "create",
                "message": (
                    "I couldn't understand the event time. "
                    "Try something like 'tomorrow at 6 PM' or "
                    "'on 5th December 2025 at 7 PM'."
                ),
            }

        end_dt = dt_utc + timedelta(minutes=30)

        title = (args.get("title") or "").strip() or "Cypher Event"

        event_body = {
            "summary": title,
            "start": {"dateTime": dt_utc.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }

        try:
            created = service.events().insert(
                calendarId="primary",
                body=event_body,
            ).execute()

            created_norm = _normalize_event(created)

            return {
                "status": "ok",
                "mode": "create",
                "id": created_norm["id"],
                "title": created_norm["title"],
                "start": created_norm["start"],
                "end": created_norm["end"],
                "htmlLink": created_norm["htmlLink"],
            }
        except Exception as e:
            return {
                "status": "error",
                "mode": "create",
                "message": f"Error while creating event: {e}",
            }

    # ------------------ DELETE (BULK) ------------------
    if action == "delete":
        try:
            start_dt, end_dt = _resolve_range(args)

            events_resp = service.events().list(
                calendarId="primary",
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=100,
            ).execute()
            events_raw = events_resp.get("items", []) or []

            deletable = [ev for ev in events_raw if _is_deletable_event(ev)]

            deleted: List[Dict[str, Any]] = []
            for ev in deletable:
                try:
                    service.events().delete(
                        calendarId="primary",
                        eventId=ev["id"],
                    ).execute()
                    deleted.append(_normalize_event(ev))
                except Exception:
                    # Skip events we can't delete (permissions, birthday, etc.)
                    continue

            return {
                "status": "ok",
                "mode": "delete",
                "deleted_count": len(deleted),
                "deleted_events": deleted,
                "range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "mode": "delete",
                "message": f"Error while deleting events: {e}",
            }

    # ------------------ UPDATE (RESCHEDULE, FUTURE) ------------------
    if action in ("update", "reschedule", "move"):
        # For now not implemented; we just signal this cleanly.
        return {
            "status": "error",
            "mode": "update",
            "message": "Rescheduling events is not implemented yet.",
        }

    # ------------------ UNKNOWN ACTION ------------------
    return {
        "status": "error",
        "message": f"Unknown calendar action: {action or 'None'}",
    }
