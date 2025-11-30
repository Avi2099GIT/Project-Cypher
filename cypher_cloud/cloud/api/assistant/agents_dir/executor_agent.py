# cloud/api/assistant/agents_dir/executor_agent.py
from __future__ import annotations

from typing import Any, Dict, List
import logging

from cloud.api.assistant.tools_registry import tool_registry
from cloud.api.assistant.tools_base import ToolContext

logger = logging.getLogger(__name__)


# agents_dir/executor_agent.py

class ExecutorAgent:

    async def run(self, steps: list[dict], ctx: dict):
        results = []

        for step in steps:
            name = step["tool"]
            args = step.get("args", {})

            res = await tool_registry.call(name=name, args=args, ctx=ctx)

            results.append({
                "tool": name,
                "args": args,
                "result": res,
            })

        return results
