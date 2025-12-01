# cloud/api/assistant/tools.py
from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime
import platform
import sys
import os
import asyncio
import string
from zoneinfo import ZoneInfo
import subprocess
import ctypes
import re

import requests  # sync HTTP client

from .tools_base import ToolContext
from .memory import memory_service


# --------------------------------------------------------------------
# HTTP helpers (run blocking requests off the event loop)
# --------------------------------------------------------------------


async def _fetch_json(
    url: str,
    params: Dict[str, Any],
    timeout: float = 8.0,
) -> Dict[str, Any]:
    """
    Run a blocking HTTP GET in a thread so we don't block the event loop.
    """
    def _do_request() -> Dict[str, Any]:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_request)


# --------------------------------------------------------------------
# Location parsing & geocoding (Open-Meteo)
# --------------------------------------------------------------------


def _extract_location_from_text(text: str) -> Optional[str]:
    """
    Very simple heuristic to pull a location name out of a sentence like:
        "What is the weather in Bangalore right now?"
        "Time in Paris?"
    We deliberately keep this dumb-but-robust and let the
    weather/time APIs handle fuzzy city names.
    """
    lower = text.lower()
    if " in " not in lower:
        return None

    after = lower.split(" in ", 1)[1]

    # Strip common trailing fluff
    for tail in [" right now", " now", " today", " currently", " outside", " please"]:
        if tail in after:
            after = after.split(tail, 1)[0]

    # Strip punctuation
    after = after.strip().strip("".join(ch for ch in string.punctuation))

    if not after:
        return None

    # Use title-case for nicer names, APIs don’t really care
    return after.title()


async def _geocode_location(raw_location: str) -> Dict[str, Any]:
    """
    Resolve a free-text location name into lat/lon/timezone using
    Open-Meteo's free Geocoding API (no API key required).

    Docs: https://open-meteo.com/en/docs/geocoding-api
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": raw_location,
        "count": 1,
        "language": "en",
        "format": "json",
    }

    data = await _fetch_json(url, params)
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Could not geocode location: {raw_location!r}")

    r = results[0]
    return {
        "name": r.get("name") or raw_location,
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        # Not all responses include timezone, so we handle that gracefully later
        "timezone": r.get("timezone"),
        "country": r.get("country"),
    }


# --------------------------------------------------------------------
# TIME TOOL — accurate global time using IANA tz db
# --------------------------------------------------------------------


async def time_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Get current time.

    Behavior:
      - If city provided: resolve timezone via Open-Meteo geocoding + IANA tz
      - Use Python's zoneinfo (not weather timestamps)
      - If no city: use server-local timezone

    Args (optional):
      - location / city / place: free-text city name
    """
    location = (
        (args.get("location") or args.get("city") or args.get("place") or "").strip()
    )

    # Try inferring from user message
    if not location:
        raw_message = str(ctx.get("message") or "")
        inferred = _extract_location_from_text(raw_message)
        if inferred:
            location = inferred

    # If still no location → server time
    if not location:
        now = datetime.now().astimezone()
        return {
            "kind": "local",
            "timezone": str(now.tzinfo),
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "iso": now.isoformat(),
        }

    # Resolve city to timezone
    geo = await _geocode_location(location)

    tz_name = geo.get("timezone")
    if not tz_name:
        return {
            "status": "error",
            "message": f"Timezone unknown for {location!r}",
        }

    now = datetime.now(ZoneInfo(tz_name))

    return {
        "kind": "city",
        "query": location,
        "resolved_name": geo["name"],
        "timezone": tz_name,
        "country": geo.get("country"),
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "iso": now.isoformat(),
    }


# --------------------------------------------------------------------
# WEATHER TOOL — real-time data via Open-Meteo
# --------------------------------------------------------------------


