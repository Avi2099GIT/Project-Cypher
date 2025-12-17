from __future__ import annotations

import time
from typing import Dict, Any, Optional, List

from cloud.api.assistant.mcp.mcp_client_base import MCPClient
from cloud.api.assistant.mcp.models import MCPToolDescriptor, MCPCallResult


class DockerMCP(MCPClient):
    name = "docker"

    def __init__(self) -> None:
        super().__init__()
        self.enabled = False
        self._client = None
        self._probe()

    def _probe(self) -> None:
        try:
            import docker
            client = docker.from_env()
            client.ping()
            self._client = client
            self.enabled = True
        except Exception:
            self.enabled = False

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok" if self.enabled else "down"}

    async def list_tools(self) -> List[MCPToolDescriptor]:
        return [
            MCPToolDescriptor(
                name="list_containers",
                description="List running Docker containers",
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

        if not self.enabled or not self._client:
            return MCPCallResult(
                tool="docker",
                payload={},
                success=False,
                error="Docker daemon not available",
            )

        if tool != "list_containers":
            return MCPCallResult(
                tool="docker",
                payload={},
                success=False,
                error=f"Unknown docker tool: {tool}",
            )

        containers = [
            {"id": c.id, "name": c.name, "status": c.status}
            for c in self._client.containers.list()
        ]

        return MCPCallResult(
            tool="docker.list_containers",
            payload={
                "containers": containers,
                "_duration_ms": (time.time() - start) * 1000,
            },
            success=True,
        )
