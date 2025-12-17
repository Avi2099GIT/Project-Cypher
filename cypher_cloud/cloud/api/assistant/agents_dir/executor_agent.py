# # cloud/api/assistant/agents_dir/executor_agent.py
# from __future__ import annotations

# from typing import Any, Dict, List
# import logging

# from cloud.api.assistant.tools_registry import tool_registry
# from cloud.api.assistant.tools_base import ToolContext
# from cloud.api.assistant.orchestrator.tracer import tracer
# logger = logging.getLogger(__name__)


# class ExecutorAgent:
 
#     async def run(
#         self,
#         steps: List[Dict[str, Any]],
#         ctx: Dict[str, Any],
#     ) -> List[Dict[str, Any]]:
        
#         device = ctx.get("device") or {"device_id": "local-dev"}
#         history = ctx.get("history") or []
#         message = ctx.get("message") or ""

#         tool_ctx = ToolContext(
#             device=device,
#             history=history,
#             message=message,
#         )

#         results: List[Dict[str, Any]] = []

#         for step in steps:
#             name = step.get("tool")
#             args = step.get("args") or {}

#             if not name:
#                 continue

#             try:
#                 result = await tool_registry.call(name=name, args=args, ctx=tool_ctx)

#                 # Convert status:error into exception
#                 if isinstance(result, dict) and result.get("status") == "error":
#                     raise RuntimeError(result.get("message", "Tool execution failed"))

#                 results.append(
#                     {
#                         "tool": name,
#                         "args": args,
#                         "result": result,
#                     }
#                 )

#             except Exception as e:
#                 logger.exception("ExecutorAgent: error calling tool %s: %s", name, e)
#                 results.append(
#                     {
#                         "tool": name,
#                         "args": args,
#                         "error": str(e),
#                     }
#                 )
#                 # 🔴 propagate upwards so the graph marks this node as FAILED
#                 raise

#         return results


# cloud/api/assistant/agents_dir/executor_agent.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import time

from cloud.api.assistant.tools_registry import tool_registry
from cloud.api.assistant.tools_base import ToolContext
from cloud.api.assistant.orchestrator.tracer import tracer
from cloud.api.assistant.orchestrator.node import NodeStatus

from cloud.api.assistant.mcp.registry import mcp_registry
from cloud.api.assistant.mcp.errors import (
    MCPError,
    MCPConfigError,
    MCPConnectionError,
    MCPNotAvailableError,
)
from cloud.api.assistant.mcp.models import MCPCallResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# MCP → LOCAL FALLBACK MAP (AUTHORITATIVE)
# ---------------------------------------------------------

MCP_TO_LOCAL_FALLBACK: Dict[str, str] = {
    "mcp:shell.exec": "os_control",
    "mcp:playwright.run_flow": "web_search",
}