async def weather_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Get live weather using Open-Meteo.

    Note:
      'observed_at' is the last sensor update time (not the wall-clock time).

    Args:
      - location / city / place (optional but strongly recommended)
        If omitted we try to infer from ctx.message.
    """
    location = (
        (args.get("location") or args.get("city") or args.get("place") or "").strip()
    )

    # Try inferring from user message
    if not location:
        raw_message = str(ctx.get("message") or "")
        inferred = _extract_location_from_text(raw_message)
        if inferred:
            location = inferred

    if not location:
        return {
            "status": "error",
            "message": "Please specify a city, e.g. 'weather in Bangalore'.",
        }

    geo = await _geocode_location(location)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "weather_code,wind_speed_10m"
        ),
        "timezone": "auto",
    }

    data = await _fetch_json(url, params)
    current = data.get("current") or {}

    timezone = data.get("timezone") or geo.get("timezone") or "unknown"

    return {
        "status": "ok",
        "resolved_name": geo["name"],
        "country": geo.get("country"),
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "timezone": timezone,

        # Weather metrics
        "temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "weather_code": current.get("weather_code"),

        # Observation timestamp (NOT guaranteed to be 'now')
        "observed_at": current.get("time"),
    }


# --------------------------------------------------------------------
# WEB SEARCH TOOL — DuckDuckGo Instant Answer
# --------------------------------------------------------------------


async def web_search_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Lightweight web search via DuckDuckGo's free Instant Answer API.

    Args:
        - query / q: search query string
    """

    query = (args.get("query") or args.get("q") or "").strip()

    # Fallback: use entire user message
    if not query:
        query = str(ctx.get("message") or "").strip()

    if not query:
        return {"status": "error", "message": "No search query provided."}

    # -------------------------------
    # Fetch DuckDuckGo result
    # -------------------------------
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
        "no_redirect": 1,
    }

    data = await _fetch_json(url, params)

    abstract = data.get("AbstractText") or ""
    related_raw = data.get("RelatedTopics") or []
    related: List[Dict[str, Any]] = []

    for item in related_raw[:5]:
        if isinstance(item, dict):
            text = item.get("Text")
            link = item.get("FirstURL")
            if text and link:
                related.append({"title": text, "url": link})

    # -------------------------------
    # Auto-open browser if requested
    # -------------------------------
    opened_browser = False
    msg = (ctx.get("message") or "").lower()

    if any(k in msg for k in ["open", "chrome", "browser", "search"]):
        import webbrowser
        google_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(google_url)
        opened_browser = True

    # -------------------------------
    # Return AFTER browser action
    # -------------------------------
    return {
        "status": "ok",
        "query": query,
        "abstract": abstract,
        "related": related,
        "browser_opened": opened_browser,
    }



# --------------------------------------------------------------------
# SYSTEM INFO TOOL
# --------------------------------------------------------------------


async def system_info_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, str]:
    """
    Return basic OS / Python info for the runtime where Cypher-cloud is running.
    """
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "cwd": os.getcwd(),
    }


# --------------------------------------------------------------------
# OS CONTROL (SAFE) — Windows automation
# --------------------------------------------------------------------


_ALLOWED_APPS: Dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "edge": "msedge",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "vscode": "code"
}


