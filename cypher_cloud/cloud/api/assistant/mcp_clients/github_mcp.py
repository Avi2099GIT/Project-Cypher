from __future__ import annotations

import os
import time
from typing import Dict, Any, Optional, List

import httpx

from cloud.api.assistant.mcp.mcp_client_base import MCPClient
from cloud.api.assistant.mcp.models import MCPToolDescriptor, MCPCallResult


class GitHubMCP(MCPClient):
    name = "github"

    def __init__(self) -> None:
        super().__init__()
        self.token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("GITHUB_REPO")
        self.enabled = bool(self.token and self.repo)

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok" if self.enabled else "down"}

    async def list_tools(self) -> List[MCPToolDescriptor]:
        return [
            MCPToolDescriptor(
                name="list_pull_requests",
                description="List pull requests for configured repository",
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
                tool="github",
                payload={},
                success=False,
                error="GitHub MCP not configured",
            )

        if tool != "list_pull_requests":
            return MCPCallResult(
                tool="github",
                payload={},
                success=False,
                error=f"Unknown github tool: {tool}",
            )

        owner, repo = self.repo.split("/", 1)

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            r.raise_for_status()

        return MCPCallResult(
            tool="github.list_pull_requests",
            payload={
                "pulls": r.json(),
                "_duration_ms": (time.time() - start) * 1000,
            },
            success=True,
        )
