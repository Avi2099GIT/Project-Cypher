from __future__ import annotations

import os
import time
import asyncio
from typing import Dict, Any, Optional, List

from cloud.api.assistant.mcp.mcp_client_base import MCPClient
from cloud.api.assistant.mcp.models import MCPToolDescriptor, MCPCallResult
from cloud.api.assistant.mcp.safety import validate_shell_command


class ShellMCP(MCPClient):
    name = "shell"

    def __init__(self) -> None:
        super().__init__()
        # Shell is always available
        self.enabled = True

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok"}

    async def list_tools(self) -> List[MCPToolDescriptor]:
        return [
            MCPToolDescriptor(
                name="exec",
                description="Execute a shell command (Windows-safe)",
            )
        ]

    async def call(
        self,
        *,
        tool: str,
        payload: Dict[str, Any],
        ctx: Optional[Dict[str, Any]] = None,
    ) -> MCPCallResult:
        if tool != "exec":
            return MCPCallResult(
                tool="shell.exec",
                payload={},
                success=False,
                error=f"Unknown shell tool: {tool}",
            )

        cmd = payload.get("cmd")

        if not cmd:
             return MCPCallResult(tool=tool, payload={}, success=False, error="No command provided")

        # LOGGING
        with open("executor_debug.log", "a", encoding="utf-8") as f:
             f.write(f"ShellMCP START: tool={tool} cmd={cmd}\n")

        try:
            validate_shell_command(cmd)
        except Exception as e:
             with open("executor_debug.log", "a", encoding="utf-8") as f:
                 f.write(f"ShellMCP VALIDATION FAILED: {e}\n")
             return MCPCallResult(
                tool=tool,
                payload={},
                success=False,
                error=str(e),
            )

        import subprocess

        try:
            # Windows-safe execution: bypass asyncio loop limitations by using thread
            def run_sync():
                return subprocess.run(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

            # Run in thread pool
            proc = await asyncio.to_thread(run_sync)
            
            with open("executor_debug.log", "a", encoding="utf-8") as f:
                 f.write(f"ShellMCP END: returncode={proc.returncode}\n")

            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or "Unknown shell error"
                return MCPCallResult(
                    tool=tool,
                    payload={"cmd": cmd},
                    success=False,
                    error=f"Command failed (exit {proc.returncode}): {err_msg}",
                )

            output = proc.stdout.strip()
            return MCPCallResult(
                tool=tool,
                payload={"output": output},
                success=True,
            )
        except Exception as e:
            with open("executor_debug.log", "a", encoding="utf-8") as f:
                 f.write(f"ShellMCP EXCEPTION: {repr(e)}\n")
            return MCPCallResult(
                tool=tool,
                payload={"cmd": cmd},
                success=False,
                error=str(e),
            )

