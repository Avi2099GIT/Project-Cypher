from __future__ import annotations

import time
from typing import Dict, Any, Optional, List

from cloud.api.assistant.mcp.mcp_client_base import MCPClient
from cloud.api.assistant.mcp.models import MCPToolDescriptor, MCPCallResult


class MathMCP(MCPClient):
    name = "math"
    
    def __init__(self) -> None:
        super().__init__()
        # Always enabled for testing
        self.enabled = True

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok"}

    async def list_tools(self) -> List[MCPToolDescriptor]:
        return [
            MCPToolDescriptor(
                name="add",
                description="Add two numbers. Args: a, b",
            ),
            MCPToolDescriptor(
                name="multiply",
                description="Multiply two numbers. Args: a, b",
            )
        ]

    async def call(
        self,
        *,
        tool: str,
        payload: Dict[str, Any],
        ctx: Optional[Dict[str, Any]] = None,
    ) -> MCPCallResult:
        start = time.time()

        if tool not in ("add", "multiply"):
            return MCPCallResult(
                tool=f"math.{tool}",
                payload={},
                success=False,
                error=f"Unknown math tool: {tool}",
            )

        try:
            val_a = float(payload.get("a", 0))
            val_b = float(payload.get("b", 0))
            
            if tool == "add":
                result = val_a + val_b
            else:
                result = val_a * val_b
                
            return MCPCallResult(
                tool=f"math.{tool}",
                payload={
                    "result": result,
                    "operation": tool,
                    "inputs": {"a": val_a, "b": val_b},
                    "_duration_ms": (time.time() - start) * 1000,
                },
                success=True,
            )
        except Exception as e:
            return MCPCallResult(
                tool=f"math.{tool}",
                payload={},
                success=False,
                error=str(e),
            )
