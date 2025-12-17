from __future__ import annotations
import asyncio
import sys
from typing import Dict, Any, List, Optional
import os

from cloud.api.assistant.mcp.mcp_client_base import MCPClient
from cloud.api.assistant.mcp.models import MCPToolDescriptor, MCPCallResult

# Try importing official SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_SDK = True
except ImportError:
    HAS_SDK = False

class GenericMcpClient(MCPClient):
    """
    Adapter for any Standard MCP server (Stdio).
    """
    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None) -> None:
        super().__init__()
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.enabled = HAS_SDK
        self._session: Optional[ClientSession] = None
        self._exit_stack = None

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok" if self.enabled else "missing_sdk"}

    async def list_tools(self) -> List[MCPToolDescriptor]:
        if not self.enabled: return []
        
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env={**os.environ, **(self.env or {})}
        )
        
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    
                    descriptors = []
                    for t in response.tools:
                        descriptors.append(MCPToolDescriptor(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.inputSchema
                        ))
                    return descriptors
        except NotImplementedError:
             raise NotImplementedError("Windows Event Loop Error: Pipes not supported. Use --loop asyncio or Docker.")
        except Exception as e:
             error_str = str(e)
             if "NotImplementedError" in error_str or "unhandled errors in a TaskGroup" in error_str:
                 raise NotImplementedError(f"Windows Event Loop Error (Wrapped): Pipes not supported. Details: {e}")
             raise e

    async def call(
        self,
        *,
        tool: str,
        payload: Dict[str, Any],
        ctx: Optional[Dict[str, Any]] = None,
    ) -> MCPCallResult:
        if not self.enabled: 
            return MCPCallResult(self.name, payload, False, "SDK missing")

        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env={**os.environ, **(self.env or {})}
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    # Call tool
                    result = await session.call_tool(tool, arguments=payload)
                    
                    output = ""
                    for content in result.content:
                        if content.type == "text":
                            output += content.text
                    
                    return MCPCallResult(
                        tool=f"{self.name}.{tool}",
                        payload={"result": output},
                        success=True
                    )
        except NotImplementedError:
            err = "Windows Event Loop Error: Pipes not supported. Use --loop asyncio or Docker."
            with open("executor_debug.log", "a", encoding="utf-8") as f:
                 f.write(f"[GenericMcpClient] ERROR: {err}\n")
            return MCPCallResult(
                tool=f"{self.name}.{tool}",
                payload={},
                success=False,
                error=err
            )
        except Exception as e:
            return MCPCallResult(
                tool=f"{self.name}.{tool}",
                payload={},
                success=False,
                error=str(e)
            )
