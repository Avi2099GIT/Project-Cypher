from __future__ import annotations

from typing import Any, Dict, Protocol, Callable
import inspect
import asyncio


# ---------------------------------------------------------
# TOOL CONTEXT (OBJECT + DICT-COMPAT)
# ---------------------------------------------------------

class ToolContext:
    """
    Context object passed to tools.

    COMPATIBILITY GUARANTEE:
    - Works as attribute object (ctx.message)
    - Works like dict (ctx.get("message"))
    - Prevents breaking legacy tools

    Canonical fields:
    - device
    - history
    - message
    - extras
    """

    def __init__(
        self,
        device: Dict[str, Any],
        history: list,
        message: str,
        **extras: Any,
    ) -> None:
        self.device = device
        self.history = history
        self.message = message
        self.extras: Dict[str, Any] = extras

    # -----------------------------
    # DICT COMPATIBILITY (CRITICAL)
    # -----------------------------

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.extras.get(key, default)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key) or key in self.extras


# ---------------------------------------------------------
# TOOL PROTOCOL (STATIC TYPING ONLY)
# ---------------------------------------------------------

class Tool(Protocol):
    name: str
    description: str

    async def __call__(self, *, args: Dict[str, Any], ctx: ToolContext) -> Any:
        ...


# ---------------------------------------------------------
# REGISTERED TOOL WRAPPER
# ---------------------------------------------------------

class RegisteredTool:
    """
    Wrapper for a registered local tool.

    Tool contract:
        async def tool(args: Dict[str, Any], ctx: ToolContext) -> Any
        OR
        def tool(args: Dict[str, Any], ctx: ToolContext) -> Any
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

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.func(args, ctx),
        )
