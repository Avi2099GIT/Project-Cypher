# cloud/api/assistant/agents_dir/executor_agent.py
from __future__ import annotations

from typing import Any, Dict, List
import logging

from cloud.api.assistant.tools_registry import tool_registry
from cloud.api.assistant.tools_base import ToolContext
from cloud.api.assistant.orchestrator.tracer import tracer
logger = logging.getLogger(__name__)


class ExecutorAgent:
 
    async def run(
        self,
        steps: List[Dict[str, Any]],
        ctx: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        
        device = ctx.get("device") or {"device_id": "local-dev"}
        history = ctx.get("history") or []
        message = ctx.get("message") or ""

        tool_ctx = ToolContext(
            device=device,
            history=history,
            message=message,
        )

        results: List[Dict[str, Any]] = []

        for step in steps:
            name = step.get("tool")
            args = step.get("args") or {}

            if not name:
                continue

            try:
                result = await tool_registry.call(name=name, args=args, ctx=tool_ctx)

                # Convert status:error into exception
                if isinstance(result, dict) and result.get("status") == "error":
                    raise RuntimeError(result.get("message", "Tool execution failed"))

                results.append(
                    {
                        "tool": name,
                        "args": args,
                        "result": result,
                    }
                )

            except Exception as e:
                logger.exception("ExecutorAgent: error calling tool %s: %s", name, e)
                results.append(
                    {
                        "tool": name,
                        "args": args,
                        "error": str(e),
                    }
                )
                # 🔴 propagate upwards so the graph marks this node as FAILED
                raise

        return results