async def os_control_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Safe OS control for Windows.

    Supported actions:
      - open_app (notepad, calculator)
      - lock
      - list_processes

    Args:
      - action: optional explicit action
      - app: app name (for open_app)
    """
    if platform.system().lower() != "windows":
        return {
            "status": "error",
            "message": "OS control is only implemented for Windows.",
        }

    message = str(ctx.get("message") or "")
    lower = message.lower()

    action: Optional[str] = (args.get("action") or "").strip() or None
    # -------------------------------
    # Detect direct URLs
    # -------------------------------
    if "http://" in lower or "https://" in lower:
        import re, webbrowser
        url = re.search(r"(https?://[^\s]+)", message)
        if url:
            webbrowser.open(url.group(1))
            return {"status": "ok", "action": "open_url", "url": url.group(1)}


    # Heuristics if action is not explicitly provided
    if not action:
        if any(kw in lower for kw in ["lock my computer", "lock the pc", "lock screen"]):
            action = "lock"
        elif "open" in lower or "launch" in lower or "start" in lower:
            action = "open_app"
        elif ("show" in lower and "process" in lower) or "list processes" in lower:
            action = "list_processes"

    if not action:
        return {
            "status": "error",
            "message": "No OS action recognized from the request.",
        }
    
    if action == "open_url":
        import webbrowser
        webbrowser.open(args["url"])
        return {"status":"ok","opened":args["url"]}

    # -------------------------------
    # Known websites
    # -------------------------------
    WEBSITE_ALIASES = {
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "google": "https://www.google.com",
        "chatgpt": "https://chatgpt.com/",
        "my website": "https://avinash-karri.netlify.app/",
        # Cypher dashboard / schedule
        "schedule": "http://localhost:8501",
        "my schedule": "http://localhost:8501",
        "dashboard": "http://localhost:8501",
        "cypher dashboard": "http://localhost:8501"
    }

    for name, url in WEBSITE_ALIASES.items():
        if name in lower:
            import webbrowser
            webbrowser.open(url)
            return {"status": "ok", "action": "open_url", "url": url}


    # ---------- open_app ----------
    if action == "open_app":
        app = (args.get("app") or "").lower().strip()

        if not app:
            # Try to infer from message text
            for spoken in _ALLOWED_APPS.keys():
                if spoken in lower:
                    app = spoken
                    break

        if not app:
            return {
                "status": "error",
                "message": "No supported application name found (supported: notepad, calculator).",
            }

        cmd = _ALLOWED_APPS.get(app)
        if not cmd:
            return {
                "status": "error",
                "message": f"Application '{app}' is not allowed.",
            }

        try:
            # Launch whitelisted app
            subprocess.Popen([cmd])
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to open {app}: {e}",
            }

        return {
            "status": "ok",
            "action": "open_app",
            "app": app,
        }

    # ---------- lock ----------
    if action == "lock":
        try:
            ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
            return {
                "status": "ok",
                "action": "lock",
            }
        except Exception as e:
            return {
                "status": "error",
                "action": "lock",
                "message": str(e),
            }

    # ---------- list_processes ----------
    if action == "list_processes":
        try:
            output = subprocess.check_output(["tasklist"], text=True, errors="ignore")
            # Avoid overloading responses — truncate a bit
            if len(output) > 4000:
                output = output[:4000] + "\n...[truncated]..."
            return {
                "status": "ok",
                "action": "list_processes",
                "output": output,
            }
        except Exception as e:
            return {
                "status": "error",
                "action": "list_processes",
                "message": str(e),
            }

    return {
        "status": "error",
        "message": f"Unsupported os_control action: {action}",
    }


# --------------------------------------------------------------------
# OS CONTROL (SAFE) — list directory
# --------------------------------------------------------------------


async def os_list_dir_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Very conservative 'OS control' tool: list files in a directory.

    Args:
        - path: directory path (optional, default=".")
    """
    path = (args.get("path") or ".").strip() or "."
    try:
        entries = os.listdir(path)
        return {
            "status": "ok",
            "path": os.path.abspath(path),
            "entries": entries,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "path": os.path.abspath(path),
        }


# --------------------------------------------------------------------
# NOTES TOOL (memory-backed)
# --------------------------------------------------------------------


async def notes_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Manage simple per-device notes.

    Args:
        action: "add" | "list" | "clear"
        content: note text (for add)
    """
    action = (args.get("action") or "add").lower()
    content = (args.get("content") or "").strip()

    device = ctx.get("device") or {"device_id": "local-dev"}

    if action == "add":
        if not content:
            return {"status": "error", "message": "No content provided for note."}
        memory_service.add_note(device, content)
        return {"status": "ok", "message": "Note added."}

    elif action == "list":
        notes: List[str] = memory_service.get_notes(device)
        return {"status": "ok", "notes": notes}

    elif action == "clear":
        memory_service.clear_notes(device)
        return {"status": "ok", "message": "All notes cleared."}

    else:
        return {"status": "error", "message": f"Unknown notes action: {action}"}


# --------------------------------------------------------------------
# TASKS / REMINDERS TOOL (memory-backed)
# --------------------------------------------------------------------


async def tasks_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Manage a simple per-device todo list.

    Args:
        action: "add" | "list" | "complete" | "clear"
        text: task text (for add)
        id: task id (for complete)
    """
    action = (args.get("action") or "add").lower()
    device = ctx.get("device") or {"device_id": "local-dev"}

    if action == "add":
        text = (args.get("text") or "").strip()
        if not text:
            return {"status": "error", "message": "No task text provided."}
        task = memory_service.add_task(device, text)
        return {"status": "ok", "task": task}

    elif action == "list":
        tasks = memory_service.list_tasks(device)
        return {"status": "ok", "tasks": tasks}

    elif action == "complete":
        try:
            task_id = int(args.get("id"))
        except Exception:
            return {"status": "error", "message": "Invalid or missing task id."}
        ok = memory_service.complete_task(device, task_id)
        if not ok:
            return {"status": "error", "message": f"No task found with id {task_id}."}
        tasks = memory_service.list_tasks(device)
        return {"status": "ok", "tasks": tasks}

    elif action == "clear":
        memory_service.clear_tasks(device)
        return {"status": "ok", "message": "All tasks cleared."}

    else:
        return {"status": "error", "message": f"Unknown tasks action: {action}"}


