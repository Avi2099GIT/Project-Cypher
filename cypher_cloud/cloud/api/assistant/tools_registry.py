# cloud/api/assistant/tools_registry.py
from __future__ import annotations

from typing import Dict, Any, List, Optional

from .tools_base import RegisteredTool, ToolContext
from .tools_google_calendar import calendar_google_tool
from cloud.api.assistant.tools_google_tasks import google_tasks_tool

from .tools import (
    time_tool,
    system_info_tool,
    weather_tool,
    web_search_tool,
    os_list_dir_tool,
    os_control_tool,
    notes_tool,
)

# ---------------------------------------------------------
# TOOL REGISTRY
# ---------------------------------------------------------


class ToolRegistry:
    """
    In-memory registry of local (non-MCP) tools.

    Responsibilities:
    - Store callable local tools
    - Provide safe execution via ToolContext
    - Remain MCP-agnostic (Executor handles MCP)
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
        """
        Execute a registered local tool.

        This method MUST be safe to call from:
        - ExecutorAgent
        - tests
        - background jobs
        """
        if ctx is None:
            ctx = ToolContext(
                device={},
                history=[],
                message="",
            )

        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")

        return await tool(args=args, ctx=ctx)


# ---------------------------------------------------------
# GLOBAL SINGLETON
# ---------------------------------------------------------

tool_registry = ToolRegistry()
_registered = False


# ---------------------------------------------------------
# BUILTIN TOOL REGISTRATION
# ---------------------------------------------------------

def register_builtin_tools() -> None:
    """
    Register all built-in local tools.

    NOTE:
    - MCP tools are NOT registered here
    - PlannerV2 + ExecutorAgent decide MCP usage
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
            description="Echo back provided text. Args: text.",
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
            description="Summarize text (simple placeholder). Args: text.",
            func=summarize_tool,
        )
    )

    # ---------------- time ----------------

    tool_registry.register(
        RegisteredTool(
            name="time",
            description="Get current time. Optional args: location/city.",
            func=time_tool,
        )
    )

    # -------------- weather ---------------

    tool_registry.register(
        RegisteredTool(
            name="weather",
            description="Get current weather for a city. Args: location/city.",
            func=weather_tool,
        )
    )

    # ----------- system_info --------------

    tool_registry.register(
        RegisteredTool(
            name="system_info",
            description="Get OS, Python, and runtime info.",
            func=system_info_tool,
        )
    )

    # ----------- web_search ---------------

    tool_registry.register(
        RegisteredTool(
            name="web_search",
            description="Search the web. Args: query/q.",
            func=web_search_tool,
        )
    )

    # ----------- os_list_dir --------------

    tool_registry.register(
        RegisteredTool(
            name="os_list_dir",
            description=(
                "Safely list files in a directory. "
                "Args: path (optional, default='.')"
            ),
            func=os_list_dir_tool,
        )
    )

    # ----------- os_control ---------------

    tool_registry.register(
        RegisteredTool(
            name="os_control",
            description=(
                "Safe OS automation. "
                "Supports: open_app, lock, list_processes."
            ),
            func=os_control_tool,
        )
    )

    # ---------------- notes ---------------

    tool_registry.register(
        RegisteredTool(
            name="notes",
            description="Manage notes. Args: action, content.",
            func=notes_tool,
        )
    )

    # -------------- calendar --------------

    tool_registry.register(
        RegisteredTool(
            name="calendar_google",
            description="Google Calendar integration.",
            func=calendar_google_tool,
        )
    )

    # --------------- tasks ----------------

    tool_registry.register(
        RegisteredTool(
            name="google_tasks",
            description="Manage Google Tasks.",
            func=google_tasks_tool,
        )
    )

    # --------------- connect mcp (dynamic) ----------------
    
    async def connect_mcp_tool(args: Dict[str, Any], ctx: ToolContext) -> str:
        """
        Dynamically connect to a local MCP server via stdio.
        Args:
            name (str): Unique name for this client
            command (str): Executable to run (e.g. 'python')
            args (List[str]): Arguments for command (e.g. ['server.py'])
            env (Dict[str,str]): Optional environment variables
        """
        from cloud.api.assistant.mcp_clients.generic_mcp import GenericMcpClient
        from cloud.api.assistant.mcp.registry import mcp_registry
        
        name = args.get("name")
        cmd = args.get("command")
        cargs = args.get("args") or []
        env = args.get("env")
        
        if not name or not cmd:
            return "Error: 'name' and 'command' are required."
            
        try:
            client = GenericMcpClient(name=name, command=cmd, args=cargs, env=env)
            # Verify health is ok (SDK check)
            health = await client.health()
            if health.get("status") != "ok":
               return f"Error: Failed to initialize MCP client (SDK missing?): {health}"
            
            # CRITICAL: Verify connection works by listing tools
            # This forces the Windows Event Loop check to run immediately
            try:
                await client.list_tools()
            except Exception as e:
                # Check for wrapped NotImplementedError (ExceptionGroup)
                error_str = str(e)
                if "NotImplementedError" in error_str or "unhandled errors in a TaskGroup" in error_str:
                     return "Error connecting to MCP server: Windows Event Loop Error (Wrapped): Pipes not supported. Use --loop asyncio or Docker." 
                return f"Error connecting to MCP server: {e}"
               
            mcp_registry.register(client)
            return f"Successfully registered MCP client '{name}'. You can now use its tools."
        except ValueError as ve:
            return f"Error registering client: {ve}"
        except Exception as e:
            return f"Unexpected error: {e}"

    tool_registry.register(
        RegisteredTool(
            name="connect_mcp_stdio",
            description="Connect to an MCP server process. Args: name, command, args.",
            func=connect_mcp_tool,
        )
    )

    # ---------------------------------------------------------
# ---------------------------------------------------------
# AUTO-REGISTER
# ---------------------------------------------------------

register_builtin_tools()
