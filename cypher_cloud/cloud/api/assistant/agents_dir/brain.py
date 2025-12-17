from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

from cloud.api.assistant.orchestrator.executor import GraphExecutor
from cloud.api.assistant.orchestrator.cypher_graph import build_cypher_graph
from cloud.api.assistant.memory import memory_service

logger = logging.getLogger(__name__)


class CypherBrain:
    """
    Cypher Phase-4 Brain (Graph Orchestrated + Memory V2)

    Orchestration:
        intent → entity → safety → reasoning → arbiter
        → planner → executor → verifier → chat
    """

    def __init__(self) -> None:
        self.graph = build_cypher_graph()
        self.executor = GraphExecutor(self.graph)

        logger.info("CypherBrain initialized with graph: %s", self.graph.name)

    async def process(
        self,
        message: str,
        ctx: Dict[str, Any],
    ) -> Tuple[str, List[Dict[str, Any]]]:

        device = ctx.get("device") or {"device_id": "local-dev"}
        history: List[Dict[str, Any]] = ctx.get("history") or []

        logger.info(
            "CypherBrain processing message graph=%s device=%s",
            self.graph.name,
            device.get("device_id") or device.get("id") or "unknown",
        )

        # -------------------------------
        # Execute orchestration graph
        # -------------------------------
        graph_ctx, tracer = await self.executor.run_query(
            message=message,
            history=history,
            device=device,
            extras=ctx,
        )

        # -------------------------------
        # Extract artifacts
        # -------------------------------
        final = graph_ctx.extras.get("final_reply")
        tools_meta = graph_ctx.extras.get("tool_result") or []
        decision = graph_ctx.extras.get("decision") or {}
        reasoning = graph_ctx.extras.get("reasoning") or {}
        verification = graph_ctx.extras.get("verification") or {}

        # 🔧 FIX #1: correct key for planner presence
        execution_plan = graph_ctx.extras.get("execution_plan")

        if not final:
            logger.error(
                "No final_reply produced by graph. Trace=%s",
                graph_ctx.trace_id,
            )
            final = str(tools_meta)

        # -------------------------------
        # EPISODIC MEMORY
        # -------------------------------
        try:
            # User episode
            memory_service.store_episode(
                device=device,
                role="user",
                content=message,
                meta={
                    "trace_id": graph_ctx.trace_id,
                    "tools_planned": bool(execution_plan),
                    "decision": decision,
                    "reasoning": reasoning,
                },
            )

            # Assistant episode
            suppress_for_reasoning = False

            # 🔧 FIX #2: suppress ALL OS / MCP execution tools
            for t in tools_meta:
                tool_name = (t.get("tool") or "").lower()

                if (
                    tool_name == "os_control"
                    or tool_name.startswith("mcp:")
                ):
                    suppress_for_reasoning = True
                    break

            memory_service.store_episode(
                device=device,
                role="assistant",
                content=final,
                meta={
                    "trace_id": graph_ctx.trace_id,
                    "tools_used": tools_meta,
                    "verification": verification,
                    "suppress_for_reasoning": suppress_for_reasoning,
                },
            )

        except Exception:
            logger.exception(
                "Failed to store episodic memory for trace_id=%s",
                graph_ctx.trace_id,
            )

        logger.debug(
            "Execution trace %s → %s",
            graph_ctx.trace_id,
            tracer.to_dict(),
        )

        return final, tools_meta