# --------------------------------------------------------------------
# CALENDAR TOOL — simple smart parser (per-device store)
# --------------------------------------------------------------------


# Very lightweight in-memory calendar store keyed by device_id
_CALENDAR_STORE: Dict[str, List[Dict[str, Any]]] = {}


def _get_calendar_bucket(device: Dict[str, Any]) -> List[Dict[str, Any]]:
    device_id = device.get("device_id") or "local-dev"
    if device_id not in _CALENDAR_STORE:
        _CALENDAR_STORE[device_id] = []
    return _CALENDAR_STORE[device_id]


async def calendar_tool(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """
    Very simple calendar / reminders tool.

    Actions:
      - add (default)
      - list
      - clear

    It tries to be forgiving:
      "Add calendar event Meeting at 5 PM"
      "Add meeting with John tomorrow at 3 PM"
      "Show my calendar"
    """
    device = ctx.get("device") or {"device_id": "local-dev"}
    events = _get_calendar_bucket(device)

    message = str(ctx.get("message") or "")
    lower = message.lower()

    action = (args.get("action") or "").lower()

    if not action:
        # Try to infer from the natural language
        if any(kw in lower for kw in ["show my calendar", "show calendar", "list events", "what's on my calendar", "whats on my calendar"]):
            action = "list"
        elif "clear calendar" in lower or "delete all events" in lower:
            action = "clear"
        else:
            action = "add"

    # ---------------- list ----------------
    if action == "list":
        return {"status": "ok", "events": events}

    # ---------------- clear ---------------
    if action == "clear":
        events.clear()
        return {"status": "ok", "message": "All calendar events cleared."}

    # ---------------- add -----------------
    if action == "add":
        title: Optional[str] = (args.get("title") or "").strip() or None
        when: Optional[str] = (args.get("when") or "").strip() or None

        # If not provided explicitly, try to extract from the message
        if not title:
            cleaned = message

            # Strip some leading command phrases
            prefixes = [
                "add calendar event",
                "create calendar event",
                "add event",
                "create event",
                "schedule event",
                "schedule a meeting",
                "schedule meeting",
                "add meeting",
                "add reminder",
                "set reminder",
            ]
            for pfx in prefixes:
                if cleaned.lower().startswith(pfx):
                    cleaned = cleaned[len(pfx):]
                    break

            cleaned = cleaned.strip().strip(".").strip()

            # Split around " at " (case-insensitive)
            match = re.split(r"\bat\b", cleaned, maxsplit=1, flags=re.IGNORECASE)
            if len(match) == 2:
                maybe_title = match[0].strip(" ,.")
                maybe_time = match[1].strip(" ,.")
                if maybe_title:
                    title = maybe_title
                if maybe_time and not when:
                    when = maybe_time

            if not title:
                title = cleaned or None

        if not title:
            return {
                "status": "error",
                "message": "No event title could be extracted.",
            }

        # If time still unknown, mark as unspecified
        when = when or "unspecified"

        event_id = len(events) + 1
        event = {
            "id": event_id,
            "title": title,
            "when": when,
            "raw_text": message,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        events.append(event)

        return {"status": "ok", "event": event}

    return {
        "status": "error",
        "message": f"Unknown calendar action: {action}",
    }
