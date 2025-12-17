from __future__ import annotations
from typing import Any, Dict, List, Optional
import os
import asyncio
from anthropic import AsyncAnthropic

from cloud.api.assistant.mcp.mcp_client_base import MCPClient
from cloud.api.assistant.mcp.models import MCPToolDescriptor, MCPCallResult

class ClaudeMCP(MCPClient):
    """
    Claude API implementation using the official 'anthropic' SDK.
    """
    name = "claude"

    def __init__(self) -> None:
        super().__init__()
        # Priority: Env Var -> Admin Key -> None
        key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_ADMIN_API_KEY")
        self.api_key = key
        self.enabled = bool(key)
        self.client: Optional[AsyncAnthropic] = None
        if self.enabled:
            self.client = AsyncAnthropic(api_key=self.api_key)

    async def health(self) -> Dict[str, Any]:
        if not self.enabled:
             return {"status": "down", "error": "ANTHROPIC_API_KEY missing"}
        return {"status": "ok"}

    async def list_tools(self) -> List[MCPToolDescriptor]:
        return [
            MCPToolDescriptor(
                name="ask",
                description="Ask Claude a question or send a message",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The message to send to Claude"},
                        "model": {"type": "string", "description": "Model to use (default: claude-3-opus-20240229)"}
                    },
                    "required": ["query"]
                }
            )
        ]

    async def call(
        self,
        *,
        tool: str,
        payload: Dict[str, Any],
        ctx: Optional[Dict[str, Any]] = None,
    ) -> MCPCallResult:
        if tool != "ask":
            return MCPCallResult(
                tool=f"{self.name}.{tool}",
                payload={},
                success=False,
                error=f"Tool '{tool}' not found",
            )
            
        if not self.client:
             return MCPCallResult(tool=tool, payload={}, success=False, error="Client not initialized")

        query = payload.get("query")
        if not query:
             return MCPCallResult(tool=tool, payload={}, success=False, error="Missing query")

        model = payload.get("model", "claude-3-opus-20240229")

        try:
            # SDK Call
            message = await self.client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": query}
                ]
            )
            
            # Extract Text
            text = ""
            for block in message.content:
                if block.type == 'text':
                    text += block.text
            
            return MCPCallResult(
                tool=f"{self.name}.ask",
                payload={"response": text},
                success=True
            )
        except Exception as e:
            return MCPCallResult(
                tool=f"{self.name}.ask",
                payload={},
                success=False,
                error=str(e)
            )
