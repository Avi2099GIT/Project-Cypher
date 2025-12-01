# cloud/api/assistant/agents_dir/chat_agent.py

from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime


async def run(
    message: str,
    history: List[Dict[str, Any]],
    device: Dict[str, Any],
    tools_used: List[Dict[str, Any]] | None = None,
) -> str:

    if not tools_used:
        return message

    output: List[str] = []

    for tool in tools_used:
        name = tool.get("tool")
        result = tool.get("result", {})

        if isinstance(result, dict) and result.get("status") != "ok":
            output.append(result.get("message", "An error occurred."))
            continue

        # ---------- GOOGLE CALENDAR ----------
        if name == "calendar_google":
            mode = result.get("mode")

            # LIST EVENTS
            if mode == "list":
                events = result.get("events", [])

                if not events:
                    output.append("📭 You have no upcoming events.")
                    continue

                lines = ["📅 **Upcoming events:**"]

                for ev in events:
                    title = ev.get("title", "Untitled")
                    start = ev.get("start")
                    link = ev.get("htmlLink")

                    try:
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        date_txt = dt.strftime("%d %b %Y, %I:%M %p")
                    except:
                        date_txt = start

                    lines.append(f"- **{title}** at {date_txt}\n  {link}")

                output.append("\n".join(lines))
                continue

            # CREATE EVENT
            if mode == "create":
                title = result.get("title", "Event")
                start = result.get("start")
                link = result.get("htmlLink")

                output.append(
                    f"✅ **{title} created**\n\n"
                    f"🕒 {start}\n"
                    f"📎 {link}"
                )
                continue

            # DELETE EVENT
            if mode == "delete":
                output.append("🗑️ Event removed successfully.")
                continue

        # ---------- FALLBACK ----------
        output.append(str(result))

    return "\n\n".join(output)
