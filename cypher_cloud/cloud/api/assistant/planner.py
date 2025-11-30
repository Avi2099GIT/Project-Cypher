from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .agents import chat_agent, planner_agent, tool_executor
from .agents import PlannerDecision


# ------------------------------------------------------------------
# TOOL FLOW
# ------------------------------------------------------------------

async def run_tool_flow(
    decision: PlannerDecision,
    message: str,
    device: Dict[str, Any],
    history: List[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Execute tool calls that were already selected by PlannerAgent.
    Planner MUST NOT be invoked again inside this function.
    """

    # Step 1: Execute tools exactly as planner decided
    tool_reply, tools_meta = await tool_executor.run(
        decision=decision,
        message=message,
        history=history,
        device=device,
    )

    # Step 2: If mixed mode — let ChatAgent verbalize tool results
    if decision.mode == "mixed":
        final_reply = await chat_agent.run(
            message=message,
            history=history,
            device=device,
            tools_used=tools_meta,
        )
        return final_reply, tools_meta

    # Step 3: For tools-only mode, return raw tool output
    return tool_reply, tools_meta


# ------------------------------------------------------------------
# MCP PLACEHOLDER
# ------------------------------------------------------------------

async def run_mcp_flow(
    decision: PlannerDecision,
    message: str,
    device: Dict[str, Any],
    history: List[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    MCP = future orchestration engine.

    For now we treat MCP the same as tool execution.
    """
    return await run_tool_flow(
        decision=decision,
        message=message,
        device=device,
        history=history,
    )
