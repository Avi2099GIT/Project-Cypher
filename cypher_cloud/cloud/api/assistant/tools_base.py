from __future__ import annotations
from typing import Any, Dict, Protocol, Callable
import inspect
import asyncio


class ToolContext(Dict[str, Any]):
    """
    Context object passed to tools.
    Example:
    - device info
    - auth info
    - request metadata
    """


class Tool(Protocol):
    name: str
    description: str

    async def __call__(self, *, args: Dict[str, Any], ctx: ToolContext) -> Any:
        ...


class RegisteredTool:
    """
    Wrapper for a registered tool.
    All tools must implement:

        async def tool(args: dict, ctx: ToolContext) -> Any
    """

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[[Dict[str, Any], ToolContext], Any],
    ) -> None:
        self.name = name
        self.description = description
        self.func = func

    async def __call__(self, *, args: Dict[str, Any], ctx: ToolContext) -> Any:
        if inspect.iscoroutinefunction(self.func):
            return await self.func(args, ctx)
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: self.func(args, ctx))