class ExecutorAgent:
    """
    Executes planned tool steps.

    Supports:
      - built-in tools via ToolRegistry
      - MCP tools via mcp:<client>.<tool_name>

    Guarantees:
      - MCP failure falls back to correct local tools
      - Local tools are never skipped
      - Execution results are always recorded
      - PlannerV2 guarantees are honored at runtime
    """

    # ---------------------------------------------------------
    # MCP EXECUTION
    # ---------------------------------------------------------

    async def _call_mcp_tool(
        self,
        *,
        full_name: str,
        args: Dict[str, Any],
        ctx: Dict[str, Any],
    ) -> MCPCallResult:

        try:
            _, rest = full_name.split(":", 1)
            client_name, tool_name = rest.split(".", 1)
        except ValueError:
            raise ValueError(
                f"Invalid MCP tool name '{full_name}'. "
                "Expected format: mcp:<client>.<tool_name>"
            )

        trace_id: Optional[str] = ctx.get("trace_id")
        start = time.time()

        mcp_result: MCPCallResult = await mcp_registry.call(
            client_name=client_name,
            tool=tool_name,
            payload=args,
            ctx=ctx,
        )

        duration_ms = mcp_result.payload.get("_duration_ms")
        if duration_ms is None:
            duration_ms = (time.time() - start) * 1000.0

        if trace_id:
            tracer.record(
                trace_id=trace_id,
                node=f"mcp:{client_name}.{tool_name}",
                status=NodeStatus.SUCCESS if mcp_result.success else NodeStatus.FAILED,
                message="MCP call" if mcp_result.success else (mcp_result.error or ""),
                extra={
                    "duration_ms": duration_ms,
                    "client": client_name,
                    "tool": tool_name,
                },
            )

        return mcp_result

    # ---------------------------------------------------------
    # MAIN EXECUTION LOOP
    # ---------------------------------------------------------

    async def run(
        self,
        steps: List[Any],
        ctx: Dict[str, Any],
    ) -> List[Any]:

        device = ctx.get("device") or {"device_id": "local-dev"}
        history = ctx.get("history") or []
        message = ctx.get("message") or ""

        tool_ctx = ToolContext(
            device=device,
            history=history,
            message=message,
        )

        results: List[Any] = []

        for step in steps:
            # Debug LOG
            with open("executor_debug.log", "a", encoding="utf-8") as f:
                 f.write(f"Executor Step: {step}\n")

            name = None
            tool_args = {}

            if hasattr(step, "tool"):
                name = step.tool
                tool_args = step.args
            elif isinstance(step, dict):
                name = step.get("tool")
                tool_args = step.get("args") or {}
            
            if not name:
                print(f"EXECUTOR DEBUG: Name empty for step {step}")
                with open("executor_debug.log", "a", encoding="utf-8") as f:
                     f.write(f"Executor SKIP: Name empty for step {step}\n")
                continue

            print(f"EXECUTOR DEBUG: Processing {name}")
            with open("executor_debug.log", "a", encoding="utf-8") as f:
                 f.write(f"Executor Processing: {name}\n")

            executed_via_mcp = False

            # -------------------------------------------------
            # MCP PATH
            # -------------------------------------------------
            if isinstance(name, str) and name.startswith("mcp:"):
                client_name, tool_name = name[4:].split(".", 1)
                
                try:
                    mcp_out = await self._call_mcp_tool(
                        full_name=name,
                        args=tool_args,
                        ctx=ctx
                    )
                    
                    with open("executor_debug.log", "a", encoding="utf-8") as f:
                         f.write(f"MCP Result: success={mcp_out.success} tool={mcp_out.tool} err={mcp_out.error}\n")

                    if mcp_out.success:
                        results.append({
                            "tool": mcp_out.tool,
                            "result": mcp_out.payload,
                            "type": "mcp",
                            "fallback_from_mcp": False,
                        })
                        executed_via_mcp = True
                        continue

                    # Capture failure
                    logger.warning(
                        "MCP tool returned failure (%s): %s",
                        name, mcp_out.error
                    )
                    results.append({
                        "tool": mcp_out.tool,
                        "error": mcp_out.error,
                        "type": "mcp_error",
                        "fallback_from_mcp": False,
                    })
                    # We consider this executed (with error), so we skip local fallback to ensure error is reported.
                    executed_via_mcp = True
                    continue

                except (MCPConfigError, MCPNotAvailableError, MCPConnectionError) as e:
                    logger.warning("MCP unavailable for %s: %s", name, e)

                except MCPError:
                    logger.exception("Hard MCP error calling %s", name)
                    raise

            # -------------------------------------------------
            # LOCAL TOOL PATH (DIRECT OR FALLBACK)
            # -------------------------------------------------

            local_name = MCP_TO_LOCAL_FALLBACK.get(name, name)

            try:
                with open("executor_debug.log", "a", encoding="utf-8") as f:
                     f.write(f"LocalTool START: {local_name}\n")
                
                result = await tool_registry.call(
                    name=local_name,
                    args=tool_args,
                    ctx=tool_ctx,
                )
                
                with open("executor_debug.log", "a", encoding="utf-8") as f:
                     f.write(f"LocalTool END: {local_name} (Success)\n")

                results.append(
                    {
                        "tool": local_name,
                        "args": tool_args,
                        "result": result,
                        "type": "local",
                        "fallback_from_mcp": executed_via_mcp is False
                        and name != local_name,
                    }
                )

            except Exception as e:
                logger.exception("Local tool execution failed for %s", local_name)
                results.append(
                    {
                        "tool": local_name,
                        "args": tool_args,
                        "error": str(e),
                        "type": "local",
                    }
                )


        return results
