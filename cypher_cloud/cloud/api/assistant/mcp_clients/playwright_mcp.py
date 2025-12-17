from __future__ import annotations

import os
import time
from typing import Dict, Any, Optional, List

import httpx

from cloud.api.assistant.mcp.mcp_client_base import MCPClient
from cloud.api.assistant.mcp.models import MCPToolDescriptor, MCPCallResult


class PlaywrightMCP(MCPClient):
    name = "playwright"

    def __init__(self) -> None:
        super().__init__()
        self.base_url = os.getenv("PLAYWRIGHT_MCP_URL")
        self.enabled = False
        self._probe()

    def _probe(self) -> None:
        if not self.base_url:
            return
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=2)
            if r.status_code == 200:
                self.enabled = True
        except Exception:
            self.enabled = False

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok" if self.enabled else "down"}

    async def list_tools(self) -> List[MCPToolDescriptor]:
        return [
            MCPToolDescriptor(
                name="run_flow",
                description="Run a browser automation flow",
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

        if not self.enabled:
            return MCPCallResult(
                tool="playwright",
                payload={},
                success=False,
                error="Playwright MCP not available",
            )

        if tool != "run_flow":
            return MCPCallResult(
                tool="playwright",
                payload={},
                success=False,
                error=f"Unknown playwright tool: {tool}",
            )

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self.base_url}/run", json=payload)
            r.raise_for_status()

        return MCPCallResult(
            tool="playwright.run_flow",
            payload={
                "result": r.json(),
                "_duration_ms": (time.time() - start) * 1000,
            },
            success=True,
        )
