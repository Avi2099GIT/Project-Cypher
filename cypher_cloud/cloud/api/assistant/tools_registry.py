# cloud/api/assistant/tools_registry.py
from __future__ import annotations

from typing import Dict, Any, List, Optional

from .tools_base import RegisteredTool, ToolContext
from .tools import (
    time_tool,
    system_info_tool,
    weather_tool,
    web_search_tool,
    os_list_dir_tool,
    os_control_tool,
    notes_tool,
    tasks_tool,
    calendar_tool,
)


class ToolRegistry:
    """
    In-memory registry of tools.

    Later:
    - You can persist this
    - Or load from plugin descriptors, MCP, etc.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool with name '{tool.name}' already exists")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[RegisteredTool]:
        return self._tools.get(name)

    def list(self) -> List[RegisteredTool]:
        return list(self._tools.values())

    async def call(
        self,
        name: str,
        args: Dict[str, Any],
        ctx: Optional[ToolContext] = None,
    ) -> Any:
        ctx = ctx or ToolContext()
        tool = self.get(name)

        if not tool:
            raise ValueError(f"Unknown tool: {name}")

        return await tool(args=args, ctx=ctx)


# ---------------------------
# Global singleton registry
# ---------------------------
tool_registry = ToolRegistry()
_registered = False


def register_builtin_tools() -> None:
    """
    Register built-in tools so the planner has something to call.

    Tools:

    - echo
    - summarize
    - time
    - weather
    - system_info
    - web_search
    - os_list_dir
    - os_control
    - notes
    - tasks
    - calendar
    """
    global _registered
    if _registered:
        return
    _registered = True

    # ---------------- echo ----------------
    async def echo_tool(args: Dict[str, Any], ctx: ToolContext) -> str:
        text = args.get("text") or ""
        return f"[echo] {text}"

    tool_registry.register(
        RegisteredTool(
            name="echo",
            description="Echoes back the provided text. Args: text.",
            func=echo_tool,
        )
    )

    # ------------- summarize --------------
    async def summarize_tool(args: Dict[str, Any], ctx: ToolContext) -> str:
        text = args.get("text") or ""
        if len(text) <= 200:
            return f"[summary] {text}"
        return f"[summary] {text[:200]}..."

    tool_registry.register(
        RegisteredTool(
            name="summarize",
            description="Summarizes a piece of text (placeholder implementation). Args: text.",
            func=summarize_tool,
        )
    )

    # --------------- time -----------------
    tool_registry.register(
        RegisteredTool(
            name="time",
            description=(
                "Get the current time. Args (optional): "
                "location/city/place for city-specific local time; "
                "otherwise returns server-local time."
            ),
            func=time_tool,
        )
    )

    # -------------- weather ---------------
    tool_registry.register(
        RegisteredTool(
            name="weather",
            description=(
                "Get current weather for a city using Open-Meteo. "
                "Args: location/city/place (string)."
            ),
            func=weather_tool,
        )
    )

    # ----------- system_info --------------
    tool_registry.register(
        RegisteredTool(
            name="system_info",
            description="Get OS, Python, and runtime info for the Cypher cloud process.",
            func=system_info_tool,
        )
    )

    # ----------- web_search ---------------
    tool_registry.register(
        RegisteredTool(
            name="web_search",
            description=(
                "Search the web using DuckDuckGo Instant Answer API. "
                "Args: query/q (string). Returns abstract + related links."
            ),
            func=web_search_tool,
        )
    )

    # ----------- os_list_dir --------------
    tool_registry.register(
        RegisteredTool(
            name="os_list_dir",
            description=(
                "List files in a directory on the Cypher cloud runtime. "
                "Args: path (string, optional, default='.')."
            ),
            func=os_list_dir_tool,
        )
    )

    # ----------- os_control ----------------
    tool_registry.register(
        RegisteredTool(
            name="os_control",
            description=(
                "Safe Windows OS automation. "
                "Supports actions: open_app (notepad, calculator), "
                "lock, list_processes."
            ),
            func=os_control_tool,
        )
    )

    # ---------------- notes ---------------
    tool_registry.register(
        RegisteredTool(
            name="notes",
            description=(
                "Manage simple notes in Cypher's memory. "
                "Args: action ('add'|'list'|'clear'), content (for 'add')."
            ),
            func=notes_tool,
        )
    )

    # ---------------- tasks ---------------
    tool_registry.register(
        RegisteredTool(
            name="tasks",
            description=(
                "Manage simple tasks / reminders. "
                "Args: action ('add'|'list'|'complete'|'clear'), "
                "text (for 'add'), id (for 'complete')."
            ),
            func=tasks_tool,
        )
    )

    # -------------- calendar --------------
    tool_registry.register(
        RegisteredTool(
            name="calendar",
            description=(
                "Lightweight per-device calendar. "
                "Understands phrases like 'Add calendar event Meeting at 5 PM' "
                "or 'Show my calendar'. Args: action ('add'|'list'|'clear'), "
                "title, when."
            ),
            func=calendar_tool,
        )
    )

# Auto-register all tools at import time
register_builtin_tools()

