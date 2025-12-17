from __future__ import annotations
from typing import Dict, Optional, Any
import logging

from .mcp_client_base import MCPClient
from .errors import MCPNotAvailableError
from .metrics import record_call
from .models import MCPCallResult
from . import safety

from cloud.api.assistant.mcp_clients.shell_mcp import ShellMCP
from cloud.api.assistant.mcp_clients.docker_mcp import DockerMCP
from cloud.api.assistant.mcp_clients.github_mcp import GitHubMCP
from cloud.api.assistant.mcp_clients.playwright_mcp import PlaywrightMCP
from cloud.api.assistant.mcp_clients.claude_mcp import ClaudeMCP
from cloud.api.assistant.mcp_clients.math_mcp import MathMCP

logger = logging.getLogger(__name__)


class MCPRegistry:
    def __init__(self) -> None:
        self._clients: Dict[str, MCPClient] = {}

    def register(self, client: MCPClient) -> None:
        if client.name in self._clients:
            raise ValueError(f"MCP client with name '{client.name}' already registered")
        # If client defines a probe function, use it to decide enabled
        try:
            if hasattr(client, "_probe_availability") and callable(getattr(client, "_probe_availability")):
                client.enabled = client._probe_availability()
            # else keep client's own .enabled default
        except Exception as e:
            logger.warning("Probe for client %s failed: %s", client.name, e)
            client.enabled = False
        self._clients[client.name] = client
        logger.info("Registered MCP client: %s (enabled=%s)", client.name, getattr(client, "enabled", False))

    def get(self, name: str) -> Optional[MCPClient]:
        return self._clients.get(name)

    def list(self) -> Dict[str, MCPClient]:
        return dict(self._clients)

    async def call(self, *, client_name: str, tool: str, payload: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None) -> MCPCallResult:
        client = self.get(client_name)
        if not client or not getattr(client, "enabled", False):
            raise MCPNotAvailableError(f"MCP client '{client_name}' is not available")

        if safety.is_dry_run():
            return MCPCallResult(tool=f"{client_name}.{tool}", payload={"simulated": True, "client": client_name, "tool": tool}, success=True, error=None, raw=None)

        result = await client.call(tool=tool, payload=payload, ctx=ctx)
        duration_ms = result.payload.get("_duration_ms", 0.0)
        record_call(client=client_name, tool=tool, duration_ms=float(duration_ms) if duration_ms else 0.0, success=result.success, error=result.error)
        return result


mcp_registry = MCPRegistry()


def register_builtin_mcp_clients() -> None:
    # register in stable order
    for cls in (ShellMCP, DockerMCP, GitHubMCP, PlaywrightMCP, ClaudeMCP, MathMCP):
        try:
            inst = cls()
            mcp_registry.register(inst)
        except Exception as e:
            logger.exception("Failed to register MCP client %s: %s", getattr(cls, "__name__", str(cls)), e)


# auto-register on import
register_builtin_mcp_clients()
