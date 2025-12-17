from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .models import MCPToolDescriptor, MCPCallResult


class MCPClient(ABC):
    """
    Base contract for MCP clients.

    AUTO-ENABLE MODEL:
    - Each client decides availability during __init__()
    - Registry trusts `client.enabled`
    """

    name: str = "base"

    def __init__(self) -> None:
        self.enabled: bool = False

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def list_tools(self) -> List[MCPToolDescriptor]:
        ...

    @abstractmethod
    async def call(
        self,
        *,
        tool: str,
        payload: Dict[str, Any],
        ctx: Optional[Dict[str, Any]] = None,
    ) -> MCPCallResult:
        ...
