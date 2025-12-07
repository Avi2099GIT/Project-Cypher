from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

from cloud.api.assistant.orchestrator.executor import GraphExecutor
from cloud.api.assistant.orchestrator.cypher_graph import build_cypher_graph
from cloud.api.assistant.memory import memory_service  # <-- NEW

logger = logging.getLogger(__name__)


class CypherBrain:
    """
    Cypher Phase-4 Brain (Graph Orchestrated + Memory V2)

    Orchestration:
        intent → entity → safety → reasoning → arbiter
        → planner → executor → verifier → chat

    Memory:
      - Each call to `process`:
          * Stores the user message as an episode
          * Stores the final assistant reply as an episode
          * Attaches lightweight metadata (tools, decision, verification)
    """

    def __init__(self) -> None:
        # Build Cypher execution graph
        self.graph = build_cypher_graph()
        self.executor = GraphExecutor(self.graph)

        logger.info("CypherBrain initialized with graph: %s", self.graph.name)

    async def process(
        self,
        message: str,
        ctx: Dict[str, Any],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute the full Cypher graph for a user message.

        Returns:
            (final_reply, tools_meta)
        """

        device = ctx.get("device") or {"device_id": "local-dev"}
        history: List[Dict[str, Any]] = ctx.get("history") or []

        logger.info(
            "CypherBrain processing message trace graph=%s device=%s",
            self.graph.name,
            device.get("device_id") or device.get("id") or "unknown",
        )

        # Execute orchestration graph
        graph_ctx, tracer = await self.executor.run_query(
            message=message,
            history=history,
            device=device,
            extras=ctx,
        )

        # Extract core artifacts from graph context
        final = graph_ctx.extras.get("final_reply")
        tools_meta = graph_ctx.extras.get("tool_result") or []
        decision = graph_ctx.extras.get("decision") or {}
        reasoning = graph_ctx.extras.get("reasoning") or {}
        verification = graph_ctx.extras.get("verification") or {}

        if not final:
            logger.error("No final_reply produced by graph. Trace=%s", graph_ctx.trace_id)
            final = "Something went wrong internally, but I am still running."

        # -------------------------------
        # EPISODIC MEMORY: store turn
        # -------------------------------
        try:
            # User episode
            memory_service.store_episode(
                device=device,
                role="user",
                content=message,
                meta={
                    "trace_id": graph_ctx.trace_id,
                    "tools_planned": bool(graph_ctx.extras.get("plan")),
                    "decision": decision,
                    "reasoning": reasoning,
                },
            )

            # Assistant episode
            # Assistant episode
            suppress_for_reasoning = False

            # If any OS-control tool ran in this turn, mark this episode as
            # something we should not treat as long-term “truth” for reasoning.
            for t in tools_meta:
                name = (t.get("tool") or "").lower()
                if name == "os_control":
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
            # Memory failures must never break the main flow
            logger.exception("Failed to store episodic memory for trace_id=%s", graph_ctx.trace_id)

        # Debug trace visibility (can be wired to dashboards later)
        logger.debug(
            "Execution trace %s → %s",
            graph_ctx.trace_id,
            tracer.to_dict(),
        )

        return final, tools_meta
